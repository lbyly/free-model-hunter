"""
上下文 (Context) / MaxTokens 获取与同步模块

从多个数据源获取每个模型的 context_window 和 max_tokens 信息，
合并后回写 Free-Model-Hub 数据库，供同步到 OpenClaw / Hermes 客户端使用。

数据源优先级（高 → 低）：
  1. OpenRouter API  https://openrouter.ai/api/v1/models  (context_length) —— 官方真实值
  2. Hermes 本地缓存 models_dev_cache.json (limit.context / limit.output) —— 近似/兜底值
  3. FMH 数据库已有的 context_window（保底，不覆盖已有值）

说明：
- max_tokens 默认值策略：无法获取到真实 max_tokens 时，使用
  max(8192, context // 4) 作为经验默认值。
- 仅处理 FMH 数据库中已存在的 (provider_slug, model_id)，
  不新增模型，避免污染模型列表。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

# ── 数据源路径 ───────────────────────────────────────────────────────────
HERMES_LOCAL_DIR = Path(r"C:\Users\Administrator\AppData\Local\hermes")
MODELS_DEV_CACHE = HERMES_LOCAL_DIR / "models_dev_cache.json"
PROVIDER_MODELS_CACHE = HERMES_LOCAL_DIR / "provider_models_cache.json"
CONTEXT_LENGTH_CACHE = HERMES_LOCAL_DIR / "context_length_cache.yaml"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# ── slug 归一化映射 ──────────────────────────────────────────────────────
# Hermes models_dev_cache 中的 provider id（如 "zhipuai"）→ FMH provider slug（如 "zhipu"）
# 常见变体都映射到 FMH 的 slug。
SLUG_ALIASES: dict[str, str] = {
    "alibaba": "alibaba_bailian",
    "alibaba-cn": "alibaba_bailian",
    "bailian": "alibaba_bailian",
    "nvidia": "nvidia",
    "novita-ai": "novity",
    "novita": "novity",
    "github-models": "github_models",
    "github_models": "github_models",
    "zhipuai": "zhipu",
    "zai": "zhipu",
    "z-ai": "zhipu",
    "sensenova": "sensenova",
    "x-ai": "xai",
    "xai": "xai",
    "minimax": "minimax",
    "minimax-cn": "minimax",
    "groq": "groq",
    "cohere": "cohere",
    "cerebras": "cerebras",
    "google": "gemini",
    "gemini": "gemini",
    "openrouter": "openrouter",
    "anyrouter": "anyrouter",
    "opencode": "opencode",
    "opencode-go": "opencode",
    "mollinations": "mollinations",
    "pollinations": "mollinations",
    "notdiamond": "notdiamond",
    "9router": "ninerouter",
    "zen": "zen",
    "cpamc": "cpamc",
    "anthropic": "anthropic",
    "openai": "openai",
    "deepseek": "deepseek",
    "stepfun": "stepfun",
    "moonshotai": "moonshotai",
    "mistral": "mistral",
    "siliconflow": "siliconflow",
    "siliconflow-cn": "siliconflow",
}

DEFAULT_MAX_TOKENS = 8192

# 无法获取 max_tokens 的模型按 context 比例计算的经验下限
MIN_DEFAULT_MAX_TOKENS = 8192

# ── 已知模型上下文（硬编码兜底）────────────────────────────────────────
# 数据源：Hermes 缓存 / OpenRouter / 各模型官方文档。
# 当 Hermes 缓存与 OpenRouter 都无法匹配时，用这里的准确值兜底，
# 避免这些知名模型显示 "未知"。
# 键：model_id（小写）。值：{context, max_tokens?}
KNOWN_CONTEXTS: dict[str, dict] = {
    # ── Gemini / Google ──
    "gemini-1.5-flash": {"context": 1048576},
    "gemini-1.5-pro": {"context": 2097152},
    "gemini-2.0-pro-exp": {"context": 1048576},
    "gemini-2.0-flash": {"context": 1048576},
    "gemini-2.0-flash-lite": {"context": 1048576},
    "gemini-2.0-flash-exp-image-generation": {"context": 32767},
    "text-embedding-004": {"context": 2048},
    # ── GitHub Models ──
    "o1-preview": {"context": 128000},
    "o1-mini": {"context": 128000},
    "o3-mini": {"context": 200000},
    "gpt-4o": {"context": 128000},
    "gpt-4o-mini": {"context": 128000},
    "claude-3.5-sonnet": {"context": 200000},
    "claude-3.5-haiku": {"context": 200000},
    "claude-3-opus": {"context": 200000},
    "deepseek-chat": {"context": 128000},
    "codestral-latest": {"context": 256000},
    "mistral-large": {"context": 128000},
    "llama-3.2-3b": {"context": 128000},
    "llama-3.2-11b": {"context": 128000},
    "llama-3.3-70b": {"context": 128000},
    "phi-3.5-mini": {"context": 128000},
    "phi-4": {"context": 128000},
    # ── Novity (Novita) ──
    "meta-llama/llama-3-8b-instruct": {"context": 8192},
    "meta-llama/llama-3-70b-instruct": {"context": 8192},
    "microsoft/wizardlm-2-8x22b": {"context": 65535},
    "inclusionai/ling-3.0-flash": {"context": 262144},
    # ── Cohere ──
    "command-r": {"context": 128000},
    "command-r-plus": {"context": 128000},
    "command-light": {"context": 8192},
    "embed-english-v3.0": {"context": 512},
    # ── Groq ──
    "mixtral-8x7b-32768": {"context": 32768},
    # ── xAI ──
    "grok-2": {"context": 131072},
    "grok-2-vision": {"context": 32768},
    # ── NotDiamond ──
    "gpt-4-0613": {"context": 8192},
    "llama-3-70b-chat-hf": {"context": 8192},
    "llama-3-8b-chat-hf": {"context": 8192},
    "meta-llama-3-70b-instruct": {"context": 8192},
    "meta-llama-3-8b-instruct": {"context": 8192},
    "meta-llama-3.1-405b-instruct-turbo": {"context": 128000},
    # ── 其他常见模型 ──
    "opencode-llm": {"context": 128000},
    "zen-chat": {"context": 128000},
    "sensenova-6.7-flash-lite": {"context": 131072},
    "sensenova-u1-fast": {"context": 131072},
}


def normalize_slug(slug: str) -> str:
    """将数据源中的 provider 标识归一化到 FMH 的 slug。"""
    return SLUG_ALIASES.get(slug.strip().lower(), slug.strip().lower())


# ── models_dev_cache.json 读取 ───────────────────────────────────────────
def load_models_dev_cache(path: Optional[Path] = None) -> dict:
    """
    读取 Hermes models_dev_cache.json，返回:
      { provider_id: { model_id: {"context": int, "output": int} } }
    仅保留包含 limit.context 的模型。
    """
    path = path or MODELS_DEV_CACHE
    result: dict[str, dict] = {}
    if not path.exists():
        logger.warning(f"models_dev_cache.json 不存在: {path}")
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"加载 {path} 失败: {e}")
        return result

    if not isinstance(raw, dict):
        return result

    for provider_id, pdata in raw.items():
        if not isinstance(pdata, dict):
            continue
        models = pdata.get("models") or {}
        if not isinstance(models, dict):
            continue
        provider_map: dict[str, dict] = {}
        for model_id, mdata in models.items():
            if not isinstance(mdata, dict):
                continue
            limit = mdata.get("limit") or {}
            if not isinstance(limit, dict):
                continue
            ctx = limit.get("context")
            out = limit.get("output")
            if ctx:
                entry: dict = {}
                try:
                    entry["context"] = int(ctx)
                except (ValueError, TypeError):
                    continue
                if out:
                    try:
                        entry["output"] = int(out)
                    except (ValueError, TypeError):
                        pass
                provider_map[model_id] = entry
        if provider_map:
            result[provider_id] = provider_map

    return result


# ── OpenRouter API 读取 ──────────────────────────────────────────────────
def load_openrouter_models(timeout: float = 20.0) -> dict:
    """
    从 OpenRouter API 获取模型 context_length，返回:
      { model_id: {"context": int} }
    免 key 即可访问。失败时返回空 dict。
    """
    result: dict[str, dict] = {}
    if httpx is None:
        logger.warning("httpx 未安装，跳过 OpenRouter 数据源")
        return result

    try:
        resp = httpx.get(
            OPENROUTER_MODELS_URL,
            headers={"User-Agent": "FreeModelsHub/2.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            mid = item.get("id")
            ctx = item.get("context_length")
            if not mid or not ctx:
                continue
            try:
                result[mid] = {"context": int(ctx)}
            except (ValueError, TypeError):
                continue
    except Exception as e:
        logger.warning(f"OpenRouter API 请求失败: {e}")

    return result


# ── 数据库写入 ───────────────────────────────────────────────────────────
def _import_db():
    """延迟导入 database 模块，兼容不同启动方式。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database import get_db
    return get_db


def get_db_models() -> list[dict]:
    """
    读取 FMH 数据库中所有模型的 (provider_slug, model_id, context_window)。
    返回: [{"provider_slug": str, "model_id": str, "context_window": str}]
    """
    get_db = _import_db()
    rows: list[dict] = []
    with get_db() as db:
        results = db.execute(
            """
            SELECT p.slug AS provider_slug, m.model_id, m.context_window
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            """
        ).fetchall()
        for r in results:
            rows.append(dict(r))
    return rows


def update_model_context(
    provider_slug: str,
    model_id: str,
    context: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> bool:
    """更新单个模型的 context_window / max_tokens。返回是否实际更新。"""
    get_db = _import_db()
    sets = []
    params = []
    if context is not None:
        sets.append("context_window = ?")
        params.append(str(context))
    if max_tokens is not None:
        sets.append("max_tokens = ?")
        params.append(int(max_tokens))
    if not sets:
        return False

    with get_db() as db:
        row = db.execute(
            "SELECT id FROM providers WHERE slug = ?", (provider_slug,)
        ).fetchone()
        if not row:
            return False
        set_sql = ", ".join(sets)
        db.execute(
            f"""
            UPDATE models
            SET {set_sql}, updated_at = CURRENT_TIMESTAMP
            WHERE model_id = ? AND provider_id = ?
            """,
            (*params, model_id, row["id"]),
        )
    return True


def compute_max_tokens(context: Optional[int]) -> int:
    """根据上下文计算经验默认 max_tokens。"""
    if context and context > 0:
        return max(MIN_DEFAULT_MAX_TOKENS, context // 4)
    return DEFAULT_MAX_TOKENS


# ── 模糊匹配兜底 ─────────────────────────────────────────────────────────
# 聚合中转商（manifest/cpamc/nvidia/opencode 等）的 model_id 形如
#   "copilot/gpt-4o-subscription"、"nvidia/nemotron-3-super-120b-a12b:free"
# 它们内部包含可在 Hermes 缓存中精确命中的核心模型名。
# 策略：
#   1) index 中某 key 是 model_id 的子串（如 "gpt-4o" ⊆ "copilot/gpt-4o-subscription"），
#      取命中最长的 key 的 context（最长最具体，避免歧义误配）。
#   2) model_id 去掉中转后缀后的核心名（如 "gpt-4o-subscription" → "gpt-4o"）
#      精确命中 index 时优先采用。
# 太短或太泛的 key（如 "custom"、"free"、"subscription"）不参与匹配。

# 中转聚合商常见后缀，剥离后可还原为标准模型名
_SUBSCRIPTION_SUFFIXES = (
    "-subscription",
    "-free",
    "-instant",
    ":free",
    ":optimized",
    ":free",
    "-preview",
)

_FUZZY_MIN_KEY = 6
_FUZZY_BLACKLIST = {
    "app", "auto", "chat", "custom", "free", "image", "latest", "mini",
    "preview", "pro", "reasoning", "search", "small", "subscription",
    "test", "thinking", "vision", "v1", "v2", "v3", "v4", "v5", "v6",
    "deploy", "default", "dev", "fast", "flash", "high", "low", "medium",
    "nano", "omni", "plus", "safe", "stable", "turbo", "ultra", "xs",
    "optimized", "instant",
}


def _core_model_name(model_id: str) -> str:
    """去掉 provider 前缀与中转后缀，还原标准模型名。"""
    # 先只取 "/" 之后的部分（去掉 provider 前缀），如
    # "nvidia/nemotron-3-super-120b-a12b:free" → "nemotron-3-super-120b-a12b:free"
    base = model_id.split("/")[-1].strip().lower()
    # 再去掉 ":xxx" 后缀变体
    if ":" in base:
        base = base.split(":", 1)[0]
    changed = True
    while changed:
        changed = False
        for suf in _SUBSCRIPTION_SUFFIXES:
            if base.endswith(suf) and base != suf:
                base = base[: -len(suf)]
                changed = True
    return base


def _build_fuzzy_index(source: dict[str, dict]) -> dict[str, dict]:
    """为模糊匹配构建索引：同时包含完整 model_id 与去前缀后的裸名。"""
    idx: dict[str, dict] = {}
    for mid_, entry in source.items():
        idx.setdefault(mid_.lower(), entry)
        base = _core_model_name(mid_)
        if base:
            idx.setdefault(base, entry)
    return idx


def _fuzzy_match_context(
    model_id: str,
    index: dict[str, dict],
) -> Optional[int]:
    """在 index（小写 model_id -> {"context": ...}）中模糊匹配真实 context。"""
    if not model_id:
        return None
    mid = model_id.lower()
    core = _core_model_name(model_id)

    best: Optional[tuple[int, int]] = None  # (len, context)
    # 1. index key 是 model_id 子串（最长者优先）
    for key, entry in index.items():
        if not key or len(key) < _FUZZY_MIN_KEY:
            continue
        if key in _FUZZY_BLACKLIST:
            continue
        if key not in mid:
            continue
        ctx = entry.get("context")
        if not ctx:
            continue
        if best is None or len(key) > best[0]:
            best = (len(key), int(ctx))
    # 2. 核心名精确命中（比子串更准确，优先采用）
    core_entry = index.get(core)
    if core_entry and core_entry.get("context"):
        cctx = int(core_entry["context"])
        if best is None or len(core) >= best[0]:
            best = (len(core), cctx)
    return best[1] if best else None


# ── 主同步入口 ───────────────────────────────────────────────────────────
def run_context_sync(
    use_dev_cache: bool = True,
    use_openrouter: bool = True,
    verbose: bool = True,
) -> dict:
    """
    执行上下文同步。

    流程:
      1. 读取 FMH 数据库中所有模型
      2. 加载 models_dev_cache.json 与 OpenRouter 数据
      3. 为每个模型计算 context / max_tokens
      4. 写回数据库

    返回统计 dict。
    """
    start = time.time()

    # 1. 数据库现状
    db_models = get_db_models()
    by_provider: dict[str, list[dict]] = {}
    stats = {
        "total_models": len(db_models),
        "dev_cache_providers": 0,
        "openrouter_models": 0,
        "updated_models": 0,
        "used_sample_default": 0,
        "context_filled": 0,
        "max_tokens_filled": 0,
    }

    if not db_models:
        stats["message"] = "数据库无模型，跳过"
        return stats

    for m in db_models:
        by_provider.setdefault(m["provider_slug"], []).append(m)

    # 2. 数据源
    dev_cache: dict[str, dict] = {}
    if use_dev_cache:
        dev_cache = load_models_dev_cache()
        stats["dev_cache_providers"] = len(dev_cache)

    openrouter_map: dict[str, dict] = {}
    if use_openrouter:
        openrouter_map = load_openrouter_models()
        stats["openrouter_models"] = len(openrouter_map)

# 3. 逐模型计算并更新
    # 预构建索引（小写 model_id -> entry），供精确/模糊匹配使用。
    # global_model_index 来自 Hermes 缓存（近似/兜底值）。
    # openrouter_index 来自 OpenRouter（官方真实值），优先采用。
    global_model_index: dict[str, dict] = {}
    for cache_data in dev_cache.values():
        for mid, val in cache_data.items():
            # 保留第一个出现的值（避免低优先级 provider 覆盖高优先级）
            global_model_index.setdefault(mid.lower(), val)
    # 同时加入去前缀后的裸名，供模糊匹配使用
    global_model_index = _build_fuzzy_index(global_model_index)

    # OpenRouter 索引：同时保留原始 key 与去前缀裸名（供模糊匹配）
    openrouter_index: dict[str, dict] = {}
    for mid_, val in openrouter_map.items():
        openrouter_index.setdefault(mid_.lower(), val)
    openrouter_index = _build_fuzzy_index(openrouter_index)

    for provider_slug, models in by_provider.items():
        # 归一化后查找 dev cache；多个 cache provider 可能映射到同一 FMH slug
        dev_source: dict[str, dict] = {}
        for cache_id, cache_data in dev_cache.items():
            if normalize_slug(cache_id) == provider_slug.lower():
                # 合并所有匹配 provider 的模型数据
                for mid, val in cache_data.items():
                    dev_source.setdefault(mid, {}).update(val)

        for m in models:
            mid = m["model_id"]
            context: Optional[int] = None
            max_tokens: Optional[int] = None

            # ── 数据源 1 (最高优先): OpenRouter 官方真实值 ──
            # 1a. 精确 model_id 命中
            or_entry = openrouter_index.get(mid.lower())
            if or_entry:
                context = or_entry.get("context")
                max_tokens = or_entry.get("output")
            # 1b. 模糊匹配（去掉中转前缀/后缀后命中真实模型）
            if context is None:
                fuzzy_or = _fuzzy_match_context(mid, openrouter_index)
                if fuzzy_or:
                    context = fuzzy_or

            # ── 数据源 2: Hermes 缓存（近似/兜底值，仅当 OpenRouter 无真实值时）──
            if context is None:
                entry = dev_source.get(mid)
                if entry:
                    context = entry.get("context")
                    max_tokens = entry.get("output")
            if context is None:
                g_entry = global_model_index.get(mid.lower())
                if g_entry:
                    context = g_entry.get("context")
                    max_tokens = g_entry.get("output")
            if context is None:
                fuzzy_ctx = _fuzzy_match_context(mid, global_model_index)
                if fuzzy_ctx:
                    context = fuzzy_ctx

            # ── 数据源 3: 已知模型上下文硬编码兜底 ──
            if context is None:
                known_entry = KNOWN_CONTEXTS.get(mid.lower())
                if known_entry:
                    context = known_entry.get("context")
                    if max_tokens is None:
                        max_tokens = known_entry.get("max_tokens")

            # ── 数据源 4: 数据库已有 context_window ──
            if context is None and m.get("context_window"):
                try:
                    context = int(str(m["context_window"]).replace(",", "").strip())
                except (ValueError, TypeError):
                    context = None

            # max_tokens 兜底
            if max_tokens is None and context is not None:
                max_tokens = compute_max_tokens(context)
                stats["used_sample_default"] += 1

            if context is None and max_tokens is None:
                continue

            if update_model_context(provider_slug, mid, context=context, max_tokens=max_tokens):
                stats["updated_models"] += 1
                if context is not None:
                    stats["context_filled"] += 1
                if max_tokens is not None:
                    stats["max_tokens_filled"] += 1

    stats["duration_seconds"] = round(time.time() - start, 2)

    if verbose:
        logger.info(
            f"上下文同步完成: 总模型 {stats['total_models']}, "
            f"更新 {stats['updated_models']}, dev_cache providers {stats['dev_cache_providers']}, "
            f"OpenRouter 模型 {stats['openrouter_models']}, "
            f"经验默认值 {stats['used_sample_default']} 个"
        )

    return stats


def get_coverage() -> dict:
    """获取上下文填充覆盖率统计（供前端展示）。"""
    get_db = _import_db()
    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) AS c FROM models WHERE COALESCE(user_removed, 0) = 0"
        ).fetchone()["c"]
        has_ctx = db.execute(
            "SELECT COUNT(*) AS c FROM models WHERE COALESCE(user_removed, 0) = 0 AND context_window IS NOT NULL AND TRIM(context_window) != ''"
        ).fetchone()["c"]
        has_mt = db.execute(
            "SELECT COUNT(*) AS c FROM models WHERE COALESCE(user_removed, 0) = 0 AND max_tokens IS NOT NULL"
        ).fetchone()["c"]
        by_provider = db.execute(
            """
            SELECT p.slug, p.name,
                   COUNT(m.id) AS total,
                   SUM(CASE WHEN m.context_window IS NOT NULL AND TRIM(m.context_window) != '' THEN 1 ELSE 0 END) AS has_ctx,
                   SUM(CASE WHEN m.max_tokens IS NOT NULL THEN 1 ELSE 0 END) AS has_mt
            FROM providers p
            LEFT JOIN models m ON m.provider_id = p.id AND COALESCE(m.user_removed, 0) = 0
            WHERE (p.hidden IS NULL OR p.hidden = 0)
            GROUP BY p.id
            ORDER BY p.name
            """
        ).fetchall()
        providers = []
        for r in by_provider:
            providers.append({
                "slug": r["slug"],
                "name": r["name"],
                "total": r["total"],
                "has_ctx": r["has_ctx"] or 0,
                "has_mt": r["has_mt"] or 0,
            })

    return {
        "total_models": total,
        "context_covered": has_ctx,
        "max_tokens_covered": has_mt,
        "context_rate": round(has_ctx / total, 4) if total else 0,
        "max_tokens_rate": round(has_mt / total, 4) if total else 0,
        "providers": providers,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_context_sync()
    print(json.dumps(result, ensure_ascii=False, indent=2))


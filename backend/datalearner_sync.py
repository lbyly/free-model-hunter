"""
Datalearner 数据源：从 https://www.datalearner.com/ai-models/pretrained-models
获取模型上下文长度与最大输出，写回 FMH 数据库。

数据流程：
  1. 遍历 Datalearner 列表页（19 页，每页 48 个模型）收集所有模型 code
  2. 读取 FMH 数据库中未覆盖上下文的模型
  3. 对每个未覆盖模型访问 Datalearner 详情页提取上下文长度和最大输出
  4. 将 "128K"、"1M" 等格式转换为数字
  5. 写回 FMH 数据库的 context_window 和 max_tokens 字段

说明：
- 仅处理 FMH 数据库中已存在的 (provider_slug, model_id)，不新增模型
- 通过模型名模糊匹配 Datalearner 模型（model_abbr_name / model_code）
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Datalearner 配置 ────────────────────────────────────────────────────
DATALEARNER_BASE = "https://www.datalearner.com"
DATALEARNER_LIST_URL = f"{DATALEARNER_BASE}/ai-models/pretrained-models"
DATALEARNER_DETAIL_URL = f"{DATALEARNER_BASE}/ai-models/pretrained-models/{{code}}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 每页模型数
PAGE_SIZE = 48
MAX_PAGES = 20

# ── 合理性校验常量 ──────────────────────────────────────────────────────
# 用于拦截 Datalearner 解析出的错误 context / max_tokens 值（如 2048、4096 等）。
# 说明：Datalearner 主要收录对话/生成模型，其 context 通常 >= 8192。
# 2048/4096 等极低值几乎都是解析错误（抓到的是其他字段），直接拒绝。
# 已知的真实低 context 模型（如 llama2-70b=4096、嵌入模型）由 KNOWN_CONTEXTS 兜底。
MIN_CONTEXT = 8192
MAX_CONTEXT = 2097152  # 2M
MIN_MAX_TOKENS = 256
MAX_MAX_TOKENS = 2097152

# 明确表示"无数据"的解析结果，需在写入前拒绝
_NON_TOKEN_MARKERS = ("未披露", "暂无", "不适用", "未知", "无", "n/a", "na", "-", "--")


# ── 工具函数 ─────────────────────────────────────────────────────────────
def get_rsc_text(url: str, timeout: float = 20.0) -> str:
    """获取页面 RSC payload 并拼接为文本。"""
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, re.DOTALL)
    return "\n".join(chunk.replace('\\"', '"').replace('\\\\', '\\') for chunk in chunks)


def extract_models_from_list(rsc: str) -> list[dict]:
    """从列表页 RSC 数据提取模型列表。"""
    models = []
    pattern = re.compile(
        r'\{"model_id":(\d+),"model_code":"([^"]+)","model_abbr_name":"([^"]+)"'
    )
    for m in pattern.finditer(rsc):
        models.append({
            "model_id": int(m.group(1)),
            "model_code": m.group(2),
            "model_abbr_name": m.group(3),
        })
    return models


def _extract_value_after_label(rsc: str, label: str) -> Optional[str]:
    """在 RSC 中找到 label 后第一个看起来像 token 数值的值。

    同一 label 可能在页面中出现多次（如 schema.org 描述、"模型基本信息"区域、
    数值卡片区域），取其第一个看起来像 token 值的 "children"，避免抓到
    "未披露"、评测分数、价格等无关字段。
    """
    for m in re.finditer(label, rsc):
        segment = rsc[m.end():m.end() + 800]
        # 依次找该片段内所有 children 值，取第一个像 token 的
        for val_m in re.finditer(r'"children":"([^"]+)"', segment):
            candidate = val_m.group(1)
            if _looks_like_token_value(candidate):
                return candidate
    return None


def extract_context_from_detail(rsc: str) -> tuple[Optional[str], Optional[str]]:
    """从详情页 RSC 数据提取上下文长度和最大输出。

    返回 (context_display, max_output_display)，如 ("128K", "16K tokens")
    """
    context = _extract_value_after_label(rsc, r'"children":"上下文长度"')
    max_output = _extract_value_after_label(rsc, r'"最大输出长度"')
    return context, max_output


def parse_token_value(display: Optional[str]) -> Optional[int]:
    """将 "128K"、"1M"、"256K tokens" 等格式转换为数字。"""
    if not display:
        return None
    text = display.strip().lower()
    # 提取数字部分
    m = re.search(r'([\d.]+)\s*([km]?)', text)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "k":
        return int(num * 1024)
    elif unit == "m":
        return int(num * 1024 * 1024)
    return int(num)


def _looks_like_token_value(display: Optional[str]) -> bool:
    """判断提取出的显示值是否像是真实的 token 数值（而非"未披露"等占位）。"""
    if not display:
        return False
    text = display.strip().lower()
    if not text:
        return False
    # 明确表示"无数据"的占位
    for marker in _NON_TOKEN_MARKERS:
        if text == marker or text.startswith(marker):
            return False
    # 必须包含数字（如 "128K"、"16K tokens"、"1000000"）
    return bool(re.search(r'\d', text))


def is_reasonable_context(context: Optional[int], max_tokens: Optional[int] = None) -> bool:
    """
    校验 context_window 数值是否合理。

    - None 视为不合理（调用方自行处理兜底）
    - 必须在 [MIN_CONTEXT, MAX_CONTEXT] 范围内
    - 若同时给出 max_tokens，context 必须 >= max_tokens
      （context 比最大输出还小，说明解析错误）
    """
    if context is None:
        return False
    if not (MIN_CONTEXT <= context <= MAX_CONTEXT):
        return False
    if max_tokens is not None and context < max_tokens:
        return False
    return True


def is_reasonable_max_tokens(max_tokens: Optional[int]) -> bool:
    """校验 max_tokens 数值是否合理（None 视为不合理）。"""
    if max_tokens is None:
        return False
    return MIN_MAX_TOKENS <= max_tokens <= MAX_MAX_TOKENS


def fetch_all_datalearner_models(max_pages: int = MAX_PAGES) -> dict[str, dict]:
    """
    遍历 Datalearner 所有列表页，返回:
      { model_code_lower: {"model_code": str, "model_abbr_name": str} }
    """
    all_models: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        url = f"{DATALEARNER_LIST_URL}?page={page}"
        try:
            rsc = get_rsc_text(url)
            models = extract_models_from_list(rsc)
            if not models:
                break
            for m in models:
                all_models.setdefault(m["model_code"].lower(), m)
            logger.info(f"第 {page} 页: 获取 {len(models)} 个模型")
            # 如果不足一页，说明已到最后一页
            if len(models) < PAGE_SIZE:
                break
        except Exception as e:
            logger.warning(f"第 {page} 页获取失败: {e}")
            break
    return all_models


# ── 数据库操作 ───────────────────────────────────────────────────────────
def _import_db():
    """延迟导入 database 模块。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from database import get_db
    return get_db


def get_uncovered_models() -> list[dict]:
    """读取 FMH 数据库中未覆盖上下文的模型。"""
    get_db = _import_db()
    rows: list[dict] = []
    with get_db() as db:
        results = db.execute(
            """
            SELECT p.slug AS provider_slug, m.model_id, m.name, m.context_window
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            WHERE m.context_window IS NULL OR TRIM(m.context_window) = ''
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


# ── 已知模型上下文（硬编码兜底）────────────────────────────────────────
# 当 Datalearner 无法匹配或匹配到不合理值时，使用以下准确值兜底。
# 键：model_id（小写）。值：context 数字。
KNOWN_CONTEXTS: dict[str, int] = {
    # ── 常见对话模型 ──
    "llama-3.3-70b": 131072,
    "llama-3.2-11b": 131072,
    "llama-3.2-3b": 131072,
    "llama-3.1-8b-instant": 131072,
    "llama-3.1-70b": 131072,
    "llama-3.3-70b-versatile": 131072,
    "gemma2-9b-it": 8192,
    "mixtral-8x7b-32768": 32768,
    "deepseek-r1-distill-llama-70b": 131072,
    "gpt-4o": 131072,
    "gpt-4o-mini": 131072,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "o1-preview": 131072,
    "o1-mini": 131072,
    "o3-mini": 200000,
    "claude-3-opus": 200000,
    "claude-3.5-sonnet": 200000,
    "claude-3.5-haiku": 200000,
    "deepseek-chat": 131072,
    "deepseek-coder-6.7b-instruct": 16384,
    "codestral-latest": 256000,
    "codestral-22b-instruct-v0.1": 32768,
    "mistral-large": 131072,
    "mistral-7b-instruct-v0.3": 32768,
    "mixtral-8x7b": 32768,
    "phi-3.5-mini": 131072,
    "phi-4": 131072,
    "gemini-2.0-flash": 1048576,
    "gemini-2.0-flash-lite": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-pro": 2097152,
    "gemini-2.0-pro-exp": 1048576,
    "grok-2": 131072,
    "grok-2-vision": 32768,
    "grok-3": 131072,
    "grok-3-mini": 131072,
    "command-r": 131072,
    "command-r-plus": 131072,
    "command-light": 8192,
    "qwen-turbo": 131072,
    "qwen-plus": 131072,
    "qwen-max": 131072,
    "qwen2.5-7b-instruct": 131072,
    "qwen2.5-32b-instruct": 131072,
    "qwen2.5-72b-instruct": 131072,
    "qwen2.5-coder-32b-instruct": 131072,
    "glm-4-flash": 131072,
    "openrouter/auto": 131072,
    "gpt-oss-120b": 131072,
    "gpt-oss-20b": 131072,
    "gpt-oss-120b-medium": 131072,
    "llama-3-70b-instruct": 8192,
    "llama-3-8b-instruct": 8192,
    "llama-3-70b-chat-hf": 8192,
    "llama-3-8b-chat-hf": 8192,
    "meta-llama-3-70b-instruct": 8192,
    "meta-llama-3-8b-instruct": 8192,
    "meta-llama-3.1-405b-instruct-turbo": 131072,
    "wizardlm-2-8x22b": 65535,
    "openrouter/auto": 131072,
    "opencode-llm": 131072,
    "zen-chat": 131072,
    "sensenova-6.7-flash-lite": 131072,
    "sensenova-u1-fast": 131072,
    "llama-3.2-1b-instruct": 131072,
    "llama-3.2-3b-instruct": 131072,
    "llama-3.2-11b-vision-instruct": 131072,
    "llama-3.2-90b-vision-instruct": 131072,
    "llama-guard-4-12b": 131072,
    "llama2-70b": 4096,
    "codegemma-7b": 8192,
    "gemma-2b": 8192,
    "recurrentgemma-2b": 8192,
    "starcoder2-15b": 8192,
    "dbrx-instruct": 32768,
    "codellama-70b": 16384,
    "palmyra-creative-122b": 131072,
    "palmyra-fin-70b-32k": 32768,
    "palmyra-med-70b": 131072,
    "palmyra-med-70b-32k": 32768,
    "nemotron-3-super-120b-a12b": 131072,
    "nemotron-nano-3-30b-a3b": 204800,
    "nemotron-3-nano-30b-a3b": 204800,
    "llama-3.1-nemotron-51b-instruct": 131072,
    "llama-3.1-nemotron-70b-instruct": 131072,
    "llama-3.1-nemotron-nano-8b-v1": 131072,
    "llama-3.1-nemotron-nano-vl-8b-v1": 131072,
    "llama-3.1-nemotron-safety-guard-8b-v3": 131072,
    "llama-3.1-nemotron-ultra-253b-v1": 131072,
    "llama-3.2-nemoretriever-1b-vlm-embed-v1": 8192,
    "llama-3.2-nv-embedqa-1b-v1": 8192,
    "llama-3.3-nemotron-super-49b-v1": 131072,
    "llama-3.3-nemotron-super-49b-v1.5": 131072,
    "llama-nemotron-embed-1b-v2": 8192,
    "llama-nemotron-embed-vl-1b-v2": 8192,
    "llama3-chatqa-1.5-70b": 131072,
    "llama-3.1-nemoguard-8b-content-safety": 8192,
    "llama-3.1-nemoguard-8b-topic-control": 8192,
    "deepseek-v4-flash": 1048576,
    "deepseek-v4-pro": 1048576,
    "deepseek-v4-vision": 1048576,
    "kimi-k2.6": 262144,
    "glm-5.2": 1048576,
    "glm-4.7": 204800,
    "glm-4.6": 204800,
    "qwen3.5-ocr": 131072,
    "qwen-flash-character": 1000000,
    "tongyi-xiaomi-analysis-flash": 131072,
    "tongyi-xiaomi-analysis-pro": 131072,
    "grok-4.5": 512000,
    "grok-4.3": 512000,
    "grok-composer-2.5-fast": 204800,
    "grok-3-mini-fast": 131072,
    "grok-imagine-video": 1024,
    "grok-imagine-video-1.5-preview": 1024,
    "grok-imagine-image": 1024,
    "grok-imagine-image-quality": 1024,
    "grok-build-0.1": 131072,
    "grok-4.20-0309-non-reasoning": 512000,
    "grok-4.20-0309-reasoning": 512000,
    "grok-4.20-multi-agent-0309": 512000,
    "claude-opus-4-6-thinking": 1048576,
    "claude-sonnet-4-6": 1048576,
    "gemini-3-flash": 1048576,
    "gemini-3-flash-agent": 1048576,
    "gemini-3.1-flash-lite": 1048576,
    "gemini-3.1-flash-image": 1048576,
    "gemini-3.1-pro-low": 1048576,
    "gemini-3.5-flash-extra-low": 1048576,
    "gemini-3.5-flash-low": 1048576,
    "gemini-3.6-flash-high": 1048576,
    "gemini-pro-agent": 1048576,
    "gemini-3.1-pro-preview": 1048576,
    "gemini-3.1-flash-lite-preview": 1048576,
    "gemini-3.1-flash-live-preview": 1048576,
    "gemini-3.1-flash-tts-preview": 1048576,
    "gemini-3-flash-preview": 1048576,
    "gemini-3-pro-preview": 1048576,
    "gemini-2.5-computer-use-preview": 1048576,
    "gemini-2.5-pro": 1048576,
    "gemini-2.5-flash": 1048576,
    "gemini-2.5-flash-lite": 1048576,
    "gemini-flash-latest": 1048576,
    "gemini-flash-lite-latest": 1048576,
    "gemini-embedding-2-preview": 8192,
    "gemma-4-31b-it": 131072,
    "imagen-4-fast": 2048,
    "nano-banana-2": 4096,
    "nano-banana-pro": 4096,
    "veo-3.1": 204800,
    "veo-3.1-fast": 204800,
    "veo-3.1-lite": 204800,
    "step-3.7-flash": 262144,
    "step-3.5-flash": 262144,
    "longcat-2.0": 131072,
    "bunny": 2048,
    "mistral-nemo": 128000,
    "mistral-nemo-minitron-8b-8k-instruct": 8192,
    "mistral-nemo-12b-instruct": 128000,
    "fuyu-8b": 8192,
    "jamba-1.5-large-instruct": 256000,
    "sea-lion-7b-instruct": 8192,
    "starcoder2-15b": 8192,
    "dbrx-instruct": 32768,
    "codegemma-1.1-7b": 8192,
    "codegemma-7b": 8192,
    "deplot": 16384,
    "gemma-2b": 8192,
    "recurrentgemma-2b": 8192,
    "granite-3.0-3b-a800m-instruct": 8192,
    "granite-3.0-8b-instruct": 8192,
    "granite-34b-code-instruct": 16384,
    "granite-8b-code-instruct": 16384,
    "codellama-70b": 16384,
    "llama2-70b": 4096,
    "kosmos-2": 1024,
    "phi-3-vision-128k-instruct": 131072,
    "codestral-22b-instruct-v0.1": 32768,
    "mistral-large-2-instruct": 131072,
    "mixtral-8x22b-v0.1": 65536,
    "mistral-nemo-12b-instruct": 128000,
    "ai-synthetic-video-detector": 8192,
    "embed-qa-4": 8192,
    "ising-calibration-1.5-31b": 8192,
    "llama-3.1-nemotron-51b-instruct": 131072,
    "llama-3.2-nemoretriever-1b-vlm-embed-v1": 8192,
    "llama-3.2-nv-embedqa-1b-v1": 8192,
    "llama-nemotron-embed-1b-v2": 8192,
    "llama3-chatqa-1.5-70b": 131072,
    "mistral-nemo-minitron-8b-8k-instruct": 8192,
    "nemoretriever-parse": 8192,
    "nemotron-3-embed-1b": 8192,
    "nemotron-3.5-content-safety": 131072,
    "nemotron-4-340b-instruct": 8192,
    "nemotron-4-340b-reward": 8192,
    "nemotron-nano-3-30b-a3b": 204800,
    "nemotron-parse": 8192,
    "neva-22b": 8192,
    "nv-embedqa-e5-v5": 8192,
    "nv-embedqa-mistral-7b-v2": 8192,
    "nvclip": 8192,
    "riva-translate-4b-instruct": 8192,
    "riva-translate-4b-instruct-v2": 8192,
    "vila": 8192,
    "arctic-embed-l": 512,
    "palmyra-creative-122b": 131072,
    "palmyra-fin-70b-32k": 32768,
    "palmyra-med-70b": 131072,
    "palmyra-med-70b-32k": 32768,
    "zamba2-7b-instruct": 8192,
    "deepseek-v4-flash-nothinking": 1048576,
    "deepseek-v4-flash-search": 1048576,
    "deepseek-v4-flash-search-nothinking": 1048576,
    "deepseek-v4-pro-nothinking": 1048576,
    "deepseek-v4-pro-search": 1048576,
    "deepseek-v4-pro-search-nothinking": 1048576,
    "deepseek-v4-vision-nothinking": 1048576,
    "deepseek-v4-flash-free": 1048576,
    "laguna-s-2.1-free": 131072,
    "ling-3.0-flash-free": 262144,
    "mimo-v2.5-free": 131072,
    "nemotron-3-ultra-free": 131072,
    "north-mini-code-free": 131072,
    "qwen-flash-character": 1000000,
    "qwen-flash-character-2026-02-26": 1000000,
    "qwen3.5-ocr": 131072,
    "tongyi-xiaomi-analysis-flash": 131072,
    "tongyi-xiaomi-analysis-pro": 131072,
    "deepseek-chat": 131072,
    "gemini-2.0-flash": 1048576,
    "qwen-turbo": 131072,
}


# ── 模型匹配 ─────────────────────────────────────────────────────────────
def _normalize_name(name: str) -> str:
    """归一化模型名用于匹配：小写、去空格、去特殊字符。"""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _find_datalearner_model(
    model_id: str,
    model_name: Optional[str],
    dl_models: dict[str, dict],
) -> Optional[dict]:
    """
    在 Datalearner 模型中查找与 FMH 模型匹配的模型。

    匹配优先级：
      1. model_code 精确匹配（去掉前缀后）
      2. model_abbr_name 归一化后匹配
      3. model_id 作为子串匹配
    """
    if not model_id:
        return None

    mid_lower = model_id.lower()
    mid_norm = _normalize_name(model_id)

    # 1. 精确匹配 model_code
    if mid_lower in dl_models:
        return dl_models[mid_lower]

    # 2. 去掉 provider 前缀后匹配 model_code
    core = model_id.split("/")[-1].lower()
    if core in dl_models:
        return dl_models[core]

    # 3. 归一化匹配 model_abbr_name
    name_norm = _normalize_name(model_name) if model_name else ""
    for code, m in dl_models.items():
        abbr_norm = _normalize_name(m.get("model_abbr_name", ""))
        if name_norm and abbr_norm == name_norm:
            return m
        # 4. model_code 包含 model_id 或 model_id 包含 model_code
        if mid_norm and (mid_norm in code or code in mid_norm):
            return m

    return None


# ── 主同步入口 ───────────────────────────────────────────────────────────
def run_datalearner_sync(verbose: bool = True) -> dict:
    """
    从 Datalearner 获取未覆盖模型的上下文数据并写入 FMH 数据库。

    返回统计 dict。
    """
    start = time.time()
    stats = {
        "total_uncovered": 0,
        "fetched_from_datalearner": 0,
        "updated_models": 0,
        "context_filled": 0,
        "max_tokens_filled": 0,
        "not_found": 0,
        "errors": 0,
        "rejected": 0,          # 校验不通过而被拒绝写入的值
        "used_known_fallback": 0,  # 不合理值回退到 KNOWN_CONTEXTS 的次数
    }

    # 1. 获取 FMH 未覆盖模型
    uncovered = get_uncovered_models()
    stats["total_uncovered"] = len(uncovered)
    if not uncovered:
        stats["message"] = "没有未覆盖的模型"
        return stats

    logger.info(f"未覆盖模型: {len(uncovered)} 个")

    # 2. 获取 Datalearner 所有模型
    logger.info("正在获取 Datalearner 模型列表...")
    dl_models = fetch_all_datalearner_models()
    stats["datalearner_total"] = len(dl_models)
    logger.info(f"Datalearner 模型: {len(dl_models)} 个")

    # 3. 逐模型匹配并获取详情
    for m in uncovered:
        provider_slug = m["provider_slug"]
        model_id = m["model_id"]
        model_name = m.get("name")

        # 匹配 Datalearner 模型
        dl_model = _find_datalearner_model(model_id, model_name, dl_models)

        if not dl_model:
            stats["not_found"] += 1
            continue

        # 获取详情页
        code = dl_model["model_code"]
        try:
            rsc = get_rsc_text(DATALEARNER_DETAIL_URL.format(code=code))
            context_display, max_output_display = extract_context_from_detail(rsc)

            context = parse_token_value(context_display)
            max_tokens = parse_token_value(max_output_display)

            if context is None and max_tokens is None:
                stats["not_found"] += 1
                continue

            # ── 合理性校验 ──
            # 1) max_tokens 不合理 → 置 None（不写入坏值）
            if not is_reasonable_max_tokens(max_tokens):
                stats["rejected"] += 1
                if verbose:
                    logger.info(f"  {provider_slug}/{model_id} 拒绝不合理 max_tokens={max_tokens}")
                max_tokens = None

            # 2) context 不合理 → 尝试 KNOWN_CONTEXTS 兜底；仍无效则置 None
            if not is_reasonable_context(context, max_tokens):
                known = KNOWN_CONTEXTS.get(model_id.lower())
                if known is not None and is_reasonable_context(known, max_tokens):
                    stats["used_known_fallback"] += 1
                    if verbose:
                        logger.info(f"  {provider_slug}/{model_id} context={context} 不合理，回退 KNOWN_CONTEXTS={known}")
                    context = known
                else:
                    stats["rejected"] += 1
                    if verbose:
                        logger.info(f"  {provider_slug}/{model_id} 拒绝不合理 context={context}")
                    context = None

            if context is None and max_tokens is None:
                stats["not_found"] += 1
                continue

            # 写入数据库
            if update_model_context(provider_slug, model_id, context=context, max_tokens=max_tokens):
                stats["updated_models"] += 1
                if context is not None:
                    stats["context_filled"] += 1
                if max_tokens is not None:
                    stats["max_tokens_filled"] += 1
                stats["fetched_from_datalearner"] += 1
                if verbose:
                    logger.info(f"  更新 {provider_slug}/{model_id}: context={context}, max_tokens={max_tokens}")

        except Exception as e:
            stats["errors"] += 1
            logger.warning(f"  {provider_slug}/{model_id} 获取失败: {e}")

    stats["duration_seconds"] = round(time.time() - start, 2)

    if verbose:
        logger.info(
            f"Datalearner 同步完成: 未覆盖 {stats['total_uncovered']}, "
            f"更新 {stats['updated_models']}, 未找到 {stats['not_found']}, "
            f"错误 {stats['errors']}, 耗时 {stats['duration_seconds']}s"
        )

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_datalearner_sync()
    print(json.dumps(result, ensure_ascii=False, indent=2))

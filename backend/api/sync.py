from fastapi import APIRouter
from typing import Dict, Any
import os
import json
import yaml
import shutil
import glob
from datetime import datetime

from .hermes_config_export import hermes_providers_config
from config import (
    HERMES_CONFIG_PATH,
    OPENCLAW_CONFIG_PATH,
    HERMES_DESKTOP_CONFIG_PATH,
)

__dict_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))

router = APIRouter(prefix="/api/sync", tags=["sync"])

# 别名保持函数内可读（原代码大量引用 HERMES_PATH / OPENCLAW_PATH）
HERMES_PATH = HERMES_CONFIG_PATH
OPENCLAW_PATH = OPENCLAW_CONFIG_PATH
HERMES_DESKTOP_PATH = HERMES_DESKTOP_CONFIG_PATH

SCRAPER_META = {
    "ag": ("AGNES_API_KEY", "Agnes AI"),
    "ce": ("CEREBRAS_API_KEY", "Cerebras"),
    "gr": ("GROQ_API_KEY", "Groq"),
    "mo": ("MOLLINATIONS_API_KEY", "Mollinations.ai"),
    "nv": ("NVIDIA_API_KEY", "NVIDIA"),
    "xa": ("XAI_API_KEY", "X.ai"),
    "se": ("SENSENOVA_API_KEY", "商汤日日新"),
    "al": ("ALIBABA_BAILIAN_API_KEY", "阿里云百炼"),
}

def _find_key_env(name: str) -> str:
    for env, display_name in SCRAPER_META.values():
        if name.lower() == display_name.lower() or name.lower() in display_name.lower():
            return env
    name_lower = name.lower()
    if "agnes" in name_lower:
        return "AGNES_API_KEY"
    if "cerebras" in name_lower:
        return "CEREBRAS_API_KEY"
    if "groq" in name_lower:
        return "GROQ_API_KEY"
    if "mollin" in name_lower or "pollin" in name_lower:
        return "MOLLINATIONS_API_KEY"
    if "nvidia" in name_lower:
        return "NVIDIA_API_KEY"
    if "x.ai" in name_lower or "xai" in name_lower:
        return "XAI_API_KEY"
    if "sensenova" in name_lower or "商汤" in name_lower:
        return "SENSENOVA_API_KEY"
    if "alibaba" in name_lower or "bailian" in name_lower or "阿里云" in name_lower or "百炼" in name_lower:
        return "ALIBABA_BAILIAN_API_KEY"
    return ""

def backup_file(filepath: str, keep: int = 5):
    """备份文件并自动轮换，只保留最近 keep 份备份。"""
    if not os.path.exists(filepath):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath + f".bak.{timestamp}"
    shutil.copy2(filepath, backup_path)
    
    # 轮换：只保留最近 keep 份
    parent_dir = os.path.dirname(filepath) or "."
    basename = os.path.basename(filepath)
    pattern = os.path.join(parent_dir, basename + ".bak.*")
    backups = glob.glob(pattern)
    # 按修改时间降序（最新在前）
    backups.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    for old in backups[keep:]:
        try:
            os.remove(old)
            print(f"  [清理旧备份] {os.path.basename(old)}")
        except Exception as e:
            print(f"  [清理失败] {os.path.basename(old)}: {e}")

async def sync_to_clients() -> dict:
    """同步 FMH provider/模型配置到 Hermes CLI、Hermes Desktop、OpenClaw。

    两个入口复用本函数：
      - POST /api/sync/clients（手动同步，见文件尾部端点）
      - scheduler 周日 weekly_test_and_sync_job（自动同步）
    返回结果 dict（success / 各客户端是否更新 / 配置文件路径）。
    """
    try:
        # 1. 获取最新配置数据
        data = await hermes_providers_config(format="json", include_public=True, include_models=True)
        providers = data.get("providers", [])
        
        # 2. 同步到 Hermes Agent (与 Desktop 相同的 yaml 安全逻辑)
        #    修复：原实现用正则整体替换 custom_providers 块，不写 key_env
        #    （同步后 provider 无密钥绑定），且会删掉用户自定义的非 FMH
        #    providers（omniRoute/CPAMC/ds2api 等）。改为 yaml 读写 + 保留逻辑。
        hermes_updated = False
        if os.path.exists(HERMES_PATH):
            try:
                backup_file(HERMES_PATH)
                with open(HERMES_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}

                old_custom = config.get("custom_providers", [])
                if old_custom is None:
                    old_custom = []

                new_custom = []
                for p in providers:
                    name = p.get("name", "").strip()
                    base_url = (p.get("base_url") or "").strip().rstrip("/")
                    if not name or not base_url:
                        continue

                    key_env = _find_key_env(name)
                    models = p.get("models", {})
                    model_ids = sorted(models.keys()) if isinstance(models, dict) else []

                    entry = {
                        "name": name,
                        "base_url": base_url,
                        "key_env": key_env,
                        "discover_models": False,
                    }
                    if model_ids:
                        entry["models"] = model_ids
                    if p.get("api_key"):
                        entry["api_key"] = p.get("api_key")

                    # 继承旧条目的 api_key / key_env（防止本地 provider 同步后丢密钥）
                    if not entry.get("api_key") or not entry.get("key_env"):
                        for cp in old_custom:
                            if isinstance(cp, dict) and str(cp.get("name", "")).strip().lower() == name.lower():
                                if not entry.get("api_key") and cp.get("api_key"):
                                    entry["api_key"] = cp["api_key"]
                                if not entry.get("key_env") and cp.get("key_env"):
                                    entry["key_env"] = cp["key_env"]
                                break

                    new_custom.append(entry)
                    print(f"  [+] Hermes Agent: {name}: {len(model_ids)} models, key_env={key_env}")

                # 保留非 FMH 的自定义 providers（防止 omniRoute/CPAMC/ds2api 被删）
                fmh_names_lower = {p.get("name", "").strip().lower() for p in providers}
                preserved = []
                for cp in old_custom:
                    if not isinstance(cp, dict):
                        preserved.append(cp)
                        continue
                    cp_name = str(cp.get("name", "")).strip().lower()
                    if cp_name in fmh_names_lower:
                        continue
                    preserved.append(cp)

                if preserved:
                    print(f"  [+] Hermes Agent: 保留 {len(preserved)} 个非 FMH 自定义 providers")
                config["custom_providers"] = new_custom + preserved

                with open(HERMES_PATH, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
                hermes_updated = True
            except Exception as e:
                print(f"Error syncing to Hermes Agent: {e}")


        # 3. 读取 FMH 数据库中的 context/max_tokens 映射（用于同步到客户端）
        #    结构: { provider_slug: { model_id: {"context_window": ..., "max_tokens": ...} } }
        ctx_model_map = {}
        # provider 显示名 → FMH slug 映射（OpenClaw / Hermes Desktop 共用）。
        # 缺失映射会回退成 name.lower()，产生中文/带点 slug（如 智谱_ai、agnes.com），
        # 导致上下文注入失败、图标失效、且清理逻辑无法删除残留 key。
        name_to_slug = {
            "9router": "9router", "Agnes AI": "agnes", "Agnes.com": "agnes_com",
            "Aliyun Bailian": "alibaba_bailian", "Cerebras": "cerebras", "Cohere": "cohere",
            "Gemini": "gemini", "GitHub Models": "github_models", "Grok": "grok",
            "Groq": "groq", "Manifest-1111": "manifest_1111", "MiniMax": "minimax",
            "Mollinations.ai": "mollinations", "NVIDIA": "nvidia", "NotDiamond": "notdiamond",
            "Novita AI": "novity", "OpenRouter": "openrouter", "SenseNova": "sensenova",
            "X.ai": "xai", "Zen API": "zen", "CPAMC": "cpamc", "cpamc": "cpamc",
            "智谱 AI": "zhipu", "超算": "scnet",
        }
        try:
            from database import get_connection
            with get_connection() as conn:
                conn.row_factory = __dict_factory
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.slug AS provider_slug, m.model_id, m.context_window, m.max_tokens
                    FROM models m JOIN providers p ON m.provider_id = p.id
                """)
                for r in cur.fetchall():
                    ctx_model_map.setdefault(r["provider_slug"], {})[r["model_id"]] = {
                        "context_window": r.get("context_window"),
                        "max_tokens": r.get("max_tokens"),
                    }
        except Exception as e:
            print(f"Warning: 读取模型 context/max_tokens 失败: {e}")

        # 4. 同步到 OpenClaw
        oc_updated = False
        if os.path.exists(OPENCLAW_PATH):
            with open(OPENCLAW_PATH, "r", encoding="utf-8") as f:
                oc = json.load(f)

            oc_providers = oc.setdefault("models", {}).setdefault("providers", {})
            defaults_models = oc.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})

            # 历史错误 slug 迁移：旧版本 name_to_slug 缺失时回退生成的 key
            # （如 智谱_ai、超算、agnes.com、manifest-1111）统一归一到正确 slug，
            # 并迁移 agents.defaults.models 中的 full_id 前缀。只动 FMH 管理范围。
            LEGACY_SLUGS = {
                "智谱_ai": "zhipu",
                "超算": "scnet",
                "agnes.cn": "agnes_com",
                "agnes.com": "agnes_com",
                "manifest-1111": "manifest_1111",
            }
            fmh_possible_slugs = set(name_to_slug.values())
            for legacy, target in LEGACY_SLUGS.items():
                if legacy == target:
                    continue
                if legacy not in oc_providers or target not in fmh_possible_slugs:
                    continue
                if target in oc_providers:
                    del oc_providers[legacy]
                else:
                    oc_providers[target] = oc_providers.pop(legacy)
                legacy_keys = [k for k in list(defaults_models.keys()) if k.startswith(legacy + "/")]
                for k in legacy_keys:
                    defaults_models[target + k[len(legacy):]] = defaults_models.pop(k)

            # Emoji 图标映射：OpenClaw 模型名统一 "emoji [提供商slug] ID" 前缀。
            # 每个 FMH provider slug 对应一个稳定 emoji；未列的用 📦 兜底。
            icon_map = {
                "alibaba_bailian": "☁️",
                "openrouter": "🌌",
                "zen": "🧘",
                "nvidia": "👁️",
                "sensenova": "🌟",
                "xai": "✖️",
                "groq": "⚡",
                "cerebras": "🧠",
                "agnes": "👧",
                "mollinations": "🌸",
                "9router": "🧭",
                "cohere": "⌨️",
                "gemini": "🌈",
                "github_models": "🐙",
                "grok": "✖️",
                "minimax": "Ⓜ️",
                "notdiamond": "💎",
                "novity": "🛸",
                "cpamc": "🏢",        # 企业级中转商
                "google": "🔍",       # Google 官方
                "anthropic": "🧠",
                "openai": "✨",
                "agnes_com": "👧",
                "agnes.com": "👧",   # name_to_slug 回退生成带点 slug 时的兜底
                "blazeai": "🔥",
                "chat2api": "💬",
                "manifest": "📜",
                "manifest_1111": "📜",
                "modelscope": "🌊",
                "nararouter": "🧭",
                "omniroute": "🧭",
                "opencode": "⚙️",
                "step": "🪜",
                "webai2api": "🕸️",
                "kilo": "🛢️",
                "scnet": "🖥️",
                "ds2api": "🔄",
                "ds2api_vercel": "▲",
                "zhipu": "🔮",
            }

            valid_slugs = []
            valid_model_ids: dict[str, set] = {}  # 本次每个 slug 的模型集合，用于逐模型清理

            for p in providers:
                name = p.get("name", "")
                slug = name_to_slug.get(name, name.lower().replace(" ", "_"))
                valid_slugs.append(slug)
                
                base_url = p.get("base_url", "")
                api_key = p.get("api_key", "")
                models_dict = p.get("models", {})

                oc_models = []
                for mid, minfo in models_dict.items():
                    # 统一命名格式：[emoji] [提供商slug] ID
                    # （不保留旧名，保证所有模型命名一致）
                    icon = icon_map.get(slug, "📦")
                    m_name = f"{icon} [{slug}] {mid}"

                    m_entry = {"id": mid, "name": m_name}

                    # 从 FMH 数据库注入 contextWindow / maxTokens（真实值）
                    ctx_info = ctx_model_map.get(slug, {}).get(mid, {})
                    ctx_val = ctx_info.get("context_window")
                    mt_val = ctx_info.get("max_tokens")

                    # 兜底：minfo 中带 context_length 时使用
                    if ctx_val is None and isinstance(minfo, dict) and "context_length" in minfo:
                        try:
                            ctx_val = int(minfo["context_length"])
                        except (ValueError, TypeError):
                            ctx_val = None

                    if ctx_val is not None:
                        try:
                            m_entry["contextWindow"] = int(str(ctx_val).replace(",", "").strip())
                        except (ValueError, TypeError):
                            pass
                    if mt_val is not None:
                        try:
                            m_entry["maxTokens"] = int(mt_val)
                        except (ValueError, TypeError):
                            pass
                    oc_models.append(m_entry)
                    valid_model_ids.setdefault(slug, set()).add(mid)

                    # 注册到 agents.defaults.models 中，使其显示在 Web UI 列表
                    full_id = f"{slug}/{mid}"
                    if full_id not in defaults_models:
                        defaults_models[full_id] = {}

                if slug in oc_providers:
                    existing = oc_providers[slug]
                    existing["models"] = oc_models
                    if not existing.get("baseUrl"):
                        existing["baseUrl"] = base_url
                    if not existing.get("apiKey") and api_key:
                        existing["apiKey"] = api_key
                    existing["api"] = "openai-completions"
                else:
                    entry = {
                        "api": "openai-completions",
                        "baseUrl": base_url,
                        "models": oc_models,
                    }
                    if api_key:
                        entry["apiKey"] = api_key
                    oc_providers[slug] = entry

            # 清理 FMH 管理范围内的过期内容（仅限 FMH slug，不碰用户自建渠道）：
            #   1) 整个 provider 已从 FMH 消失/隐藏 → 删除 provider 条目
            #   2) 单个模型已从 provider 移除或 user_removed → 删除 defaults.models 条目
            to_delete = [slug for slug in oc_providers.keys()
                         if slug in fmh_possible_slugs and slug not in valid_slugs]
            for slug in to_delete:
                del oc_providers[slug]

            for full_id in list(defaults_models.keys()):
                if "/" not in full_id:
                    continue
                mslug, mid = full_id.split("/", 1)
                if mslug not in fmh_possible_slugs:
                    continue  # 非 FMH 渠道不动
                if mslug in to_delete or mslug not in valid_slugs:
                    del defaults_models[full_id]
                elif mid not in valid_model_ids.get(mslug, set()):
                    del defaults_models[full_id]

            with open(OPENCLAW_PATH, "w", encoding="utf-8") as f:
                json.dump(oc, f, indent=2, ensure_ascii=False)
            oc_updated = True

        # 4. 同步到 Hermes Desktop
        hermes_desktop_updated = False
        if os.path.exists(HERMES_DESKTOP_PATH):
            try:
                backup_file(HERMES_DESKTOP_PATH)
                with open(HERMES_DESKTOP_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}

                old_custom = config.get("custom_providers", [])
                if old_custom is None:
                    old_custom = []

                new_custom = []
                for p in providers:
                    name = p.get("name", "").strip()
                    base_url = (p.get("base_url") or "").strip().rstrip("/")
                    if not name or not base_url:
                        continue
                    
                    key_env = _find_key_env(name)
                    models = p.get("models", {})
                    model_ids = sorted(models.keys()) if isinstance(models, dict) else []

                    # Hermes Desktop 版本支持带 context_length 的 models 字典。
                    # 为了兼容旧版（仅字符串数组），如果所有模型都有上下文数据则写字典；
                    # 否则退回字符串数组，避免破坏旧配置。
                    slug_lower = name.lower().replace(" ", "_")
                    deskmodel_map = ctx_model_map.get(slug_lower, {})
                    if not deskmodel_map:
                        # 尝试通过 name_to_slug 得到 slug
                        deskmodel_map = ctx_model_map.get(
                            name_to_slug.get(name, ""),
                            {},
                        )

                    model_configs = {}
                    for mid in model_ids:
                        mi = deskmodel_map.get(mid, {})
                        sub = {}
                        if mi.get("context_window"):
                            try:
                                sub["context_length"] = int(str(mi["context_window"]).replace(",", "").strip())
                            except (ValueError, TypeError):
                                pass
                        if mi.get("max_tokens") is not None:
                            sub["max_tokens"] = mi["max_tokens"]
                        if sub:
                            model_configs[mid] = sub

                    entry = {
                        "name": name,
                        "base_url": base_url,
                        "key_env": key_env,
                        "discover_models": False,
                    }
                    if model_ids:
                        # Hermes Desktop 支持 models 为 dict {id: {context_length}}
                        if len(model_configs) == len(model_ids):
                            entry["models"] = model_configs
                        else:
                            entry["models"] = model_ids
                        # 若部分有数据，用字典；保留上下文信息最大化
                        if model_configs:
                            entry["models"] = model_configs
                    if p.get("api_key"):
                        entry["api_key"] = p.get("api_key")

                    # 继承旧条目的 api_key / key_env：FMH 数据库没有 key 的 provider
                    # （如本地 omniRoute/CPAMC/ds2api）同步后会丢失用户已配置的密钥，
                    # 从旧配置中同名条目补回。
                    if not entry.get("api_key") or not entry.get("key_env"):
                        for cp in old_custom:
                            if isinstance(cp, dict) and str(cp.get("name", "")).strip().lower() == name.lower():
                                if not entry.get("api_key") and cp.get("api_key"):
                                    entry["api_key"] = cp["api_key"]
                                if not entry.get("key_env") and cp.get("key_env"):
                                    entry["key_env"] = cp["key_env"]
                                break

                    new_custom.append(entry)

                # 保留非 FMH 自定义 providers
                fmh_names_lower = {p.get("name", "").strip().lower() for p in providers}
                fmh_key_envs = {_find_key_env(p.get("name", "")) for p in providers}
                fmh_key_envs = {k for k in fmh_key_envs if k}

                preserved = []
                for cp in old_custom:
                    if not isinstance(cp, dict):
                        preserved.append(cp)
                        continue
                    cp_name = str(cp.get("name", "")).strip().lower()
                    if cp_name in fmh_names_lower:
                        continue
                    cp_key_env = str(cp.get("key_env", "")).strip().upper()
                    if cp_key_env in fmh_key_envs and cp_key_env:
                        continue
                    preserved.append(cp)

                config["custom_providers"] = new_custom + preserved

                with open(HERMES_DESKTOP_PATH, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
                hermes_desktop_updated = True
            except Exception as e:
                print(f"Error syncing to Hermes Desktop: {e}")

        return {
            "success": True,
            "message": f"Successfully synced {len(providers)} providers to 3 clients.",
            "hermes_updated": hermes_updated,
            "hermes_path": HERMES_PATH,
            "hermes_desktop_updated": hermes_desktop_updated,
            "hermes_desktop_path": HERMES_DESKTOP_PATH,
            "openclaw_updated": oc_updated,
            "openclaw_path": OPENCLAW_PATH
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}"
        }


@router.post("/clients")
async def sync_clients():
    """POST /api/sync/clients — 手动触发同步到客户端（复用 sync_to_clients）"""
    return await sync_to_clients()

"""
⚠️ 已废弃 (DEPRECATED) —— 请勿再调用本模块的同步函数。

同步逻辑已统一到 backend/api/sync.py 的 sync_to_clients()：
  - 手动同步：POST /api/sync/clients
  - 自动同步：scheduler.py 的 weekly_test_and_sync_job（已改为调用新实现）

本文件保留仅作历史参考（差异点：不过滤 user_removed、无 FROZEN_BASE_URLS 兜底、
写入 Hermes 旧 providers: 格式、会 subprocess 调用外部 rename_models.py），
确认无引用后可安全删除。
"""

import os
import json
import yaml
import shutil
import glob
from datetime import datetime
from pathlib import Path
import logging

# Ensure we can import from backend
import sys
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import get_connection
from scrapers import get_all_scrapers
from config import (
    get_api_key_for_slug,
    HERMES_CONFIG_PATH as _HERMES_STR,
    OPENCLAW_CONFIG_PATH as _OPENCLAW_STR,
    HERMES_DESKTOP_CONFIG_PATH as _HERMES_DESKTOP_STR,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# sync_configs 内部使用 Path 对象，从 config 的 str 值转换
HERMES_CONFIG_PATH = Path(_HERMES_STR)
OPENCLAW_CONFIG_PATH = Path(_OPENCLAW_STR)
HERMES_DESKTOP_CONFIG_PATH = Path(_HERMES_DESKTOP_STR)

SCRAPER_META = {
    "ag": ("AGNES_API_KEY", "Agnes AI"),
    "ce": ("CEREBRAS_API_KEY", "Cerebras"),
    "gr": ("GROQ_API_KEY", "Groq"),
    "mo": ("MOLLINATIONS_API_KEY", "Mollinations.ai"),
    "nv": ("NVIDIA_API_KEY", "NVIDIA"),
    "xa": ("XAI_API_KEY", "X.ai"),
    "se": ("SENSENOVA_API_KEY", "商汤日日新"),
    "al": ("ALIBABA_BAILIAN_API_KEY", "阿里云百炼"),
    "ma": ("MANIFEST_API_KEY", "Manifest"),
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
    if "manifest" in name_lower:
        return "MANIFEST_API_KEY"
    return ""

def sync_hermes_desktop(providers_data):
    if not HERMES_DESKTOP_CONFIG_PATH.exists():
        logger.warning(f"Hermes Desktop config not found at {HERMES_DESKTOP_CONFIG_PATH}")
        return

    backup_file(HERMES_DESKTOP_CONFIG_PATH)

    try:
        with open(HERMES_DESKTOP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse Hermes Desktop YAML: {e}")
        return

    old_custom = config.get("custom_providers", [])
    if old_custom is None:
        old_custom = []

    new_custom = []
    for slug, data in providers_data.items():
        name = data["name"].strip()
        base_url = data["base_url"].strip().rstrip("/")
        if not name or not base_url:
            continue
        
        key_env = _find_key_env(name)
        model_ids = [m["id"] for m in data["models"]]
        
        entry = {
            "name": name,
            "base_url": base_url,
            "key_env": key_env,
            "discover_models": False,
        }
        if model_ids:
            entry["models"] = model_ids
        
        new_custom.append(entry)

    # 保留非 FMH 自定义 providers
    fmh_names_lower = {data["name"].strip().lower() for data in providers_data.values()}
    fmh_key_envs = {_find_key_env(data["name"]) for data in providers_data.values()}
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

    with open(HERMES_DESKTOP_CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
    
    logger.info("Hermes Desktop config updated successfully.")

def backup_file(filepath: Path, keep: int = 5):
    """备份文件并自动轮换，只保留最近 keep 份备份（与 api/sync.py 同规则）。"""
    if not filepath.exists():
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_suffix(f"{filepath.suffix}.bak.{timestamp}")
    shutil.copy2(filepath, backup_path)
    logger.info(f"Backed up {filepath.name} to {backup_path.name}")

    # 轮换：只保留最近 keep 份
    parent_dir = filepath.parent
    basename = filepath.name
    pattern = str(parent_dir / f"{basename}.bak.*")
    backups = glob.glob(pattern)
    # 按修改时间降序（最新在前）
    backups.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    for old in backups[keep:]:
        try:
            os.remove(old)
            logger.info(f"  清理旧备份: {os.path.basename(old)}")
        except Exception as e:
            logger.warning(f"  清理失败 {os.path.basename(old)}: {e}")

def get_providers_data():
    """从数据库和爬虫配置中获取要同步的免费模型信息"""
    scrapers = get_all_scrapers()
    scraper_endpoints = {}
    for slug, scraper_cls in scrapers.items():
        inst = scraper_cls()
        ep = {}
        if inst.chat_endpoint_base:
            ep["base_url"] = inst.chat_endpoint_base.rstrip("/")
        if inst.chat_api_key:
            ep["has_hardcoded_key"] = True
        if ep:
            scraper_endpoints[slug] = ep

    providers_data = {}
    with get_connection() as conn:
        conn.row_factory = dict
        cursor = conn.cursor()
        
        # We need a custom dict factory since sqlite3.Row isn't exactly dict
        def dict_factory(cursor, row):
            return dict(zip([col[0] for col in cursor.description], row))
        conn.row_factory = dict_factory
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, slug
            FROM providers
            WHERE (hidden IS NULL OR hidden = 0)
              AND (is_active IS NULL OR is_active = 1)
        """)
        provider_rows = cursor.fetchall()

        for prow in provider_rows:
            slug = prow["slug"]
            ep_info = scraper_endpoints.get(slug, {})
            base_url = ep_info.get("base_url", "")
            if not base_url:
                continue

            api_key = ""
            if ep_info.get("has_hardcoded_key"):
                inst = scrapers[slug]()
                api_key = inst.chat_api_key or ""
            if not api_key:
                api_key = get_api_key_for_slug(slug)

            # 查询所有相关的模型
            cursor.execute("""
                SELECT model_id, name, context_window
                FROM models
                WHERE provider_id = ?
                ORDER BY name
            """, (prow["id"],))
            model_rows = cursor.fetchall()

            if not model_rows:
                continue

            models = []
            for mrow in model_rows:
                ctx = mrow["context_window"]
                ctx_int = 131072 # 默认 128k
                if ctx:
                    try:
                        ctx_int = int(ctx)
                    except ValueError:
                        pass
                
                models.append({
                    "id": mrow["model_id"],
                    "name": mrow["name"] or mrow["model_id"],
                    "context_length": ctx_int
                })

            if slug == "cerebras":
                extra_cerebras = [
                    {"id": "llama3.1-8b", "name": "llama3.1-8b", "context_length": 131072},
                    {"id": "qwen-3-235b-a22b-instruct-2507", "name": "qwen-3-235b-a22b-instruct-2507", "context_length": 131072},
                    {"id": "zai-glm-4.7", "name": "zai-glm-4.7", "context_length": 131072}
                ]
                for em in extra_cerebras:
                    if not any(m["id"] == em["id"] for m in models):
                        models.append(em)

            providers_data[slug] = {
                "name": prow["name"] or slug,
                "base_url": base_url,
                "api_key": api_key,
                "models": models
            }

    return providers_data

def sync_hermes(providers_data):
    if not HERMES_CONFIG_PATH.exists():
        logger.warning(f"Hermes config not found at {HERMES_CONFIG_PATH}")
        return

    backup_file(HERMES_CONFIG_PATH)

    try:
        with open(HERMES_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse Hermes YAML: {e}")
        return

    if 'providers' not in config:
        config['providers'] = {}

    for slug, data in providers_data.items():
        # Hermes 格式
        provider_key = data["name"] # Hermes里有时候用name当key，为了兼容最好统一
        
        # 构建 models 字典
        models_dict = {}
        for m in data["models"]:
            models_dict[m["id"]] = {"context_length": m["context_length"]}

        config['providers'][slug] = {
            "base_url": data["base_url"],
            "api_key": data["api_key"] or "",
            "model": data["models"][0]["id"] if data["models"] else "",
            "models": models_dict
        }

    with open(HERMES_CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    logger.info(f"Hermes config updated successfully.")

def sync_openclaw(providers_data):
    if not OPENCLAW_CONFIG_PATH.exists():
        logger.warning(f"Openclaw config not found at {OPENCLAW_CONFIG_PATH}")
        return

    backup_file(OPENCLAW_CONFIG_PATH)

    try:
        with open(OPENCLAW_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Openclaw JSON: {e}")
        return

    if 'models' not in config:
        config['models'] = {}
    if 'providers' not in config['models']:
        config['models']['providers'] = {}

    oc_providers = config['models']['providers']

    name_to_slug = {
        "9router": "9router", "Agnes AI": "agnes", "Aliyun Bailian": "alibaba_bailian",
        "Cerebras": "cerebras", "Cohere": "cohere",
        "Gemini": "gemini", "GitHub Models": "github_models", "Grok": "grok",
        "Groq": "groq", "MiniMax": "minimax", "Mollinations.ai": "mollinations",
        "NVIDIA": "nvidia", "NotDiamond": "notdiamond", "Novita AI": "novity",
        "OpenRouter": "openrouter", "SenseNova": "sensenova", "X.ai": "xai",
        "Zen API": "zen", "OmniRoute": "omniroute", "omniroute": "omniroute",
        "CPAMC": "cpamc", "cpamc": "cpamc", "Manifest": "manifest",
    }

    icon_map = {
        "alibaba_bailian": "☁️", "openrouter": "🌌", "zen": "🧘", "nvidia": "👁️",
        "sensenova": "🌟", "xai": "✖️", "groq": "⚡", "cerebras": "🧠",
        "agnes": "👧", "mollinations": "🌸", "9router": "🧭", "cohere": "⌨️",
        "gemini": "🔮", "github_models": "🐙", "grok": "✖️", "minimax": "Ⓜ️",
        "notdiamond": "💎", "novity": "🛸", "cpamc": "🏢", "google": "🔍",
        "anthropic": "🧠", "openai": "✨", "omniroute": "🧭",
        "anyrouter": "🔀", "opencode": "💻", "zhipu": "💡", "blazeai": "🔥",
        "manifest": "📝",
    }

    valid_slugs = []
    for slug, data in providers_data.items():
        mapped_slug = name_to_slug.get(data["name"], slug)
        valid_slugs.append(mapped_slug)

        existing_provider = oc_providers.get(mapped_slug, {})
        existing_models_map = {m["id"]: m.get("name", m["id"]) for m in existing_provider.get("models", [])}

        oc_models = []
        for m in data["models"]:
            mid = m["id"]
            
            # 净化或重新生成模型的显示名称，剥除 omniroute/ 前缀，确保符合 emoji [provider] ID 格式
            need_rebuild = True
            if mid in existing_models_map:
                m_name = existing_models_map[mid]
                # 检查是否已符合格式且不含多余的前缀
                import re
                if "omniRoute/" not in m_name and re.match(r'^[^\x00-\x7f]\ufe0f?\s*\[[^\]]+\]\s+', m_name):
                    need_rebuild = False
            
            if need_rebuild:
                icon = icon_map.get(mapped_slug, "📦")
                # 剥除原名字或 ID 中的 omniroute/ 前缀，再生成干净 of name
                raw_name = existing_models_map.get(mid, mid)
                # 稳健剥除 omniroute/ (不区分大小写)
                import re
                cleaned_name = re.sub(r'^(omniroute)/', '', raw_name, flags=re.IGNORECASE)
                # 稳健剥除已存在的 emoji+provider 格式前缀，拿到最基础的模型名
                prefix_re = re.compile(r'^[^\S\r\n]*([^\x00-\x7f]\ufe0f?)\s*\[[^\]]+\]\s+')
                while True:
                    match_pref = prefix_re.match(cleaned_name)
                    if not match_pref:
                        break
                    cleaned_name = cleaned_name[match_pref.end():]
                cleaned_name = re.sub(r'^(omniroute)/', '', cleaned_name, flags=re.IGNORECASE)
                m_name = f"{icon} [{mapped_slug}] {cleaned_name}"
            else:
                m_name = existing_models_map[mid]

            m_entry = {
                "contextWindow": m["context_length"],
                "id": mid,
                "input": ["text"],
                "maxTokens": 8192,
                "name": m_name
            }
            oc_models.append(m_entry)

            # 注册到 agents.defaults.models 中，使其显示在 Web UI 列表
            full_id = f"{mapped_slug}/{mid}"
            if "agents" not in config:
                config["agents"] = {}
            if "defaults" not in config["agents"]:
                config["agents"]["defaults"] = {}
            if "models" not in config["agents"]["defaults"]:
                config["agents"]["defaults"]["models"] = {}
            if full_id not in config["agents"]["defaults"]["models"]:
                config["agents"]["defaults"]["models"][full_id] = {}

        if mapped_slug in oc_providers:
            existing = oc_providers[mapped_slug]
            existing["models"] = oc_models
            if not existing.get("baseUrl"):
                existing["baseUrl"] = data["base_url"]
            if not existing.get("apiKey") and data["api_key"]:
                existing["apiKey"] = data["api_key"]
            existing["api"] = "openai-completions"
        else:
            entry = {
                "api": "openai-completions",
                "baseUrl": data["base_url"],
                "models": oc_models,
            }
            if data["api_key"]:
                entry["apiKey"] = data["api_key"]
            oc_providers[mapped_slug] = entry

    # 只清理 FMH 范围内且已被删除的提供商，不碰非 FMH 的个人渠道
    fmh_possible_slugs = set(name_to_slug.values())
    to_delete = [s for s in oc_providers.keys() if s in fmh_possible_slugs and s not in valid_slugs]
    for s in to_delete:
        del oc_providers[s]

    # 清理 agents.defaults.models
    if "agents" in config and "defaults" in config["agents"] and "models" in config["agents"]["defaults"]:
        defaults_models = config["agents"]["defaults"]["models"]
        keys_to_delete = []
        for full_id in defaults_models.keys():
            for s in to_delete:
                if full_id.startswith(f"{s}/"):
                    keys_to_delete.append(full_id)
                    break
        for k in keys_to_delete:
            del defaults_models[k]

    with open(OPENCLAW_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    logger.info("Openclaw config updated successfully with details and emojis.")

def sync_to_clients():
    logger.info("Fetching providers data from database...")
    providers_data = get_providers_data()
    if not providers_data:
        logger.warning("No providers or models found to sync.")
        return

    logger.info(f"Found {len(providers_data)} active providers with free models.")
    sync_hermes(providers_data)
    sync_hermes_desktop(providers_data)
    sync_openclaw(providers_data)
    logger.info("Sync to clients completed.")

    # 自动运行重命名脚本，确保格式一致
    import subprocess
    import sys
    try:
        rename_script = r"C:\Users\Administrator\.openclaw\rename_models.py"
        subprocess.run([sys.executable, rename_script], check=True)
        logger.info("Automatically executed rename_models.py successfully.")
    except Exception as e:
        logger.error(f"Failed to auto-run rename_models.py: {e}")

if __name__ == "__main__":
    sync_to_clients()

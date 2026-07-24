from fastapi import APIRouter
from typing import Dict, Any
import os
import re
import json
import yaml
import shutil
from datetime import datetime

from .hermes_config_export import hermes_providers_config

router = APIRouter(prefix="/api/sync", tags=["sync"])

HERMES_PATH = r"C:\Users\Administrator\.hermes\config.yaml"
OPENCLAW_PATH = r"C:\Users\Administrator\.openclaw\openclaw.json"
HERMES_DESKTOP_PATH = r"C:\Users\Administrator\AppData\Local\hermes\config.yaml"

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

def backup_file(filepath: str):
    if not os.path.exists(filepath):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath + f".bak.{timestamp}"
    shutil.copy2(filepath, backup_path)

@router.post("/clients")
async def sync_clients():
    try:
        # 1. 获取最新配置数据
        data = await hermes_providers_config(format="json", include_public=True, include_models=True)
        providers = data.get("providers", [])
        
        # 2. 同步到 Hermes (使用正则以保留注释)
        hermes_updated = False
        if os.path.exists(HERMES_PATH):
            yaml_lines = ["custom_providers:\n"]
            for p in providers:
                yaml_lines.append(f"- name: {p.get('name')}\n")
                yaml_lines.append(f"  base_url: {p.get('base_url')}\n")
                if p.get('api_key'):
                    yaml_lines.append(f"  api_key: {p.get('api_key')}\n")
                if p.get('model'):
                    yaml_lines.append(f"  model: {p.get('model')}\n")
                
                yaml_lines.append(f"  discover_models: false\n")
                
                models = p.get('models')
                if models and isinstance(models, dict):
                    yaml_lines.append(f"  models:\n")
                    for m_name, m_info in models.items():
                        yaml_lines.append(f"    {m_name}:\n")
                        if isinstance(m_info, dict) and 'context_length' in m_info:
                            yaml_lines.append(f"      context_length: {m_info['context_length']}\n")

            new_providers_block = "".join(yaml_lines)

            with open(HERMES_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            new_content = re.sub(
                r"^custom_providers:.*?(?=^platforms:|\Z)",
                new_providers_block,
                content,
                flags=re.MULTILINE | re.DOTALL
            )

            with open(HERMES_PATH, "w", encoding="utf-8") as f:
                f.write(new_content)
            hermes_updated = True
            
        # 3. 同步到 OpenClaw
        oc_updated = False
        if os.path.exists(OPENCLAW_PATH):
            with open(OPENCLAW_PATH, "r", encoding="utf-8") as f:
                oc = json.load(f)

            oc_providers = oc.setdefault("models", {}).setdefault("providers", {})
            name_to_slug = {
                "9router": "9router", "Agnes AI": "agnes", "Aliyun Bailian": "alibaba_bailian",
                "Cerebras": "cerebras", "Cohere": "cohere",
                "Gemini": "gemini", "GitHub Models": "github_models", "Grok": "grok",
                "Groq": "groq", "MiniMax": "minimax", "Mollinations.ai": "mollinations",
                "NVIDIA": "nvidia", "NotDiamond": "notdiamond", "Novita AI": "novity",
                "OpenRouter": "openrouter", "SenseNova": "sensenova", "X.ai": "xai",
                "Zen API": "zen", "CPAMC": "cpamc", "cpamc": "cpamc",
            }

            # Emoji 图标映射：所有模型名统一加 "emoji [provider] " 前缀
            # 已有模型的 name 会被保留不覆盖（见下面逻辑）；新加的模型用此映射生成 name
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
            }

            valid_slugs = []

            for p in providers:
                name = p.get("name", "")
                slug = name_to_slug.get(name, name.lower().replace(" ", "_"))
                valid_slugs.append(slug)
                
                base_url = p.get("base_url", "")
                api_key = p.get("api_key", "")
                models_dict = p.get("models", {})
                
                existing_provider = oc_providers.get(slug, {})
                existing_models_map = {m["id"]: m.get("name", m["id"]) for m in existing_provider.get("models", [])}
                
                oc_models = []
                for mid, minfo in models_dict.items():
                    if mid in existing_models_map:
                        m_name = existing_models_map[mid]
                    else:
                        icon = icon_map.get(slug, "📦")
                        m_name = f"{icon} [{slug}] {mid}"
                        
                    m_entry = {"id": mid, "name": m_name}
                    if isinstance(minfo, dict) and "context_length" in minfo:
                        try:
                            m_entry["contextWindow"] = int(minfo["context_length"])
                        except:
                            pass
                    oc_models.append(m_entry)
                    
                    # 注册到 agents.defaults.models 中，使其显示在 Web UI 列表
                    full_id = f"{slug}/{mid}"
                    if "agents" not in oc:
                        oc["agents"] = {}
                    if "defaults" not in oc["agents"]:
                        oc["agents"]["defaults"] = {}
                    if "models" not in oc["agents"]["defaults"]:
                        oc["agents"]["defaults"]["models"] = {}
                        
                    if full_id not in oc["agents"]["defaults"]["models"]:
                        oc["agents"]["defaults"]["models"][full_id] = {}
                    
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

            # 清理在 FMH 中已删除的提供商，仅限属于 FMH 的 slug，防止误删用户自定义的个人渠道
            fmh_possible_slugs = set(name_to_slug.values())
            to_delete = [slug for slug in oc_providers.keys() if slug in fmh_possible_slugs and slug not in valid_slugs]
            for slug in to_delete:
                del oc_providers[slug]
                
            # 清理 agents.defaults.models 中对应被删除提供商的模型
            if "agents" in oc and "defaults" in oc["agents"] and "models" in oc["agents"]["defaults"]:
                defaults_models = oc["agents"]["defaults"]["models"]
                keys_to_delete = []
                for full_id in defaults_models.keys():
                    # full_id 格式为 "slug/mid"
                    for slug in to_delete:
                        if full_id.startswith(f"{slug}/"):
                            keys_to_delete.append(full_id)
                            break
                for k in keys_to_delete:
                    del defaults_models[k]

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

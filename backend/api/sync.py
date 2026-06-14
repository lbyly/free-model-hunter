from fastapi import APIRouter
from typing import Dict, Any
import os
import re
import json

from .hermes_config_export import hermes_providers_config

router = APIRouter(prefix="/api/sync", tags=["sync"])

HERMES_PATH = r"C:\Users\Administrator\.hermes\config.yaml"
OPENCLAW_PATH = r"C:\Users\Administrator\.openclaw\openclaw.json"

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
                "Zen API": "zen",
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

            # 清理在 FMH 中已删除的提供商
            to_delete = [slug for slug in oc_providers.keys() if slug not in valid_slugs]
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

        return {
            "success": True,
            "message": f"Successfully synced {len(providers)} providers to clients.",
            "hermes_updated": hermes_updated,
            "hermes_path": HERMES_PATH,
            "openclaw_updated": oc_updated,
            "openclaw_path": OPENCLAW_PATH
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}"
        }

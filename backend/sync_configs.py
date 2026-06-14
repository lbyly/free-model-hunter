import os
import json
import yaml
import shutil
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
from config import get_api_key_for_slug

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HERMES_CONFIG_PATH = Path("C:/Users/Administrator/.hermes/config.yaml")
OPENCLAW_CONFIG_PATH = Path("C:/Users/Administrator/.openclaw/openclaw.json")

def backup_file(filepath: Path):
    if not filepath.exists():
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_suffix(f"{filepath.suffix}.bak.{timestamp}")
    shutil.copy2(filepath, backup_path)
    logger.info(f"Backed up {filepath.name} to {backup_path.name}")

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

            # 只查询免费模型
            cursor.execute("""
                SELECT model_id, name, context_window
                FROM models
                WHERE provider_id = ? AND is_free = 1
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

    for slug, data in providers_data.items():
        # Openclaw 格式
        models_list = []
        for m in data["models"]:
            models_list.append({
                "contextWindow": m["context_length"],
                "id": m["id"],
                "input": ["text"],
                "maxTokens": 8192,
                "name": m["name"]
            })

        config['models']['providers'][slug] = {
            "api": "openai-completions",
            "apiKey": data["api_key"] or "",
            "baseUrl": data["base_url"],
            "models": models_list
        }

    with open(OPENCLAW_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Openclaw config updated successfully.")

def sync_to_clients():
    logger.info("Fetching providers data from database...")
    providers_data = get_providers_data()
    if not providers_data:
        logger.warning("No providers or models found to sync.")
        return

    logger.info(f"Found {len(providers_data)} active providers with free models.")
    sync_hermes(providers_data)
    sync_openclaw(providers_data)
    logger.info("Sync to clients completed.")

if __name__ == "__main__":
    sync_to_clients()

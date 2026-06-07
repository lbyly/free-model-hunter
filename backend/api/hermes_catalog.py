"""
Hermes Model Catalog API 端点

提供符合 Hermes model_catalog 规范的 JSON manifest，
使 Hermes 可以通过 model_catalog.url 直接消费 Free-Model-Hub 的模型数据。

规范: https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from database import get_connection
from scrapers import get_all_scrapers, get_scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


@router.get("/catalog")
async def hermes_catalog():
    """
    返回 Hermes 兼容的 model catalog JSON manifest。

    格式:
    {
        "version": 1,
        "updated_at": "ISO8601",
        "metadata": { ... },
        "providers": {
            "<provider_slug>": {
                "metadata": { "display_name": "...", "base_url": "..." },
                "models": [
                    { "id": "<model_id>", "description": "..." },
                    ...
                ]
            }
        }
    }
    """
    # 收集所有活跃爬虫的 endpoint 配置
    scrapers = get_all_scrapers()
    scraper_endpoints: dict[str, dict] = {}
    for slug, scraper_cls in scrapers.items():
        inst = scraper_cls()
        endpoint_info = {}
        if inst.chat_endpoint_base:
            endpoint_info["base_url"] = inst.chat_endpoint_base.rstrip("/")
        if inst.chat_endpoint_template:
            endpoint_info["endpoint_template"] = inst.chat_endpoint_template
        if inst.chat_api_key:
            endpoint_info["has_api_key"] = True
        if inst.chat_extra_headers:
            endpoint_info["extra_headers"] = str(inst.chat_extra_headers)
        if inst.chat_extra_body:
            endpoint_info["extra_body"] = str(inst.chat_extra_body)
        if endpoint_info:
            scraper_endpoints[slug] = endpoint_info

    # 从数据库读取所有活跃、未隐藏的 provider 及其模型
    providers_dict: dict[str, dict] = {}

    with get_connection() as conn:
        conn.row_factory = __dict_factory
        cursor = conn.cursor()

        # 查询 providers
        cursor.execute("""
            SELECT id, name, slug, website, scrape_url, logo_url,
                   is_active, hidden, last_scraped
            FROM providers
            WHERE (hidden IS NULL OR hidden = 0)
              AND (is_active IS NULL OR is_active = 1)
            ORDER BY name
        """)
        provider_rows = cursor.fetchall()

        for prow in provider_rows:
            slug = prow["slug"]
            slug = slug.replace("-", "_")  # Hermes 用下划线

            # 查询该 provider 下的所有模型
            cursor.execute("""
                SELECT model_id, name, description, type, is_free,
                       context_window, capability_tier, use_case, tags
                FROM models
                WHERE provider_id = ?
                ORDER BY is_free DESC, capability_tier ASC NULLS LAST, name
            """, (prow["id"],))
            model_rows = cursor.fetchall()

            if not model_rows:
                continue

            # 构造 provider 元数据
            display_name = prow["name"] or slug
            metadata: dict = {
                "display_name": display_name,
            }
            if prow.get("website"):
                metadata["website"] = prow["website"]
            if prow.get("logo_url"):
                metadata["logo_url"] = prow["logo_url"]
            if prow.get("last_scraped"):
                metadata["last_scraped"] = prow["last_scraped"]

            # 合并爬虫的 endpoint 信息
            original_slug = prow["slug"]
            if original_slug in scraper_endpoints:
                metadata.update(scraper_endpoints[original_slug])

            # 构造模型列表
            models_list = []
            for mrow in model_rows:
                entry: dict = {"id": mrow["model_id"]}

                # 可选信息
                extras = []
                if mrow.get("name") and mrow["name"] != mrow["model_id"]:
                    entry["name"] = mrow["name"]
                if mrow.get("is_free"):
                    extras.append("free")
                if mrow.get("use_case"):
                    extras.append(mrow["use_case"])
                if mrow.get("capability_tier") is not None:
                    entry["capability_tier"] = mrow["capability_tier"]
                if mrow.get("context_window"):
                    entry["context_window"] = mrow["context_window"]
                if extras:
                    entry["description"] = ", ".join(extras)

                models_list.append(entry)

            providers_dict[slug] = {
                "metadata": metadata,
                "models": models_list,
            }

    manifest = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata": {
            "source": "Free-Model-Hub",
            "total_providers": len(providers_dict),
            "total_models": sum(len(p["models"]) for p in providers_dict.values()),
        },
        "providers": providers_dict,
    }

    return manifest


def __dict_factory(cursor, row):
    """将 sqlite3.Row 转为 dict"""
    return dict(zip([col[0] for col in cursor.description], row))

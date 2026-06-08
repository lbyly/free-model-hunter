"""
Hermes custom_providers YAML 生成端点

生成可直接复制到 Hermes config.yaml 的 custom_providers 配置块。
每个活跃的 Free-Model-Hub provider 对应一个 custom_providers 条目，
包含 base_url、api_key（如有）、和所有免费模型的列表。

用法：
  curl http://localhost:8000/api/hermes/providers-config
  → 返回 raw YAML 文本，复制到 config.yaml 的 custom_providers: 下

  curl http://localhost:8000/api/hermes/providers-config?format=json
  → 返回 JSON 格式，适合程序化处理
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from textwrap import dedent

import yaml
from fastapi import APIRouter, Query
from database import get_connection
from scrapers import get_all_scrapers
from config import get_api_key_for_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_utc_readable() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def __dict_factory(cursor, row):
    return dict(zip([col[0] for col in cursor.description], row))


@router.get("/providers-config")
async def hermes_providers_config(
    format: str = Query("yaml", description="输出格式: yaml 或 json"),
    include_public: bool = Query(
        True, description="是否包含无需 API Key 的公共 Provider（如 mollinations）"
    ),
    include_models: bool = Query(
        True, description="是否在配置中包含所有模型的 context_length"
    ),
):
    """
    生成 Hermes custom_providers 配置。

    输出可直接复制到 ~/.hermes/config.yaml 的 custom_providers: 字段下。
    """
    # 收集 scrapers 的 endpoint 配置
    scrapers = get_all_scrapers()
    scraper_endpoints: dict[str, dict] = {}
    for slug, scraper_cls in scrapers.items():
        inst = scraper_cls()
        ep = {}
        if inst.chat_endpoint_base:
            ep["base_url"] = inst.chat_endpoint_base.rstrip("/")
        if inst.chat_endpoint_template:
            ep["endpoint_template"] = inst.chat_endpoint_template
        if inst.chat_api_key:
            ep["has_hardcoded_key"] = True
        if ep:
            scraper_endpoints[slug] = ep

    # 从数据库读取所有活跃 provider
    providers_list: list[dict] = []

    with get_connection() as conn:
        conn.row_factory = __dict_factory
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, slug, is_active, hidden
            FROM providers
            WHERE (hidden IS NULL OR hidden = 0)
              AND (is_active IS NULL OR is_active = 1)
            ORDER BY name
        """)
        provider_rows = cursor.fetchall()

        for prow in provider_rows:
            slug = prow["slug"]

            # 跳过没有 endpoint 配置的 provider
            ep_info = scraper_endpoints.get(slug, {})
            base_url = ep_info.get("base_url", "")
            if not base_url:
                continue

            # 读取 API Key
            # 优先用 scraper 的硬编码 key（如公共 API），
            # 再用 config.py 的环境变量映射
            api_key = ""
            if ep_info.get("has_hardcoded_key"):
                inst = scrapers[slug]()
                api_key = inst.chat_api_key or ""
            if not api_key:
                api_key = get_api_key_for_slug(slug)

            # 读取该 provider 的所有模型
            cursor.execute("""
                SELECT model_id, name, context_window, is_free
                FROM models
                WHERE provider_id = ?
                ORDER BY is_free DESC, name
            """, (prow["id"],))
            model_rows = cursor.fetchall()

            if not model_rows:
                continue

            # 构造模型列表
            default_model = ""
            models_dict: dict[str, dict] = {}

            for mrow in model_rows:
                mid = mrow["model_id"]
                if not default_model:
                    default_model = mid

                if include_models and mrow.get("context_window"):
                    ctx = str(mrow["context_window"])
                    try:
                        ctx_int = int(ctx)
                        models_dict[mid] = {"context_length": ctx_int}
                    except (ValueError, TypeError):
                        models_dict[mid] = {"context_length": ctx}
                else:
                    models_dict[mid] = {}

            # 构造 provider 条目
            display_name = prow["name"] or slug
            entry: dict = {
                "name": display_name,
                "base_url": base_url,
                "discover_models": False,   # 避免 Hermes 实时探测 /v1/models（20+ 秒延迟）
            }

            has_any_key = bool(api_key)
            if has_any_key:
                entry["api_key"] = api_key
            elif not include_public:
                # 跳过没有 API Key 的公共 provider
                continue

            entry["model"] = default_model
            if models_dict and include_models:
                entry["models"] = models_dict
                entry["total_models"] = len(models_dict)

            providers_list.append(entry)

    if format == "json":
        return {
            "source": "Free-Model-Hub",
            "updated_at": _now_utc(),
            "total_providers": len(providers_list),
            "providers": providers_list,
        }

    # YAML 输出 - 构造 custom_providers 块的注释说明
    header = dedent(f"""\
        # ── Free-Model-Hub Auto-Generated Providers ──────────────────
        # Generated at: {_now_utc_readable()}
        # Source: Free-Model-Hub ({len(providers_list)} providers)
        #
        # 将此块复制到 config.yaml 的 custom_providers: 字段下。
        # 如果已有 custom_providers: 条目，请手动合并。
        # ────────────────────────────────────────────────────────────
    """)

    # 生成 YAML
    yaml_text = yaml.dump(
        providers_list,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
        indent=2,
    )

    # yaml.dump returns str in PyYAML, but we ensure str for type safety
    yaml_str = str(yaml_text) if not isinstance(yaml_text, str) else yaml_text

    # 返回纯文本 YAML
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(header + yaml_str + "\n")

"""
数据库操作辅助函数（Repository 层）
"""
import json
import time
import sys
import os
from typing import Optional
from database import get_db
from classifier import classify_model
# 从项目根目录加入 sys.path 以便导入 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_api_key_for_slug


# ===== Provider 操作 =====

def get_all_providers(active_only: bool = True, include_hidden: bool = False) -> list[dict]:
    """获取所有 Provider"""
    with get_db() as db:
        where = []
        params = []
        if active_only:
            where.append("is_active = 1")
        if not include_hidden:
            where.append("(hidden IS NULL OR hidden = 0)")
        where_sql = " AND ".join(where) if where else "1=1"
        rows = db.execute(f"SELECT * FROM providers WHERE {where_sql} ORDER BY name").fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # 统计模型数
            cnt = db.execute("SELECT COUNT(*) as c FROM models WHERE provider_id = ?", (d["id"],)).fetchone()
            d["model_count"] = cnt["c"]
            # hidden 默认 false
            d["hidden"] = bool(d.get("hidden", 0))
            results.append(d)
        return results


def get_provider_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 获取 Provider"""
    with get_db() as db:
        row = db.execute("SELECT * FROM providers WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["hidden"] = bool(d.get("hidden", 0))
        return d


def toggle_provider_hidden(slug: str) -> dict:
    """切换 Provider 的 hidden 状态，返回更新后的 provider"""
    with get_db() as db:
        row = db.execute("SELECT id, hidden FROM providers WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise ValueError(f"Provider '{slug}' not found")
        new_hidden = 0 if row["hidden"] else 1
        db.execute("UPDATE providers SET hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?", (new_hidden, slug))
        # 重新查询完整信息返回
        updated = db.execute("SELECT * FROM providers WHERE slug = ?", (slug,)).fetchone()
        d = dict(updated)
        cnt = db.execute("SELECT COUNT(*) as c FROM models WHERE provider_id = ?", (d["id"],)).fetchone()
        d["model_count"] = cnt["c"]
        d["hidden"] = bool(d["hidden"])
        return d


def batch_set_providers_hidden(slugs: list[str], hidden: bool) -> list[dict]:
    """批量设置 Provider 的 hidden 状态"""
    hidden_int = 1 if hidden else 0
    with get_db() as db:
        placeholders = ",".join("?" for _ in slugs)
        db.execute(
            f"UPDATE providers SET hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE slug IN ({placeholders})",
            [hidden_int] + slugs
        )
        # 返回更新后的所有提供商
        rows = db.execute(
            f"SELECT * FROM providers WHERE slug IN ({placeholders}) ORDER BY name",
            slugs
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            cnt = db.execute("SELECT COUNT(*) as c FROM models WHERE provider_id = ?", (d["id"],)).fetchone()
            d["model_count"] = cnt["c"]
            d["hidden"] = bool(d["hidden"])
            results.append(d)
        return results


# ===== Model 操作 =====

def search_models(
    provider: Optional[str] = None,
    is_free: Optional[bool] = None,
    model_type: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[str] = None,
    capability_tier: Optional[int] = None,
    use_case: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """搜索模型，返回 (models, total_count)"""
    with get_db() as db:
        where_clauses = []
        params = []

        if provider:
            where_clauses.append("p.slug = ?")
            params.append(provider)
        if is_free is not None:
            where_clauses.append("m.is_free = ?")
            params.append(1 if is_free else 0)
        if model_type:
            where_clauses.append("m.type = ?")
            params.append(model_type)
        if search:
            where_clauses.append("(m.name LIKE ? OR m.model_id LIKE ? OR m.description LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            for t in tag_list:
                where_clauses.append("m.tags LIKE ?")
                params.append(f"%{t}%")
        if capability_tier is not None:
            where_clauses.append("m.capability_tier = ?")
            params.append(capability_tier)
        if use_case:
            where_clauses.append("m.use_case = ?")
            params.append(use_case)

        # 排除已隐藏提供商的模型
        where_clauses.append("(p.hidden IS NULL OR p.hidden = 0)")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # 统计总数
        count_row = db.execute(
            f"SELECT COUNT(*) as c FROM models m JOIN providers p ON m.provider_id = p.id WHERE {where_sql}",
            params
        ).fetchone()
        total = count_row["c"]

        # 排序
        if sort == "tier":
            order_sql = "m.capability_tier ASC, m.is_free DESC, p.name, m.name"
        elif sort == "tier_desc":
            order_sql = "m.capability_tier DESC, m.is_free DESC, p.name, m.name"
        elif sort == "newest":
            order_sql = "m.created_at DESC, p.name, m.name"
        else:
            order_sql = "m.is_free DESC, m.capability_tier ASC NULLS LAST, p.name, m.name"

        # 分页查询
        offset = (page - 1) * page_size
        rows = db.execute(
            f"""
            SELECT m.*, p.name as provider_name, p.slug as provider_slug, p.logo_url as provider_logo
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset]
        ).fetchall()

        models = []
        for row in rows:
            d = dict(row)
            # 解析 tags
            try:
                d["tags"] = json.loads(d.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            # 获取速率限制
            rate_rows = db.execute(
                "SELECT * FROM model_rate_limits WHERE model_id = ?",
                (d["id"],)
            ).fetchall()
            d["rate_limits"] = [dict(r) for r in rate_rows]
            # 嵌套 provider 信息（同时从 .env 注入 API Key）
            provider_slug = d.pop("provider_slug")
            d["provider"] = {
                "slug": provider_slug,
                "name": d.pop("provider_name"),
                "logo_url": d.pop("provider_logo"),
                "api_key": get_api_key_for_slug(provider_slug),
            }
            models.append(d)

        return models, total


def get_model_by_id(model_id: int) -> Optional[dict]:
    """根据 ID 获取模型详情"""
    with get_db() as db:
        row = db.execute(
            """
            SELECT m.*, p.name as provider_name, p.slug as provider_slug,
                   p.website as provider_website, p.logo_url as provider_logo
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            WHERE m.id = ?
            """,
            (model_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        rate_rows = db.execute(
            "SELECT * FROM model_rate_limits WHERE model_id = ?",
            (d["id"],)
        ).fetchall()
        d["rate_limits"] = [dict(r) for r in rate_rows]
        d["provider"] = {
            "slug": d.pop("provider_slug"),
            "name": d.pop("provider_name"),
            "website": d.pop("provider_website"),
            "logo_url": d.pop("provider_logo"),
            # 从 .env 注入该 provider 对应的 API Key（未配置则为空串）
            "api_key": get_api_key_for_slug(d["provider"]["slug"]),
        }
        return d


# ===== 爬虫数据写入 =====

def upsert_models(provider_id: int, models: list) -> int:
    """
    UPSERT 写入模型数据
    返回本次写入/更新的数量
    """
    # 仅保留免费的模型（is_free 为 True 的模型），舍弃任何收费模型
    models = [m for m in models if m.get("is_free")]

    count = 0
    # 获取 provider slug
    with get_db() as db:
        provider_row = db.execute("SELECT slug, name FROM providers WHERE id = ?", (provider_id,)).fetchone()
        provider_slug = provider_row["slug"] if provider_row else ""
        provider_name = provider_row["name"] if provider_row else ""

    with get_db() as db:
        # 获取本次爬取的 model_id 集合，删除该 provider 下不再存在的模型
        current_ids = tuple(m["model_id"] for m in models)
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            # 先删除这些 model 的 rate_limits（避免外键约束）
            stale_models = db.execute(
                f"SELECT id FROM models WHERE provider_id = ? AND model_id NOT IN ({placeholders})",
                (provider_id, *current_ids)
            ).fetchall()
            for sm in stale_models:
                db.execute("DELETE FROM model_rate_limits WHERE model_id = ?", (sm["id"],))
            # 删除该 provider 下已不存在的模型
            db.execute(
                f"DELETE FROM models WHERE provider_id = ? AND model_id NOT IN ({placeholders})",
                (provider_id, *current_ids)
            )
        else:
            # 如果没有模型返回，清空该 provider 的所有模型
            db.execute("DELETE FROM model_rate_limits WHERE model_id IN (SELECT id FROM models WHERE provider_id = ?)", (provider_id,))
            db.execute("DELETE FROM models WHERE provider_id = ?", (provider_id,))

        for m in models:
            # 自动分类
            classification = classify_model(
                name=m.get("name", ""),
                model_id=m.get("model_id", ""),
                model_type=m.get("type", "chat"),
                provider=provider_name,
                context_window=m.get("context_window"),
                description=m.get("description", ""),
            )

            tags_json = json.dumps(m.get("tags", []), ensure_ascii=False)
            db.execute(
                """
                INSERT INTO models (provider_id, model_id, name, description, type,
                    capability_tier, use_case,
                    is_free, free_quota, pricing_url, context_window, tags, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    type=excluded.type,
                    capability_tier=excluded.capability_tier,
                    use_case=excluded.use_case,
                    is_free=excluded.is_free,
                    free_quota=excluded.free_quota,
                    pricing_url=excluded.pricing_url,
                    context_window=excluded.context_window,
                    tags=excluded.tags,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    provider_id,
                    m["model_id"],
                    m.get("name", ""),
                    m.get("description", ""),
                    m.get("type", "chat"),
                    classification["capability_tier"],
                    classification["use_case"],
                    1 if m.get("is_free") else 0,
                    m.get("free_quota"),
                    m.get("pricing_url"),
                    m.get("context_window"),
                    tags_json,
                    m.get("status", "active"),
                )
            )
            # 获取插入/更新的 model_id
            model_row = db.execute(
                "SELECT id FROM models WHERE provider_id = ? AND model_id = ?",
                (provider_id, m["model_id"])
            ).fetchone()
            if model_row:
                # 处理速率限制
                db.execute("DELETE FROM model_rate_limits WHERE model_id = ?", (model_row["id"],))
                for rl in m.get("rate_limits", []):
                    db.execute(
                        "INSERT INTO model_rate_limits (model_id, rate_type, limit_value, tier) VALUES (?, ?, ?, ?)",
                        (model_row["id"], rl.get("rate_type"), rl.get("limit_value"), rl.get("tier", "free"))
                    )
            count += 1

        # 更新 provider 的最后爬取时间
        db.execute(
            "UPDATE providers SET last_scraped = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (provider_id,)
        )
    return count


def classify_all_models() -> dict:
    """
    对数据库中所有未分类或全部分类进行重新分类。
    返回统计信息。
    """
    from classifier import classify_model as cm

    with get_db() as db:
        rows = db.execute("""
            SELECT m.id, m.name, m.model_id, m.type, p.name as provider_name,
                   m.context_window, m.description
            FROM models m
            JOIN providers p ON m.provider_id = p.id
        """).fetchall()

        stats = {"total": len(rows), "updated": 0, "by_tier": {1: 0, 2: 0, 3: 0}, "by_use_case": {}}

        for row in rows:
            d = dict(row)
            classification = cm(
                name=d.get("name", ""),
                model_id=d.get("model_id", ""),
                model_type=d.get("type", "chat"),
                provider=d.get("provider_name", ""),
                context_window=d.get("context_window"),
                description=d.get("description", ""),
            )
            db.execute(
                "UPDATE models SET capability_tier = ?, use_case = ? WHERE id = ?",
                (classification["capability_tier"], classification["use_case"], d["id"])
            )
            stats["updated"] += 1
            stats["by_tier"][classification["capability_tier"]] = \
                stats["by_tier"].get(classification["capability_tier"], 0) + 1
            stats["by_use_case"][classification["use_case"]] = \
                stats["by_use_case"].get(classification["use_case"], 0) + 1

    return stats


def log_scrape(provider_id: int, status: str, model_count: int, error_message: str = "", duration: float = 0):
    """记录爬取日志"""
    with get_db() as db:
        db.execute(
            "INSERT INTO scrape_logs (provider_id, status, model_count, error_message, duration_seconds) VALUES (?, ?, ?, ?, ?)",
            (provider_id, status, model_count, error_message[:500] if error_message else "", duration)
        )


def seed_providers():
    """初始化 Provider 数据"""
    providers = [
        {"name": "GitHub Models", "slug": "github_models", "website": "https://github.com/marketplace/models",
         "scrape_url": "https://github.com/marketplace/models", "scraper_class": "GitHubModelsScraper",
         "logo_url": "https://github.githubassets.com/favicons/favicon.svg"},
        {"name": "NotDiamond", "slug": "notdiamond", "website": "https://notdiamond.ai",
         "scrape_url": "https://api.notdiamond.ai/v2/models", "scraper_class": "NotDiamondScraper",
         "logo_url": ""},
        {"name": "阿里云百炼", "slug": "alibaba_bailian", "website": "https://bailian.console.aliyun.com",
         "scrape_url": "https://bailian.console.aliyun.com", "scraper_class": "AlibabaBailianScraper",
         "logo_url": "https://bailian.console.aliyun.com/favicon.ico"},
        {"name": "X.ai", "slug": "xai", "website": "https://x.ai/api",
         "scrape_url": "https://x.ai/api", "scraper_class": "XaiScraper",
         "logo_url": ""},
        {"name": "AnyRouter", "slug": "anyrouter", "website": "https://anyrouter.ai",
         "scrape_url": "https://anyrouter.ai", "scraper_class": "AnyRouterScraper",
         "logo_url": ""},
        {"name": "MiniMax", "slug": "minimax", "website": "https://minimax.com",
         "scrape_url": "https://minimax.com", "scraper_class": "MiniMaxScraper",
         "logo_url": ""},
        {"name": "Grok", "slug": "grok", "website": "https://grok.com",
         "scrape_url": "https://grok.com", "scraper_class": "GrokScraper",
         "logo_url": ""},
        {"name": "OpenCode", "slug": "opencode", "website": "https://opencode.ai",
         "scrape_url": "https://opencode.ai", "scraper_class": "OpenCodeScraper",
         "logo_url": ""},
        {"name": "Zen API", "slug": "zen", "website": "https://zenapi.ai",
         "scrape_url": "https://zenapi.ai", "scraper_class": "ZenScraper",
         "logo_url": ""},
        {"name": "Groq", "slug": "groq", "website": "https://groq.com",
         "scrape_url": "https://groq.com", "scraper_class": "GroqScraper",
         "logo_url": ""},
        {"name": "Cohere", "slug": "cohere", "website": "https://cohere.com",
         "scrape_url": "https://cohere.com", "scraper_class": "CohereScraper",
         "logo_url": ""},
        {"name": "Gemini", "slug": "gemini", "website": "https://ai.google.dev",
         "scrape_url": "https://ai.google.dev", "scraper_class": "GeminiScraper",
         "logo_url": ""},
        {"name": "OpenRouter", "slug": "openrouter", "website": "https://openrouter.ai",
         "scrape_url": "https://openrouter.ai", "scraper_class": "OpenRouterScraper",
         "logo_url": ""},
        {"name": "Cerebras", "slug": "cerebras", "website": "https://cerebras.ai",
         "scrape_url": "https://api.cerebras.ai/v1/models", "scraper_class": "CerebrasScraper",
         "logo_url": ""},
        {"name": "Agnes AI", "slug": "agnes", "website": "https://agnes.ai",
         "scrape_url": "https://agnes.ai", "scraper_class": "AgnesScraper",
         "logo_url": ""},
        {"name": "Mollinations.ai", "slug": "mollinations", "website": "https://mollinations.ai",
         "scrape_url": "https://mollinations.ai", "scraper_class": "MollinationsScraper",
         "logo_url": ""},
        {"name": "商汤日日新", "slug": "sensenova", "website": "https://platform.sensenova.cn",
         "scrape_url": "https://token.sensenova.cn/v1/models", "scraper_class": "SenseNovaScraper",
         "logo_url": ""},
        {"name": "NVIDIA", "slug": "nvidia", "website": "https://build.nvidia.com/explore/discover",
         "scrape_url": "https://integrate.api.nvidia.com/v1/models", "scraper_class": "NvidiaScraper",
         "logo_url": ""},
    ]
    with get_db() as db:
        for p in providers:
            existing = db.execute("SELECT id FROM providers WHERE slug = ?", (p["slug"],)).fetchone()
            if not existing:
                db.execute(
                    """INSERT INTO providers (name, slug, website, scrape_url, scraper_class, logo_url)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (p["name"], p["slug"], p["website"], p["scrape_url"], p["scraper_class"], p["logo_url"])
                )
        print(f"  [OK] 已初始化 {len(providers)} 个 Provider")

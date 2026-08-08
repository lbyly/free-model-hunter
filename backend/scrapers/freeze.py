"""
冻结爬虫 (Freeze Scrapers)

这些 provider 的模型列表以数据库中的"可见模型"（user_removed=0）为准，
爬虫刷新时不再调用上游 /v1/models 全量接口，而是直接返回当前保留的模型集合。

用途：PA (Page Assist) 已验证裁剪后的模型清单固化 —— 防止定时刷新/启动刷新
把全量模型重新拉回（如 omniroute 曾从 15 膨胀到 2536）。

如需新增模型：直接在数据库将 user_removed 置 0（或调用恢复 API），下次刷新即生效。
如需彻底放弃冻结：删除本文件即可（get_scraper 将回退到通用爬虫）。
"""
import json
import logging
import sqlite3

from .base import BaseScraper, ScrapedModel

logger = logging.getLogger(__name__)

# 所有被冻结的 provider slug（也用于 get_scraper 的快速判断）
FROZEN_SLUGS = {
    "agnes", "agnes_com", "blazeai", "cerebras", "cf_gateway_free",
    "chat2api", "cpamc", "ds2api", "ds2api_vercel", "fyra",
    "grok2api", "groq", "kilo", "manifest", "manifest_1111",
    "modelscope", "nararouter", "nvidia", "omniroute", "opencode",
    "openrouter", "peezy", "scnet", "sensenova", "step", "webai2api",
}


class FreezeScraper(BaseScraper):
    """从数据库读取该 provider 的可见模型（user_removed=0）并返回。

    不设置 chat_endpoint_base —— 不触发 verify_free_models 的 Hi 免费验证，
    保留数据库中的 is_free 状态原样。
    """

    provider_slug = "freeze"  # 占位，实际以子类为准

    def __init__(self, slug: str = None):
        super().__init__()
        if slug:
            self.provider_slug = slug
        self.chat_endpoint_base = None
        self.chat_endpoint_template = None

    async def scrape(self) -> list[ScrapedModel]:
        db_path = self._resolve_db_path()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT m.model_id, m.name, m.description, m.type, m.is_free,
                           m.free_quota, m.pricing_url, m.context_window, m.tags,
                           m.status
                    FROM models m
                    JOIN providers p ON m.provider_id = p.id
                    WHERE p.slug = ? AND COALESCE(m.user_removed, 0) = 0
                    """,
                    (self.provider_slug,),
                ).fetchall()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"[freeze:{self.provider_slug}] 读取数据库失败: {e}")
            return []

        models = []
        for r in rows:
            try:
                tags = json.loads(r["tags"]) if r["tags"] else []
            except (json.JSONDecodeError, TypeError):
                tags = []
            models.append(ScrapedModel(
                model_id=r["model_id"],
                name=r["name"] or r["model_id"],
                description=r["description"] or "",
                model_type=r["type"] or "chat",
                is_free=bool(r["is_free"]),
                free_quota=r["free_quota"],
                pricing_url=r["pricing_url"],
                context_window=r["context_window"],
                tags=tags,
                status=r["status"] or "active",
            ))
        logger.info(f"[freeze:{self.provider_slug}] 返回冻结清单 {len(models)} 个模型")
        return models

    @staticmethod
    def _resolve_db_path() -> str:
        """使用服务配置的 DATABASE_PATH（主库 D:/Free-Model-Hub/data/models.db），
        避免 fallback 到 cwd 下的旧库 backend/data/models.db"""
        try:
            from config import DATABASE_PATH
            return DATABASE_PATH
        except Exception:
            import os
            candidates = [
                os.path.join(os.getcwd(), "data", "models.db"),
                r"D:\Free-Model-Hub\data\models.db",
            ]
            for p in candidates:
                if os.path.exists(p):
                    return p
            return candidates[0]


def _make_frozen_cls(slug: str):
    """为指定 slug 生成一个 FreezeScraper 子类（类名首字母大写）"""
    name = "".join(part.capitalize() for part in slug.replace("-", "_").split("_")) + "FreezeScraper"
    return type(name, (FreezeScraper,), {"provider_slug": slug})


# 为每个冻结 provider 生成独立类，discover_scrapers 会自动注册
for _slug in sorted(FROZEN_SLUGS):
    _cls = _make_frozen_cls(_slug)
    globals()[_cls.__name__] = _cls

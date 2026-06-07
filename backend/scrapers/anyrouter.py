"""
AnyRouter 爬虫
"""
from .base import BaseScraper, ScrapedModel


class AnyRouterScraper(BaseScraper):
    provider_slug = "anyrouter"

    async def scrape(self) -> list[ScrapedModel]:
        # AnyRouter 聚合 API，标记免费模型
        return [
            ScrapedModel(model_id="deepseek-chat", name="DeepSeek Chat", model_type="chat",
                is_free=True, tags=["anyrouter", "deepseek"]),
            ScrapedModel(model_id="gemini-2.0-flash", name="Gemini 2.0 Flash", model_type="chat",
                is_free=True, free_quota="通过 AnyRouter 免费路由", tags=["anyrouter", "gemini"]),
            ScrapedModel(model_id="qwen-turbo", name="Qwen Turbo", model_type="chat",
                is_free=True, tags=["anyrouter", "qwen"]),
        ]
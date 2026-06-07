"""
OpenCode 爬虫
"""
from .base import BaseScraper, ScrapedModel


class OpenCodeScraper(BaseScraper):
    provider_slug = "opencode"

    async def scrape(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="opencode-llm", name="OpenCode LLM",
                model_type="chat", is_free=True,
                free_quota="OpenCode 免费 API 层",
                tags=["opencode"]),
        ]

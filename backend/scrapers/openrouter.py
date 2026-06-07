"""
OpenRouter 爬虫
"""
import httpx
from .base import BaseScraper, ScrapedModel


class OpenRouterScraper(BaseScraper):
    provider_slug = "openrouter"

    async def scrape(self) -> list[ScrapedModel]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            pricing = item.get("pricing", {})
            prompt_price = float(pricing.get("prompt", 1)) if pricing else 1
            completion_price = float(pricing.get("completion", 1)) if pricing else 1
            is_free = prompt_price == 0 and completion_price == 0
            context = str(item.get("context_length", ""))
            models.append(ScrapedModel(
                model_id=mid,
                name=mid.split("/")[-1] if "/" in mid else mid,
                description=item.get("description", ""),
                model_type="chat",
                is_free=is_free,
                free_quota="完全免费" if is_free else None,
                context_window=context,
                tags=["openrouter"],
            ))
        return models

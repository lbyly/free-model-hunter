"""
Grok (xAI) 爬虫
"""
import httpx
from .base import BaseScraper, ScrapedModel


class GrokScraper(BaseScraper):
    provider_slug = "grok"

    async def scrape(self) -> list[ScrapedModel]:
        # Grok 通过 xAI API 提供
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://api.x.ai/v1/models")
                resp.raise_for_status()
                data = resp.json()
            models = []
            for item in data.get("data", []):
                mid = item.get("id", "")
                if "grok" in mid.lower():
                    models.append(ScrapedModel(
                        model_id=mid,
                        name=mid,
                        description=item.get("description", ""),
                        model_type="chat",
                        is_free=False,
                        free_quota=None,
                        tags=["grok", "xai"],
                    ))
            return models
        except Exception:
            # 降级返回已知模型
            return [
                ScrapedModel(model_id="grok-3", name="Grok 3", model_type="chat",
                    is_free=True, free_quota="X Premium 免费使用", tags=["grok"]),
                ScrapedModel(model_id="grok-3-mini", name="Grok 3 Mini", model_type="chat",
                    is_free=True, free_quota="X Premium 免费使用", tags=["grok"]),
            ]

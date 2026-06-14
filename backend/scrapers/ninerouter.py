"""
9router 本地爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import NINEROUTER_API_KEY

logger = logging.getLogger(__name__)

class NineRouterScraper(BaseScraper):
    provider_slug = "9router"
    chat_endpoint_base = "http://localhost:20128/v1"
    chat_api_key = NINEROUTER_API_KEY
    
    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"9router API 请求失败 ({type(e).__name__}: {e})")
            return []

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(
                f"{self.chat_endpoint_base}/models",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return self._parse_models(data)

    def _parse_models(self, data: dict) -> list[ScrapedModel]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type="chat",
                is_free=False,  # 设置为 False，交由 verify_free_models 发送 'Hi' 测试
                tags=["9router"],
            ))
        return models

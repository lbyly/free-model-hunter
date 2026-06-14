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
        return await self._scrape_via_api()

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
            lower_mid = mid.lower()
            
            # 9router 返回了 99 个模型，但我们只关心免费的
            if "free" not in lower_mid:
                continue
            # 排除名为 Freemode/ 的收费/失效节点
            if lower_mid.startswith("freemode/"):
                continue
                
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type="chat",
                is_free=False,  # 设置为 False，让 verify_free_models 去发送 Hi 实际测试它们是否连通
                tags=["9router"],
            ))
        return models

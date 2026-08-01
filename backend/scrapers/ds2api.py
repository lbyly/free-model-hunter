"""
ds2api 爬虫 - 调用 OpenAI 兼容 API 获取模型列表
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import get_api_key_for_slug

logger = logging.getLogger(__name__)


class ds2apiScraper(BaseScraper):
    provider_slug = "ds2api"
    chat_endpoint_base = "http://127.0.0.1:5001/v1"
    
    @property
    def chat_api_key(self):
        return get_api_key_for_slug(self.provider_slug)

    async def scrape(self) -> list[ScrapedModel]:
        api_url = f"{self.chat_endpoint_base}/models"
        
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
        }
        api_key = self.chat_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(api_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"ds2api API 请求失败: {e}")
            return []

        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            
            models.append(ScrapedModel(
                model_id=mid,
                name=item.get("name", mid.split("/")[-1] if "/" in mid else mid),
                description=item.get("description", ""),
                model_type="chat",
                is_free=False,  # 设为 False，由 verify_free_models 发送 Hi 验证连通性
                tags=["ds2api"],
            ))
        
        logger.info(f"ds2api 爬取到 {len(models)} 个模型")
        return models

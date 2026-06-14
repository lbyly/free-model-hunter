"""
CPAMC (本地中转) 爬虫 - 调用 OpenAI 兼容 API 获取模型列表
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import CPAMC_API_KEY

logger = logging.getLogger(__name__)


class CpamcScraper(BaseScraper):
    provider_slug = "cpamc"
    chat_endpoint_base = "http://127.0.0.1:8317/v1"

    async def scrape(self) -> list[ScrapedModel]:
        """调用本地中转 API 获取模型列表"""
        api_url = "http://127.0.0.1:8317/v1/models"
        
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
        }
        if CPAMC_API_KEY:
            headers["Authorization"] = f"Bearer {CPAMC_API_KEY}"
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(api_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"cpamc API 请求失败: {e}")
            return []

        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            
            # 尝试获取定价信息
            input_price = item.get("input_token_price_per_m", 0) or item.get("pricing", {}).get("input", 0)
            output_price = item.get("output_token_price_per_m", 0) or item.get("pricing", {}).get("output", 0)
            
            # 判断是否免费
            is_free = False
            free_quota = None
            
            # 检查是否标记为免费
            metadata = item.get("metadata", {})
            if metadata.get("free") or item.get("free"):
                is_free = True
                free_quota = metadata.get("free_quota", "完全免费")
            elif input_price == 0 and output_price == 0:
                is_free = True
                free_quota = "定价为零"
            
            models.append(ScrapedModel(
                model_id=mid,
                name=item.get("name", mid.split("/")[-1] if "/" in mid else mid),
                description=item.get("description", ""),
                model_type="chat",
                is_free=is_free,
                free_quota=free_quota,
                context_window=str(item.get("context_length", "")) if item.get("context_length") else None,
                tags=["cpamc"],
            ))
        
        logger.info(f"cpamc 爬取到 {len(models)} 个模型")
        return models

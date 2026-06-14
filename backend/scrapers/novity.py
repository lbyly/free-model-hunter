"""
Novity (Novita AI) 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import NOVITY_API_KEY

logger = logging.getLogger(__name__)


class NovityScraper(BaseScraper):
    provider_slug = "novity"
    chat_endpoint_base = "https://api.novita.ai/v3/openai"

    async def scrape(self) -> list[ScrapedModel]:
        if not NOVITY_API_KEY:
            logger.warning("NOVITY_API_KEY 未配置，使用已知模型")
            return self._known_models()

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.novita.ai/v3/openai/models",
                    headers={
                        "Authorization": f"Bearer {NOVITY_API_KEY}",
                        "User-Agent": "FreeModelsHub/1.0",
                    }
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"novity API 请求失败: {e}, 使用已知模型降级")
            return self._known_models()

        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            input_price = item.get("input_token_price_per_m", 1)
            output_price = item.get("output_token_price_per_m", 1)
            
            # 定价为 0 的模型视为免费
            is_free = (input_price == 0 and output_price == 0)
            
            if is_free:
                models.append(ScrapedModel(
                    model_id=mid,
                    name=mid.split("/")[-1] if "/" in mid else mid,
                    description=f"Owned by: {item.get('owned_by', 'unknown')}",
                    model_type="chat",
                    is_free=True,
                    free_quota="完全免费",
                    tags=["novity", "novita"],
                ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="meta-llama/llama-3-8b-instruct", name="llama-3-8b-instruct",
                         model_type="chat", is_free=True,
                         free_quota="完全免费", tags=["novity", "novita"]),
            ScrapedModel(model_id="meta-llama/llama-3-70b-instruct", name="llama-3-70b-instruct",
                         model_type="chat", is_free=True,
                         free_quota="完全免费", tags=["novity", "novita"]),
            ScrapedModel(model_id="microsoft/wizardlm-2-8x22b", name="wizardlm-2-8x22b",
                         model_type="chat", is_free=True,
                         free_quota="完全免费", tags=["novity", "novita"]),
        ]

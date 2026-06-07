"""
Groq 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)


class GroqScraper(BaseScraper):
    provider_slug = "groq"
    chat_endpoint_base = "https://api.groq.com/openai/v1"
    chat_api_key = GROQ_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"groq API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        if GROQ_API_KEY:
            headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.groq.com/openai/v1/models", headers=headers)
            if resp.status_code == 401 and not GROQ_API_KEY:
                logger.warning("Groq API 需要 API Key，使用已知模型")
                return self._known_models()
            resp.raise_for_status()
            data = resp.json()
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=f"由 Groq 提供，高速推理",
                model_type="chat",
                is_free=False,
                free_quota=None,
                tags=["groq", "fast"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="llama-3.3-70b-versatile", name="Llama 3.3 70B",
                         model_type="chat", is_free=True,
                         free_quota="Groq 免费层：30 RPM", tags=["groq", "meta"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
            ScrapedModel(model_id="llama-3.1-8b-instant", name="Llama 3.1 8B",
                         model_type="chat", is_free=True,
                         free_quota="Groq 免费层：30 RPM", tags=["groq", "meta"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
            ScrapedModel(model_id="mixtral-8x7b-32768", name="Mixtral 8x7B",
                         model_type="chat", is_free=True,
                         free_quota="Groq 免费层：30 RPM", tags=["groq", "mistral"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
            ScrapedModel(model_id="gemma2-9b-it", name="Gemma 2 9B",
                         model_type="chat", is_free=True,
                         free_quota="Groq 免费层：30 RPM", tags=["groq", "google"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
            ScrapedModel(model_id="deepseek-r1-distill-llama-70b", name="DeepSeek R1 Distill Llama 70B",
                         model_type="chat", is_free=True,
                         free_quota="Groq 免费层：30 RPM", tags=["groq", "deepseek"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
        ]

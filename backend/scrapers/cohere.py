"""
Cohere 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import COHERE_API_KEY

logger = logging.getLogger(__name__)


class CohereScraper(BaseScraper):
    provider_slug = "cohere"

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"cohere API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        if COHERE_API_KEY:
            headers["Authorization"] = f"Bearer {COHERE_API_KEY}"
        else:
            # 无 API Key 时尝试免认证端点
            pass

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.cohere.ai/v1/models", headers=headers)
            if resp.status_code == 401 and not COHERE_API_KEY:
                logger.warning("Cohere API 需要 API Key，使用已知模型")
                return self._known_models()
            resp.raise_for_status()
            data = resp.json()

        models = []
        for item in (data if isinstance(data, list) else data.get("models", [])):
            mid = item.get("name", "") or item.get("id", "")
            if not mid:
                continue
            is_free = "free" in str(item.get("pricing", {})).lower() or item.get("is_free")
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type=item.get("type", "chat"),
                is_free=is_free,
                free_quota="Cohere 免费 API 层（每日限制）" if is_free else None,
                tags=["cohere"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="command-r-plus", name="Command R+",
                         model_type="chat", is_free=True,
                         free_quota="Cohere 免费试用层", tags=["cohere"]),
            ScrapedModel(model_id="command-r", name="Command R",
                         model_type="chat", is_free=True,
                         free_quota="Cohere 免费试用层", tags=["cohere"]),
            ScrapedModel(model_id="command-light", name="Command Light",
                         model_type="chat", is_free=True,
                         free_quota="Cohere 免费试用层", tags=["cohere"]),
            ScrapedModel(model_id="embed-english-v3.0", name="Embed English v3",
                         model_type="embedding", is_free=True,
                         free_quota="Cohere 免费试用层", tags=["cohere"]),
        ]
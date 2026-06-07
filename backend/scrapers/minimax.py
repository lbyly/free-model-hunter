"""
MiniMax 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import MINIMAX_API_KEY

logger = logging.getLogger(__name__)


class MiniMaxScraper(BaseScraper):
    provider_slug = "minimax"

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"minimax API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        if MINIMAX_API_KEY:
            # MiniMax 使用 token 认证 (JWT)
            headers["Authorization"] = f"Bearer {MINIMAX_API_KEY}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.minimax.chat/v1/models", headers=headers)
            if resp.status_code == 401:
                # 尝试使用 MiniMax 新版 API 端点
                resp2 = await client.get("https://api.minimax.chat/v1/models/list", headers=headers)
                if resp2.status_code == 401:
                    logger.warning("MiniMax API 需要 API Key，使用已知模型")
                    return self._known_models()
                resp = resp2
            resp.raise_for_status()
            data = resp.json()
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "") or item.get("name", "")
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type="chat",
                is_free=False,
                free_quota=None,
                tags=["minimax"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="minimax-abab6.5-chat", name="MiniMax ABAB 6.5",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["minimax"]),
            ScrapedModel(model_id="minimax-abab6.5s-chat", name="MiniMax ABAB 6.5s",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["minimax"]),
            ScrapedModel(model_id="minimax-abab5.5-chat", name="MiniMax ABAB 5.5",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["minimax"]),
        ]

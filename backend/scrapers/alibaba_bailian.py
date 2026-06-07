"""
阿里云百炼 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import ALIBABA_API_KEY

logger = logging.getLogger(__name__)


class AlibabaBailianScraper(BaseScraper):
    provider_slug = "alibaba_bailian"
    chat_endpoint_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_api_key = ALIBABA_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"alibaba_bailian API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        if ALIBABA_API_KEY:
            headers["Authorization"] = f"Bearer {ALIBABA_API_KEY}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://dashscope.aliyuncs.com/compatible-mode/v1/models", headers=headers)
            if resp.status_code == 401 and not ALIBABA_API_KEY:
                logger.warning("阿里云百炼 API 需要 API Key，使用已知模型")
                return self._known_models()
            resp.raise_for_status()
            data = resp.json()
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "") or item.get("name", "")
            if not mid:
                continue
            models.append(ScrapedModel(
                model_id=mid,
                name=mid.split("/")[-1] if "/" in mid else mid,
                description=item.get("description", ""),
                model_type=item.get("type", "chat"),
                is_free=False,
                free_quota=None,
                tags=["alibaba", "bailian"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="qwen-max", name="Qwen Max",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen-plus", name="Qwen Plus",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen-turbo", name="Qwen Turbo",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen2.5-72b-instruct", name="Qwen 2.5 72B",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen2.5-32b-instruct", name="Qwen 2.5 32B",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen2.5-7b-instruct", name="Qwen 2.5 7B",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen"]),
            ScrapedModel(model_id="qwen2.5-coder-32b-instruct", name="Qwen 2.5 Coder 32B",
                         model_type="chat", is_free=True,
                         free_quota="新用户赠送 100 万 tokens",
                         tags=["alibaba", "qwen", "code"]),
        ]
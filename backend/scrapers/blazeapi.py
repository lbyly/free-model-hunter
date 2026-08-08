"""
blazeapi 爬虫 - 调用 OpenAI 兼容 API 获取模型列表
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import get_api_key_for_slug

logger = logging.getLogger(__name__)


class BlazeaiScraper(BaseScraper):
    provider_slug = "blazeai"
    chat_endpoint_base = "https://api.blazeapi.org/paid/v1"

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
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                resp = await client.get(api_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"blazeapi API 请求失败: {e}")
            return []

        models = []
        seen = set()
        for item in data.get("data", []):
            # blazebapi 返回字段：id(显示名)/model_id(实际调用ID)/context_window/max_output/is_free/available
            mid = item.get("model_id") or item.get("id", "")
            if not mid or mid in seen:
                continue
            seen.add(mid)

            # 模型当前是否可调用（available=false 表示已下架/不可用，跳过）
            if item.get("available") is False:
                continue

            ctx = item.get("context_window")
            max_out = item.get("max_output")

            models.append(ScrapedModel(
                model_id=mid,
                name=item.get("id", mid),
                description="",
                model_type="chat",
                is_free=bool(item.get("is_free")),
                context_window=str(ctx) if ctx else None,
                tags=["blazeapi", "blaze"],
            ))

        logger.info(f"blazeapi 爬取到 {len(models)} 个模型")
        return models
"""
智谱 AI 爬虫 / API 发现
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import ZHIPU_API_KEY

logger = logging.getLogger(__name__)


class ZhipuScraper(BaseScraper):
    provider_slug = "zhipu"
    chat_endpoint_base = "https://open.bigmodel.cn/api/paas/v4"
    chat_api_key = ZHIPU_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"Zhipu API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        # 如果有 ZHIPU_API_KEY，从内存/环境变量获取它
        api_key = self.chat_api_key or ZHIPU_API_KEY
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            logger.warning("Zhipu API 需要 API Key，使用已知模型")
            return self._known_models()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://open.bigmodel.cn/api/paas/v4/models", headers=headers)
            if resp.status_code == 401:
                logger.warning("Zhipu API 认证失败，使用已知模型")
                return self._known_models()
            resp.raise_for_status()
            data = resp.json()

        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            
            # 标记默认免费候选或交由验证模块测试
            is_free = mid in ("glm-4-flash", "glm-4v-flash")
            
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=f"由智谱 AI 提供",
                model_type="vision" if "vision" in mid or "4v" in mid else "chat",
                is_free=is_free,
                free_quota="免费额度以账户状态为准" if not is_free else "API 永久免费使用",
                tags=["zhipu", "glm"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        # 降级备用，当接口失败或未配置 Key 时返回的常见智谱免费模型
        return [
            ScrapedModel(
                model_id="glm-4-flash",
                name="GLM-4-Flash",
                description="智谱 AI 推出的轻量级模型，API 永久免费使用",
                model_type="chat",
                is_free=True,
                free_quota="API 永久免费使用",
                tags=["zhipu", "glm", "free"]
            )
        ]

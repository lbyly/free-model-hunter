"""
Blazeai 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import BLAZEAI_API_KEY

logger = logging.getLogger(__name__)


class BlazeaiScraper(BaseScraper):
    provider_slug = "blazeai"

    async def scrape(self) -> list[ScrapedModel]:
        if not BLAZEAI_API_KEY:
            logger.warning("BLAZEAI_API_KEY 未配置，使用已知模型")
            return self._known_models()

        try:
            # 使用 verify=False 避免部分环境下 SSL UNEXPECTED_EOF_WHILE_READING 报错
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                resp = await client.get(
                    "https://blazeai.boxu.dev/api/models",
                    headers={
                        "Authorization": f"Bearer {BLAZEAI_API_KEY}",
                        "User-Agent": "FreeModelsHub/1.0",
                    }
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"blazeai API 请求失败: {e}, 使用已知模型降级")
            return self._known_models()

        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            
            # 过滤掉不可用或降级的模型，仅保留状态为 'healthy' 的活跃模型
            if item.get("status") != "healthy":
                continue
            
            # 外部 Blazeai 模型默认在该接口下均为免费使用
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=f"Owned by: {item.get('owned_by', 'blazeapi')}",
                model_type="chat",
                is_free=True,
                free_quota="Blazeai 免费接口",
                tags=["blazeai"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="grok-4.20-fast", name="grok-4.20-fast",
                         model_type="chat", is_free=True,
                         free_quota="Blazeai 免费接口", tags=["blazeai"]),
            ScrapedModel(model_id="kimi-k2.5-official", name="kimi-k2.5-official",
                         model_type="chat", is_free=True,
                         free_quota="Blazeai 免费接口", tags=["blazeai"]),
            ScrapedModel(model_id="qwen3.6-plus-preview-search", name="qwen3.6-plus-preview-search",
                         model_type="chat", is_free=True,
                         free_quota="Blazeai 免费接口", tags=["blazeai"]),
        ]

"""
NotDiamond 爬虫
使用官方 API: https://api.notdiamond.ai/v2/models
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel

logger = logging.getLogger(__name__)


class NotDiamondScraper(BaseScraper):
    provider_slug = "notdiamond"

    async def scrape(self) -> list[ScrapedModel]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.notdiamond.ai/v2/models",
                    headers={"User-Agent": "FreeModelsHub/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models_data = data.get("models", [])
                    if models_data:
                        return self._parse_models(models_data)
                logger.warning(f"notdiamond API 返回 {resp.status_code}")
        except Exception as e:
            logger.warning(f"notdiamond API 请求失败: {e}")

        # 降级：返回已知模型
        return self._known_models()

    def _parse_models(self, models_data: list) -> list[ScrapedModel]:
        models = []
        seen = set()
        for item in models_data:
            mid = item.get("model", "")
            if not mid or mid in seen:
                continue
            seen.add(mid)

            provider = item.get("provider", "unknown")
            context_length = item.get("context_length", 0)
            input_price = item.get("input_price", 0)
            output_price = item.get("output_price", 0)

            # 定价为 0 的模型视为免费
            is_free = (input_price == 0 and output_price == 0)

            tags = ["notdiamond"]
            if provider:
                tags.append(provider.lower())

            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=f"Provider: {provider} | Context: {context_length} | Input: ${input_price}/M tokens | Output: ${output_price}/M tokens",
                model_type="chat",
                is_free=is_free,
                context_window=str(context_length) if context_length else None,
                tags=tags,
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="notdiamond-router", name="NotDiamond Router",
                         model_type="chat", is_free=True,
                         free_quota="免费路由层（首1000次）",
                         tags=["notdiamond", "router"]),
            ScrapedModel(model_id="gpt-4o", name="GPT-4o",
                         model_type="chat", is_free=True,
                         free_quota="NotDiamond 免费路由", tags=["notdiamond", "openai"]),
            ScrapedModel(model_id="claude-3.5-sonnet", name="Claude 3.5 Sonnet",
                         model_type="chat", is_free=True,
                         free_quota="NotDiamond 免费路由", tags=["notdiamond", "anthropic"]),
            ScrapedModel(model_id="gemini-2.0-flash", name="Gemini 2.0 Flash",
                         model_type="chat", is_free=True,
                         free_quota="NotDiamond 免费路由", tags=["notdiamond", "google"]),
        ]
"""
Manifest 爬虫
使用官方 API: https://app.manifest.build/v1/models
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import MANIFEST_API_KEY

logger = logging.getLogger(__name__)


class ManifestScraper(BaseScraper):
    provider_slug = "manifest"
    chat_endpoint_base = "https://app.manifest.build/v1"
    chat_api_key = MANIFEST_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        if not self.chat_api_key:
            logger.warning("Manifest API Key 未配置，跳过爬取。")
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.chat_api_key}",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                resp = await client.get(
                    f"{self.chat_endpoint_base}/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models_data = data.get("data", [])
                    if models_data:
                        return self._parse_models(models_data)
                logger.warning(f"Manifest API 返回 {resp.status_code}")
        except Exception as e:
            logger.warning(f"Manifest API 请求失败: {e}")

        return []

    def _parse_models(self, models_data: list) -> list[ScrapedModel]:
        models = []
        allowed_owners = {"manifest", "cerebras", "groq", "mistral", "kiro"}
        
        for item in models_data:
            mid = item.get("id", "")
            if not mid:
                continue
            
            lower_mid = mid.lower()
            owner = item.get("owned_by", "").lower()
            
            # 初步过滤条件以减少 verify_free_models 发送 Hi 请求时的负担
            is_candidate = False
            if owner in allowed_owners:
                is_candidate = True
            elif "free" in lower_mid or "subscription" in lower_mid or "instant" in lower_mid:
                is_candidate = True
                
            if not is_candidate:
                continue

            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=f"Manifest ({owner}) model" if owner != "manifest" else "Manifest Routing Model",
                model_type="chat",
                is_free=False,  # 设为 False，由 verify_free_models 并发发送 Hi 验证连通性
                tags=["manifest", owner],
            ))
        return models

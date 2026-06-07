"""
Cerebras 爬虫 — 自动从 API 获取模型列表
"""
import httpx
from config import CEREBRAS_API_KEY
from .base import BaseScraper, ScrapedModel


class CerebrasScraper(BaseScraper):
    provider_slug = "cerebras"
    chat_endpoint_base = "https://api.cerebras.ai/v1"
    chat_api_key = CEREBRAS_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        models = []

        try:
            headers = {
                "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.cerebras.ai/v1/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "").strip()
                        if not mid:
                            continue
                        models.append(ScrapedModel(
                            model_id=mid,
                            name=mid,
                            model_type="chat",
                            is_free=False,
                            free_quota=None,
                            tags=["cerebras", "openai-compatible"],
                        ))
        except Exception as e:
            print(f"  [WARNING] Cerebras API 请求失败: {e}，使用已知模型降级")

        # 降级方案
        if not models:
            models = [
                ScrapedModel(model_id="gpt-oss-120b", name="GPT-OSS-120B",
                    model_type="chat", is_free=True,
                    free_quota="Cerebras 免费模型",
                    tags=["cerebras"],
                    rate_limits=[{"rate_type": "RPM", "limit_value": 30, "tier": "free"}]),
            ]

        return models
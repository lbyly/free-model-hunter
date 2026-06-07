"""
Zen API 爬虫 — 自动从 API 获取免费模型列表
"""
import httpx
from .base import BaseScraper, ScrapedModel


class ZenScraper(BaseScraper):
    provider_slug = "zen"

    async def scrape(self) -> list[ScrapedModel]:
        known_free = [
            ScrapedModel(model_id="zen-chat", name="Zen Chat",
                model_type="chat", is_free=True,
                free_quota="Zen API 免费层（速率限制）",
                tags=["zen"],
                rate_limits=[{"rate_type": "RPM", "limit_value": 20, "tier": "free"}]),
        ]

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://opencode.ai/zen/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "")
                        # 名称以 -free 结尾的为免费模型
                        if mid.endswith("-free"):
                            name = item.get("id", "")
                            known_free.append(ScrapedModel(
                                model_id=mid,
                                name=name,
                                model_type="chat",
                                is_free=True,
                                free_quota="Zen API 免费层",
                                tags=["zen", "openai-compatible"],
                                rate_limits=[{"rate_type": "RPM", "limit_value": 20, "tier": "free"}],
                            ))
        except Exception as e:
            print(f"  [WARNING] Zen API 请求失败: {e}，使用已知模型")

        return known_free

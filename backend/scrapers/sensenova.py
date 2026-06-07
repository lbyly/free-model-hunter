"""
商汤日日新 (SenseNova) 爬虫 — 从 OpenAI 兼容 API 获取模型列表
"""
import httpx
from .base import BaseScraper, ScrapedModel
from config import SENSENOVA_API_KEY


class SenseNovaScraper(BaseScraper):
    provider_slug = "sensenova"
    chat_endpoint_base = "https://token.sensenova.cn/v1"
    chat_api_key = SENSENOVA_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        models = []
        try:
            headers = {
                "Authorization": f"Bearer {SENSENOVA_API_KEY}",
                "User-Agent": "FreeModelsHub/1.0",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://token.sensenova.cn/v1/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "").strip()
                        if not mid:
                            continue
                        pricing = item.get("pricing", {})
                        is_free = pricing.get("prompt", "0") == "0"
                        context_length = item.get("context_length", 0)
                        desc = item.get("description", "")
                        ctx_str = f"{context_length//1024}K" if context_length else None
                        models.append(ScrapedModel(
                            model_id=mid,
                            name=item.get("name", mid),
                            description=desc,
                            model_type="chat",
                            is_free=is_free,
                            free_quota="免费" if is_free else None,
                            tags=["sensenova", "openai-compatible"],
                        ))
        except Exception as e:
            print(f"  [WARNING] SenseNova API 请求失败: {e}，使用默认模型")

        # 降级：API 失败时返回已知模型
        if not models:
            models = [
                ScrapedModel(model_id="sensenova-6.7-flash-lite",
                    name="SenseNova 6.7 Flash Lite",
                    description="轻量级多模态 Agent 模型",
                    model_type="chat", is_free=True,
                    free_quota="免费", tags=["sensenova"]),
                ScrapedModel(model_id="deepseek-v4-flash",
                    name="DeepSeek V4 Flash",
                    description="高速推理模型",
                    model_type="chat", is_free=True,
                    free_quota="免费", tags=["sensenova"]),
            ]
        return models

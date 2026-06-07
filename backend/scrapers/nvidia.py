"""
NVIDIA API 爬虫 — 从 OpenAI 兼容 API 获取模型列表
"""
import httpx
from .base import BaseScraper, ScrapedModel
from config import NVIDIA_API_KEY


class NvidiaScraper(BaseScraper):
    provider_slug = "nvidia"
    chat_endpoint_base = "https://integrate.api.nvidia.com/v1"
    chat_api_key = NVIDIA_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        models = []
        try:
            headers = {
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "User-Agent": "FreeModelsHub/1.0",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://integrate.api.nvidia.com/v1/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "").strip()
                        if not mid:
                            continue
                        owned_by = item.get("owned_by", "")
                        models.append(ScrapedModel(
                            model_id=mid,
                            name=mid.split("/")[-1] if "/" in mid else mid,
                            description=f"由 {owned_by} 提供" if owned_by else "",
                            model_type="chat",
                            is_free=False,
                            free_quota=None,
                            tags=["nvidia", "openai-compatible"],
                        ))
        except Exception as e:
            print(f"  [WARNING] NVIDIA API 请求失败: {e}，使用默认模型")

        # 降级：API 失败时返回已知模型
        if not models:
            models = [
                ScrapedModel(model_id="meta/llama-3.1-8b-instruct",
                    name="Llama 3.1 8B Instruct",
                    description="Meta 提供的 Llama 3.1 指令模型",
                    model_type="chat", is_free=False,
                    tags=["nvidia", "meta"]),
                ScrapedModel(model_id="mistralai/mistral-7b-instruct-v0.3",
                    name="Mistral 7B Instruct v0.3",
                    description="Mistral AI 提供的 7B 指令模型",
                    model_type="chat", is_free=False,
                    tags=["nvidia", "mistral"]),
            ]
        return models

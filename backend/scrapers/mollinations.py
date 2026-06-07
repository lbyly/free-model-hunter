"""
Mollinations.ai / Pollinations.ai 爬虫 — 自动从 API 获取模型列表
API: https://gen.pollinations.ai (公共 API，无需认证)
"""
import httpx
from .base import BaseScraper, ScrapedModel

# 根据 category 映射 model_type
CATEGORY_MAP = {
    "text": "chat",
    "image": "image",
    "video": "vision",
    "audio": "audio",
    "embedding": "embedding",
    "realtime": "chat",
}

# 根据 brand 映射 tags
BRAND_TAGS = {
    "OpenAI": "openai-compatible",
    "Google": "openai-compatible",
    "Anthropic": "openai-compatible",
    "Meta": "openai-compatible",
    "Mistral": "openai-compatible",
    "DeepSeek": "openai-compatible",
    "Qwen": "openai-compatible",
    "xAI": "openai-compatible",
    "MiniMax": "openai-compatible",
    "Moonshot AI": "openai-compatible",
    "Perplexity": "openai-compatible",
    "Amazon": "openai-compatible",
    "StepFun": "openai-compatible",
    "ByteDance": "openai-compatible",
    "Alibaba": "openai-compatible",
    "ElevenLabs": "openai-compatible",
    "AssemblyAI": "openai-compatible",
    "Black Forest Labs": "openai-compatible",
    "Lightricks": "openai-compatible",
    "Pruna": "openai-compatible",
    "ACE-Step": "openai-compatible",
    "Z.ai": "openai-compatible",
    "Pollinations": "openai-compatible",
}


class MollinationsScraper(BaseScraper):
    provider_slug = "mollinations"
    chat_endpoint_base = "https://gen.pollinations.ai/v1"
    # 公共 API，不需要 Key

    async def scrape(self) -> list[ScrapedModel]:
        models = []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://gen.pollinations.ai/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "").strip()
                        if not mid:
                            continue

                        # 判断模型类型
                        modalities = item.get("output_modalities", [])
                        mtype = "chat"
                        if "image" in modalities or "video" in modalities:
                            mtype = "image"
                        if "audio" in modalities:
                            mtype = "audio"
                        if "embedding" in modalities:
                            mtype = "embedding"

                        models.append(ScrapedModel(
                            model_id=mid,
                            name=mid,
                            model_type=mtype,
                            is_free=False,
                            free_quota=None,
                            tags=["mollinations", "pollinations", "openai-compatible"],
                        ))
        except Exception as e:
            print(f"  [WARNING] Pollinations API 请求失败: {e}，使用已知模型降级")

        # 降级方案
        if not models:
            models = [
                ScrapedModel(model_id="openai", name="OpenAI (Pollinations)",
                    model_type="chat", is_free=True,
                    free_quota="Pollinations.ai 免费 API",
                    tags=["mollinations", "pollinations"]),
                ScrapedModel(model_id="gemini", name="Gemini (Pollinations)",
                    model_type="chat", is_free=True,
                    free_quota="Pollinations.ai 免费 API",
                    tags=["mollinations", "pollinations"]),
                ScrapedModel(model_id="flux", name="Flux (Pollinations)",
                    model_type="image", is_free=True,
                    free_quota="Pollinations.ai 免费 API",
                    tags=["mollinations", "pollinations"]),
            ]

        return models

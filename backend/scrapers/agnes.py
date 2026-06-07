"""
Agnes AI 爬虫 — 从 API 自动获取免费模型列表
"""
import httpx
from .base import BaseScraper, ScrapedModel
from config import AGNES_API_KEY

# Agnes API 模型类型映射（根据 model_id 中的关键词）
MODEL_TYPE_MAP = {
    "image": "image",
    "video": "vision",
    "embed": "embedding",
    "code": "code",
}


class AgnesScraper(BaseScraper):
    provider_slug = "agnes"
    chat_endpoint_base = "https://apihub.agnes-ai.com/v1"
    chat_api_key = AGNES_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        models = []
        try:
            headers = {
                "Authorization": f"Bearer {AGNES_API_KEY}",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://apihub.agnes-ai.com/v1/models",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        mid = item.get("id", "").strip()
                        if not mid:
                            continue
                        # 根据模型 ID 判断类型
                        mid_lower = mid.lower()
                        mtype = "chat"
                        for kw, t in MODEL_TYPE_MAP.items():
                            if kw in mid_lower:
                                mtype = t
                                break
                        models.append(ScrapedModel(
                            model_id=mid,
                            name=mid,
                            model_type=mtype,
                            is_free=False,
                            free_quota=None,
                            tags=["agnes", "openai-compatible"],
                        ))
        except Exception as e:
            print(f"  [WARNING] Agnes API 请求失败: {e}，使用已知模型降级")

        # 降级：API 失败时返回已知模型
        if not models:
            models = [
                ScrapedModel(model_id="agnes-1.5-flash", name="Agnes 1.5 Flash",
                    model_type="chat", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes", "flash"]),
                ScrapedModel(model_id="agnes-2.0-flash", name="Agnes 2.0 Flash",
                    model_type="chat", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes", "flash"]),
                ScrapedModel(model_id="agnes-image-2.0-flash", name="Agnes Image 2.0 Flash",
                    model_type="image", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes", "image"]),
                ScrapedModel(model_id="agnes-image-2.1-flash", name="Agnes Image 2.1 Flash",
                    model_type="image", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes", "image"]),
                ScrapedModel(model_id="agnes-video-v2.0", name="Agnes Video V2.0",
                    model_type="vision", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes", "video"]),
                ScrapedModel(model_id="agnes-chat", name="Agnes Chat",
                    model_type="chat", is_free=True,
                    free_quota="Agnes AI 免费层",
                    tags=["agnes"]),
            ]

        return models

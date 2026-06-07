"""
Gemini (Google) 爬虫
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


class GeminiScraper(BaseScraper):
    provider_slug = "gemini"

    # Gemini 使用非 OpenAI 兼容端点（:generateContent），需 URL 模板
    chat_endpoint_template = None  # 在 __init_subclass__ 或类级别动态设置
    chat_api_key = GEMINI_API_KEY
    # Gemini 使用查询参数 ?key=xxx 传递 API 密钥，而非 Bearer 认证

    async def scrape(self) -> list[ScrapedModel]:
        # 优先使用 Gemini API 获取模型列表
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"gemini API 失败: {e}, 使用已知模型降级")
            return self._known_models()

    @classmethod
    def _init_chat_config(cls):
        """初始化 chat completion 测试配置（因 GEMINI_API_KEY 在 import 时才可用）"""
        cls.chat_endpoint_template = f"https://generativelanguage.googleapis.com/v1beta/models/{{model_id}}:generateContent?key={GEMINI_API_KEY}"
        cls.chat_extra_body = {
            "contents": [{"parts": [{"text": "Hi"}]}],
        }

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        """使用 Google Gemini API 获取模型列表"""
        # 确保 chat 测试配置已初始化
        self._init_chat_config()
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        if GEMINI_API_KEY:
            url += f"?key={GEMINI_API_KEY}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        models = []
        for item in data.get("models", []):
            mid = item.get("name", "").replace("models/", "")
            if not mid:
                continue
            supported = item.get("supportedGenerationMethods", [])
            model_type = "chat" if "generateContent" in supported else "embedding" if "embedContent" in supported else "other"
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type=model_type,
                is_free=False,
                free_quota=None,
                tags=["gemini", "google"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        """API 不可用时的降级方案"""
        known = [
            ("gemini-2.0-flash", "Gemini 2.0 Flash", "高速模型", "chat"),
            ("gemini-2.0-flash-lite", "Gemini 2.0 Flash Lite", "轻量高速模型", "chat"),
            ("gemini-2.0-pro-exp", "Gemini 2.0 Pro Exp", "实验版 Pro 模型", "chat"),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", "上一代高速模型", "chat"),
            ("gemini-1.5-pro", "Gemini 1.5 Pro", "上一代 Pro 模型", "chat"),
            ("gemini-2.0-flash-exp-image-generation", "Gemini 2.0 Flash Image Gen", "图像生成模型", "image"),
            ("text-embedding-004", "Text Embedding 004", "文本嵌入模型", "embedding"),
        ]
        return [
            ScrapedModel(model_id=mid, name=name, description=desc,
                         model_type=mtype, is_free=True,
                         free_quota="Gemini API 免费层：每分钟60次",
                         tags=["gemini", "google"],
                         rate_limits=[{"rate_type": "RPM", "limit_value": 60, "tier": "free"}])
            for mid, name, desc, mtype in known
        ]
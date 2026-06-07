"""
GitHub Models (Kilo) 爬虫
"""
import asyncio
import logging
from .base import BaseScraper, ScrapedModel

logger = logging.getLogger(__name__)


class GitHubModelsScraper(BaseScraper):
    provider_slug = "github_models"

    async def scrape(self) -> list[ScrapedModel]:
        """
        使用 httpx 直接调用 GitHub API 获取模型列表，
        避免 Playwright 在 Windows/Python3.13 上的兼容性问题。
        """
        import httpx
        models = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                # GitHub Marketplace Models API (公开数据)
                resp = await client.get(
                    "https://api.github.com/marketplace/models",
                    headers={
                        "User-Agent": "FreeModelsHub/1.0",
                        "Accept": "application/vnd.github+json",
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data if isinstance(data, list) else data.get("models", data.get("data", [])):
                        mid = item.get("id", "") or item.get("name", "")
                        if not mid:
                            continue
                        models.append(ScrapedModel(
                            model_id=str(mid),
                            name=item.get("name", str(mid)),
                            description=item.get("description", ""),
                            model_type="chat",
                            is_free=False,
                            free_quota=None,
                            context_window=str(item.get("context_window", "")) if item.get("context_window") else None,
                            tags=["github"],
                        ))
                    if models:
                        return models
            except Exception as e:
                logger.warning(f"github_models API 失败, 降级到已知模型列表: {e}")

            # API 降级：返回已知的 GitHub Models 免费模型
            known_models = [
                ("gpt-4o-mini", "GPT-4o Mini", "轻量级 GPT-4o 模型"),
                ("gpt-4o", "GPT-4o", "多模态 GPT-4o 模型"),
                ("o1-mini", "O1 Mini", "推理模型 Mini"),
                ("o1-preview", "O1 Preview", "推理模型预览版"),
                ("o3-mini", "O3 Mini", "最新推理模型 Mini"),
                ("claude-3.5-sonnet", "Claude 3.5 Sonnet", "Anthropic 中端模型"),
                ("claude-3.5-haiku", "Claude 3.5 Haiku", "Anthropic 轻量模型"),
                ("claude-3-opus", "Claude 3 Opus", "Anthropic 旗舰模型"),
                ("gemini-2.0-flash", "Gemini 2.0 Flash", "Google 高速模型"),
                ("gemini-2.0-flash-lite", "Gemini 2.0 Flash Lite", "Google 轻量模型"),
                ("deepseek-chat", "DeepSeek Chat", "DeepSeek 对话模型"),
                ("codestral-latest", "Codestral", "Mistral 代码模型"),
                ("mistral-large", "Mistral Large", "Mistral 旗舰模型"),
                ("llama-3.2-3b", "Llama 3.2 3B", "Meta 轻量模型"),
                ("llama-3.2-11b", "Llama 3.2 11B", "Meta 多模态模型"),
                ("llama-3.3-70b", "Llama 3.3 70B", "Meta 旗舰模型"),
                ("phi-3.5-mini", "Phi 3.5 Mini", "Microsoft 轻量模型"),
                ("phi-4", "Phi 4", "Microsoft 最新模型"),
            ]
            for mid, name, desc in known_models:
                models.append(ScrapedModel(
                    model_id=mid, name=name, description=desc,
                    model_type="chat", is_free=True,
                    free_quota="GitHub Copilot 免费层可用",
                    tags=["github"],
                ))

        return models

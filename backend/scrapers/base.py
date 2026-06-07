"""
爬虫基类 - 所有 Provider 爬虫的抽象接口
"""
import asyncio
import httpx
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ScrapedModel:
    """爬虫返回的模型数据结构"""
    model_id: str                    # 唯一模型ID，如 "deepseek-chat"
    name: str = ""                   # 显示名称
    description: str = ""
    model_type: str = "chat"         # chat / embedding / image / code
    is_free: bool = False
    free_quota: Optional[str] = None # "每日100次" / "限量100万token"
    pricing_url: Optional[str] = None
    context_window: Optional[str] = None  # "128K" / "32K"
    tags: list = field(default_factory=list)
    status: str = "active"
    rate_limits: list = field(default_factory=list)
    # rate_limits 示例: [{"rate_type": "RPM", "limit_value": 60, "tier": "free"}]

    def to_dict(self) -> dict:
        return asdict(self)


# 并发测试信号量，限制同时最多 10 个请求
_CHAT_TEST_SEMAPHORE = asyncio.Semaphore(10)

# 不参与 chat completion 测试的模型类型
_NON_CHAT_PREFIXES = ("embedding", "rerank", "moderation", "tts", "whisper")


class BaseScraper(ABC):
    """所有爬虫的抽象基类"""

    @property
    @abstractmethod
    def provider_slug(self) -> str:
        """返回提供商标识符，如 'siliconflow'"""
        pass

    # === Chat Completion 免费验证配置（子类可覆盖） ===
    chat_endpoint_base: Optional[str] = None
    """OpenAI 兼容的 chat completions 端点基础 URL，如 'https://api.siliconflow.cn/v1'"""

    chat_api_key: Optional[str] = None
    """用于 chat completion 请求的 API Key，None 表示无需认证"""

    chat_extra_headers: Optional[dict] = None
    """额外的请求头，如 Gemini 需要用 query param 传递 key"""

    chat_extra_body: Optional[dict] = None
    """额外的请求体字段，如 Gemini 的 generationConfig"""

    @abstractmethod
    async def scrape(self) -> list[ScrapedModel]:
        """
        爬取官网并返回模型列表。
        子类需自行处理：反爬、JS渲染、异常捕获等。
        """
        pass

    chat_endpoint_template: Optional[str] = None
    """用于非 OpenAI 兼容端点的 URL 模板，如 'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key=xxx'"""

    def _build_chat_url(self, model_id: str) -> Optional[str]:
        """构造 chat completion 请求 URL"""
        if self.chat_endpoint_template:
            return self.chat_endpoint_template.replace("{model_id}", model_id)
        if self.chat_endpoint_base:
            return f"{self.chat_endpoint_base}/chat/completions"
        return None

    async def _test_single_model(self, client: httpx.AsyncClient, model_id: str) -> bool:
        """向指定模型发送 'Hi'，若能返回消息体则返回 True"""
        url = self._build_chat_url(model_id)
        if not url:
            return False
        # 过滤非 chat 类模型
        if model_id.startswith(_NON_CHAT_PREFIXES):
            return False
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self.chat_api_key and not self.chat_extra_headers:
                headers["Authorization"] = f"Bearer {self.chat_api_key}"
            if self.chat_extra_headers:
                headers.update(self.chat_extra_headers)

            # 对于非 OpenAI 兼容端点（如 Gemini），使用 chat_extra_body 作为完整请求体
            if self.chat_endpoint_template and self.chat_extra_body:
                body = self.chat_extra_body
            else:
                body = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                }
                if self.chat_extra_body:
                    body.update(self.chat_extra_body)

            async with _CHAT_TEST_SEMAPHORE:
                resp = await client.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=10,
                )

            if resp.status_code == 200:
                data = resp.json()
                # OpenAI 兼容格式：有 choices + message 就算通过
                choices = data.get("choices")
                if choices and len(choices) > 0:
                    msg = choices[0].get("message", {})
                    # 有些 API（如 Cerebras）返回 reasoning 而非 content
                    if msg.get("content") or msg.get("reasoning") or msg.get("role") == "assistant":
                        return True
                # Gemini 格式：有 candidates + parts 就算通过
                candidates = data.get("candidates")
                if candidates and len(candidates) > 0:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and any(p.get("text") for p in parts):
                        return True
            return False
        except Exception:
            return False

    async def verify_free_models(self, models: list[ScrapedModel]) -> list[ScrapedModel]:
        """
        对每个模型发送 'Hi' 测试，仅保留能正常响应的模型并标记 is_free=True。
        不响应的模型直接删除（不展示给用户）。
        """
        if not (self.chat_endpoint_base or self.chat_endpoint_template) or not models:
            return models

        # 跳过已确认免费的模型（来自 pricing API 等更可靠的判断）
        already_free = [m for m in models if m.is_free]
        to_test = [m for m in models if not m.is_free]

        if not to_test:
            return models

        async with httpx.AsyncClient(timeout=10) as client:
            tasks = [self._test_single_model(client, m.model_id) for m in to_test]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        verified = list(already_free)
        for idx, ok in enumerate(results):
            if isinstance(ok, bool) and ok:
                to_test[idx].is_free = True
                verified.append(to_test[idx])
            # 不响应的模型直接丢弃，不加入 verified

        removed_count = len(to_test) - sum(1 for r in results if isinstance(r, bool) and r)
        if removed_count > 0:
            print(f"  [INFO] {self.provider_slug}: 发送 'Hi' 测试了 {len(to_test)} 个模型，"
                  f"{sum(1 for r in results if isinstance(r, bool) and r)} 个有回应（标记免费），"
                  f"{removed_count} 个无回应（已删除）")

        return verified

    async def run(self) -> tuple[bool, list[ScrapedModel], str]:
        """
        标准执行入口。
        先爬取模型列表，再通过 chat completion 测试验证免费状态。
        返回: (是否成功, 模型列表, 错误信息)
        """
        try:
            models = await self.scrape()
            if self.chat_endpoint_base or self.chat_endpoint_template:
                models = await self.verify_free_models(models)
            return (True, models, "")
        except Exception as e:
            return (False, [], str(e))

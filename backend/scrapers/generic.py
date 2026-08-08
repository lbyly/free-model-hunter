"""
通用 OpenAI 兼容爬虫 (Generic)

对新增的、使用 OpenAI 兼容 /v1/models 接口的 provider，无需手写专属爬虫文件。
只要 provider 在数据库中配置了 scrape_url（形如 https://xxx/v1/models），
get_scraper() 找不到专属爬虫时就会回退到本通用爬虫，从 DB 读取该 provider 的
scrape_url / api_key 动态拉取模型。

注意：本类不通过 discover_scrapers 自动注册（它没有固定的 provider_slug），
由 get_scraper() 按需实例化。
"""
import httpx
import logging

from .base import BaseScraper, ScrapedModel
from config import get_api_key_for_slug

logger = logging.getLogger(__name__)


class GenericOpenAIScraper(BaseScraper):
    # 不设置固定 provider_slug —— 以实例化时传入的 slug 为准
    provider_slug = None

    def __init__(self, slug: str, scrape_url: str = None):
        super().__init__()
        self.provider_slug = slug
        self._scrape_url = scrape_url
        # 不设置 chat_endpoint_base —— 通用爬虫回退到中转站时，
        # /models 返回的 is_free 字段即为最终付费状态，不应再触发
        # verify_free_models 的 Hi 免费验证（会导致模型因测试失败被全删）。
        self.chat_endpoint_base = None
        self.chat_endpoint_template = None

    @property
    def chat_api_key(self):
        return get_api_key_for_slug(self.provider_slug)

    async def scrape(self) -> list[ScrapedModel]:
        if not self._scrape_url:
            logger.warning(f"[generic:{self.provider_slug}] 未配置 scrape_url，跳过")
            return []

        # OpenAI 兼容端点通常为 {base}/models；scrape_url 若没带 /models 则自动拼接
        url = self._scrape_url.rstrip("/")
        if not url.endswith("/models"):
            url += "/models"

        headers = {"User-Agent": "FreeModelsHub/1.0"}
        api_key = self.chat_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"[generic:{self.provider_slug}] API 请求失败: {e}")
            return []

        # OpenAI 兼容 /models 返回 {"object":"list","data":[{id,...}]}
        items = data.get("data", []) if isinstance(data, dict) else data or []
        if not isinstance(items, list):
            logger.warning(f"[generic:{self.provider_slug}] 无法识别的响应结构")
            return []

        models = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            mid = item.get("model_id") or item.get("id", "")
            if not mid or mid in seen:
                continue
            seen.add(mid)

            # 一些中转站会标 available=false 的下架模型，跳过
            if item.get("available") is False:
                continue

            # model_type: chat/embedding/image/code
            mtype = item.get("type", "") or "chat"
            if mtype not in ("chat", "embedding", "image", "code", "reasoning", "vision", "audio", "rerank", "reranker"):
                mtype = "chat"

            ctx = item.get("context_window") or item.get("context_length")
            # 中转聚合站的模型默认收录；响应若自带 is_free 则采用，否则默认 True
            _is_free = item.get("is_free")
            _is_free = True if _is_free is None else bool(_is_free)
            models.append(ScrapedModel(
                model_id=mid,
                name=item.get("name") or item.get("id", mid),
                description=item.get("description", ""),
                model_type=mtype,
                is_free=_is_free,
                context_window=str(ctx) if ctx else None,
                tags=[self.provider_slug],
                free_quota=item.get("free_quota"),
            ))

        logger.info(f"[generic:{self.provider_slug}] 爬取到 {len(models)} 个模型")
        return models
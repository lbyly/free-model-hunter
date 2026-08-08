"""
CF-Gateway-Free 专属爬虫

Cloudflare Workers AI 网关的 /v1/models 会返回数千个模型，但免费网关实际
可用的只有一个：workers-ai/@cf/openai/gpt-oss-120b。
因此这里不调用 /models 全量接口，直接返回已知可用模型列表（已人工验证）。
"""
import logging
from .base import BaseScraper, ScrapedModel

logger = logging.getLogger(__name__)


class CfGatewayFreeScraper(BaseScraper):
    provider_slug = "cf_gateway_free"

    async def scrape(self) -> list[ScrapedModel]:
        # 仅返回人工验证过可用的模型
        return [
            ScrapedModel(
                model_id="workers-ai/@cf/openai/gpt-oss-120b",
                name="GPT-OSS-120B (Workers AI)",
                description="Cloudflare Workers AI 免费网关可用模型",
                model_type="chat",
                is_free=True,
                free_quota="Cloudflare Workers AI 免费额度",
                tags=["cf_gateway_free", "cloudflare", "workers-ai"],
            ),
        ]

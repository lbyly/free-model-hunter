"""
X.ai (xAI) 爬虫
- 支持 DNS-over-HTTPS 绕过 DNS 污染
- 使用 socket.getaddrinfo patch 实现无感 DNS 劫持
- 回退到已知模型列表
"""
import httpx
import logging
from .base import BaseScraper, ScrapedModel
from config import XAI_API_KEY
from doh_resolver import dns_patch

logger = logging.getLogger(__name__)

# DoH 解析缓存（避免每次请求都解析）
_doh_resolved_ip: str | None = None


async def _resolve_api_xai():
    """通过 DoH 解析 api.x.ai 的真实 IP，绕过 DNS 污染"""
    global _doh_resolved_ip
    if _doh_resolved_ip:
        return _doh_resolved_ip

    doh_endpoints = [
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/dns-query",
    ]

    for endpoint in doh_endpoints:
        try:
            params = {"name": "api.x.ai", "type": "A"}
            headers = {"Accept": "application/dns-json"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(endpoint, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            for answer in data.get("Answer", []):
                if answer.get("type") == 1:  # A 记录
                    ip = answer.get("data", "")
                    if ip:
                        _doh_resolved_ip = ip
                        logger.info(f"DoH 解析 api.x.ai -> {ip}")
                        return ip
        except Exception as e:
            logger.warning(f"DoH {endpoint} 解析失败: {e}")
            continue

    logger.warning("所有 DoH 端点解析 api.x.ai 失败，回退到系统 DNS")
    return None


class XaiScraper(BaseScraper):
    provider_slug = "xai"
    chat_endpoint_base = "https://api.x.ai/v1"
    chat_api_key = XAI_API_KEY

    async def scrape(self) -> list[ScrapedModel]:
        try:
            return await self._scrape_via_api()
        except Exception as e:
            logger.warning(f"xAI API 请求失败 ({type(e).__name__}: {e})，使用已知模型")
            return self._known_models()

    async def _scrape_via_api(self) -> list[ScrapedModel]:
        headers = {
            "User-Agent": "FreeModelsHub/1.0",
            "Accept": "application/json",
        }
        if XAI_API_KEY:
            headers["Authorization"] = f"Bearer {XAI_API_KEY}"

        # 1. 先通过 DoH 解析真实 IP
        real_ip = await _resolve_api_xai()

        # 2. 使用 DNS Patch：劫持 socket.getaddrinfo
        #    httpx 请求 api.x.ai 时走 DoH 解析的正确 IP
        #    SSL SNI/Host 仍为 api.x.ai，证书验证通过
        host_to_ip = {}
        if real_ip:
            host_to_ip["api.x.ai"] = real_ip

        with dns_patch(host_to_ip):
            try:
                async with httpx.AsyncClient(timeout=15, verify=True) as client:
                    resp = await client.get(
                        "https://api.x.ai/v1/models",
                        headers=headers,
                    )
                    if resp.status_code == 400 and XAI_API_KEY:
                        logger.warning("xAI API 返回 400，使用已知模型")
                        return self._known_models()
                    resp.raise_for_status()
                    data = resp.json()
                return self._parse_models(data)
            except Exception as e:
                logger.warning(f"xAI API 请求失败 ({type(e).__name__}: {e})，回退到已知模型")
                raise

    def _parse_models(self, data: dict) -> list[ScrapedModel]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            models.append(ScrapedModel(
                model_id=mid,
                name=mid,
                description=item.get("description", ""),
                model_type="chat",
                is_free=False,
                free_quota=None,
                tags=["xai", "x.ai"],
            ))
        return models

    def _known_models(self) -> list[ScrapedModel]:
        return [
            ScrapedModel(model_id="grok-3", name="Grok 3",
                         model_type="chat", is_free=True,
                         free_quota="xAI 免费层", tags=["xai", "x.ai", "grok"]),
            ScrapedModel(model_id="grok-3-mini", name="Grok 3 Mini",
                         model_type="chat", is_free=True,
                         free_quota="xAI 免费层", tags=["xai", "x.ai", "grok"]),
            ScrapedModel(model_id="grok-2", name="Grok 2",
                         model_type="chat", is_free=True,
                         free_quota="xAI 免费层", tags=["xai", "x.ai", "grok"]),
            ScrapedModel(model_id="grok-2-vision", name="Grok 2 Vision",
                         model_type="chat", is_free=True,
                         free_quota="xAI 免费层", tags=["xai", "x.ai", "grok"]),
        ]

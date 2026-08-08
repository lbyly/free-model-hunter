"""
爬虫自动发现与注册机制 (Uvicorn Reload Triggered)
"""
import importlib
import pkgutil
from typing import Optional

from .base import BaseScraper

_scraper_registry: dict[str, type[BaseScraper]] = {}
_initialized = False


def discover_scrapers():
    """自动发现并注册所有 Scraper 类"""
    global _initialized
    if _initialized:
        return

    package_path = __path__[0]
    # generic 模块是回退爬虫（需传入 slug，不参与无参自动发现）
    for importer, modname, ispkg in pkgutil.iter_modules([package_path]):
        if modname in ("base", "__init__", "generic"):
            continue
        module = importlib.import_module(f".{modname}", __package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, BaseScraper) and
                attr is not BaseScraper):
                instance = attr()
                _scraper_registry[instance.provider_slug] = attr
                # 验证 provider_slug 不为空
                if not instance.provider_slug:
                    raise ValueError(f"Scraper {modname}.{attr_name} 的 provider_slug 为空")

    _initialized = True
    print(f"  [OK] 已自动发现 {len(_scraper_registry)} 个爬虫: {list(_scraper_registry.keys())}")


def get_scraper(slug: str) -> Optional[BaseScraper]:
    """根据 slug 获取爬虫实例"""
    discover_scrapers()
    # 冻结 provider：直接返回 FreezeScraper（DB 保留清单），优先级最高，
    # 避免 manifest.py / nvidia.py 等既有专属爬虫或通用爬虫重新拉全量
    try:
        from .freeze import FROZEN_SLUGS, FreezeScraper
        if slug in FROZEN_SLUGS:
            return FreezeScraper(slug)
    except Exception:
        pass
    cls = _scraper_registry.get(slug)
    if cls:
        return cls()
    # 专属爬虫不存在时，若 provider 配置了 OpenAI 兼容 scrape_url，回退到通用爬虫
    try:
        from database import get_connection
        with get_connection() as conn:
            conn.row_factory = None
            row = conn.execute(
                "SELECT scrape_url FROM providers WHERE slug = ?", (slug,)
            ).fetchone()
            if row and row[0]:
                from .generic import GenericOpenAIScraper
                return GenericOpenAIScraper(slug, row[0])
    except Exception:
        pass
    return None


def get_all_scrapers() -> dict[str, type[BaseScraper]]:
    """获取所有爬虫类"""
    discover_scrapers()
    return dict(_scraper_registry)

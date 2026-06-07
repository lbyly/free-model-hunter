"""
爬虫自动发现与注册机制
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
    for importer, modname, ispkg in pkgutil.iter_modules([package_path]):
        if modname in ("base", "__init__"):
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
    cls = _scraper_registry.get(slug)
    return cls() if cls else None


def get_all_scrapers() -> dict[str, type[BaseScraper]]:
    """获取所有爬虫类"""
    discover_scrapers()
    return dict(_scraper_registry)

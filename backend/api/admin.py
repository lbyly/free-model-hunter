"""
Admin API 路由（手动触发爬取等管理功能）
"""
import time
import asyncio
from fastapi import APIRouter, HTTPException
from models.repository import (
    get_all_providers,
    upsert_models,
    log_scrape,
    export_data_json,
    import_data_json,
    backup_local_database,
)
from scrapers import get_scraper, discover_scrapers

router = APIRouter(prefix="/api", tags=["admin"])


@router.post("/refresh")
async def refresh_all():
    """手动触发全量刷新"""
    discover_scrapers()
    providers = get_all_providers(active_only=True)
    results = {}
    total_models = 0

    for provider in providers:
        scraper = get_scraper(provider["slug"])
        if not scraper:
            results[provider["slug"]] = {
                "success": False,
                "error": "Scraper not found",
                "count": 0,
            }
            continue

        start = time.time()
        try:
            success, models, error = await scraper.run()
            duration = time.time() - start

            if success:
                model_dicts = [m.to_dict() for m in models]
                count = upsert_models(provider["id"], model_dicts)
                log_scrape(provider["id"], "success", count, duration=duration)
                total_models += count
                results[provider["slug"]] = {"success": True, "count": count}
            else:
                log_scrape(provider["id"], "failed", 0, error, duration)
                results[provider["slug"]] = {"success": False, "error": error, "count": 0}
        except Exception as e:
            duration = time.time() - start
            log_scrape(provider["id"], "failed", 0, str(e), duration)
            results[provider["slug"]] = {"success": False, "error": str(e), "count": 0}

    return {
        "success": True,
        "message": f"全量刷新完成，共获取 {total_models} 个模型",
        "total_models": total_models,
        "results": results,
    }


@router.post("/refresh/{slug}")
async def refresh_provider(slug: str):
    """手动触发单个 Provider 刷新"""
    from models.repository import get_provider_by_slug

    provider = get_provider_by_slug(slug)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{slug}' not found")

    discover_scrapers()
    scraper = get_scraper(slug)
    if not scraper:
        raise HTTPException(status_code=500, detail=f"Scraper for '{slug}' not found")

    start = time.time()
    try:
        success, models, error = await scraper.run()
        duration = time.time() - start

        if success:
            model_dicts = [m.to_dict() for m in models]
            count = upsert_models(provider["id"], model_dicts)
            log_scrape(provider["id"], "success", count, duration=duration)
            return {"success": True, "provider": slug, "count": count}
        else:
            log_scrape(provider["id"], "failed", 0, error, duration)
            raise HTTPException(status_code=500, detail=f"Scrape failed: {error}")
    except HTTPException:
        raise
    except Exception as e:
        duration = time.time() - start
        log_scrape(provider["id"], "failed", 0, str(e), duration)
        raise HTTPException(status_code=500, detail=f"Scrape error: {str(e)}")


@router.get("/scrape-logs")
async def get_scrape_logs(limit: int = 50):
    """获取最近的爬取日志"""
    from database import get_db

    with get_db() as db:
        rows = db.execute(
            """SELECT sl.*, p.name as provider_name, p.slug as provider_slug
               FROM scrape_logs sl
               JOIN providers p ON sl.provider_id = p.id
               ORDER BY sl.scraped_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return {"logs": [dict(r) for r in rows]}


@router.get("/backup/export")
async def export_backup():
    """导出所有提供商和模型配置数据"""
    try:
        data = export_data_json()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出数据失败: {str(e)}")


@router.post("/backup/import")
async def import_backup(data: dict):
    """导入提供商和模型配置数据"""
    try:
        stats = import_data_json(data)
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入数据失败: {str(e)}")


@router.post("/backup/local")
async def local_backup():
    """在服务器本地备份 SQLite 数据库文件"""
    try:
        filename = backup_local_database()
        return {"success": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"本地备份失败: {str(e)}")

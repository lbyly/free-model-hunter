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
    import logging
    logger = logging.getLogger(__name__)

    provider = get_provider_by_slug(slug)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{slug}' not found")

    discover_scrapers()
    scraper = get_scraper(slug)
    if not scraper:
        raise HTTPException(status_code=500, detail=f"Scraper for '{slug}' not found")

    start = time.time()
    try:
        logger.info(f"Starting scraper for {slug}...")
        success, models, error = await scraper.run()
        duration = time.time() - start
        logger.info(f"Scraper {slug} run result: success={success}, count={len(models)}, error={error}")

        if success:
            model_dicts = [m.to_dict() for m in models]
            count = upsert_models(provider["id"], model_dicts)
            log_scrape(provider["id"], "success", count, duration=duration)
            logger.info(f"Upsert models for {slug} completed with count={count}")
            return {"success": True, "provider": slug, "count": count}
        else:
            log_scrape(provider["id"], "failed", 0, error, duration)
            raise HTTPException(status_code=500, detail=f"Scrape failed: {error}")
    except HTTPException:
        raise
    except Exception as e:
        duration = time.time() - start
        log_scrape(provider["id"], "failed", 0, str(e), duration)
        logger.error(f"Scrape error for {slug}: {e}", exc_info=True)
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

@router.post("/import-pa-models")
async def import_pa_models(data: dict):
    """导入 Page Assist 导出的模型清单，重算全库 user_removed（provider 级匹配）：
    对应 PA 提供商清单中有的模型 -> 可见(0)，其余（含无对应 PA 提供商的 FMH 提供商）-> 隐藏(1)。
    请求体: {"content": "<md文本>"} 或 {"model_ids_by_provider": {"Manifest": [...], ...}}；
    都不传时自动读取 D:/syncthing backup/重要备份 下最新的 page-assist-all-models-*.md。
    """
    import re
    import glob
    import os
    from models.repository import apply_pa_removed

    content = data.get("content") or ""
    model_ids_by_provider = data.get("model_ids_by_provider") or {}
    source = "upload"

    if not content and not model_ids_by_provider:
        base = r"D:\syncthing backup\重要备份"
        files = glob.glob(os.path.join(base, "page-assist-all-models-*.md"))
        if not files:
            raise HTTPException(
                status_code=400,
                detail=f"未提供文件内容，且目录 {base} 下未找到 page-assist-all-models-*.md",
            )
        latest = max(files, key=os.path.getmtime)
        content = open(latest, "r", encoding="utf-8").read()
        source = f"auto:{os.path.basename(latest)}"

    if not model_ids_by_provider:
        # 按章节解析 MD：## 提供商名 (N) 下的「原始模型ID」
        current = None
        for line in content.splitlines():
            m = re.match(r"^##\s+(.+?)\s+\(\d+\)", line)
            if m:
                current = m.group(1).strip()
                model_ids_by_provider.setdefault(current, [])
                continue
            m2 = re.search(r"\*\*原始模型ID\*\*:\s*`([^`]+)`", line)
            if m2 and current:
                model_ids_by_provider[current].append(m2.group(1).strip())

    total_ids = sum(len(v) for v in model_ids_by_provider.values())
    if not total_ids:
        raise HTTPException(status_code=400, detail="未能从文件中解析到任何模型 ID，请确认是 Page Assist 导出的 MD 清单")

    try:
        result = apply_pa_removed(model_ids_by_provider)
        return {"success": True, "pa_count": total_ids, "source": source, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")

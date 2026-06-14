"""
APScheduler 定时任务
"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SCHEDULE_HOURS

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def refresh_job():
    """定时刷新所有 Provider"""
    logger.info(f"[{datetime.now()}] 开始定时刷新所有 Provider")

    # 延迟导入避免循环依赖
    from scrapers import discover_scrapers
    from models.repository import get_all_providers, upsert_models, log_scrape
    from scrapers import get_scraper
    import time

    discover_scrapers()
    providers = get_all_providers(active_only=True)

    for provider in providers:
        scraper = get_scraper(provider["slug"])
        if not scraper:
            continue

        start = time.time()
        try:
            success, models, error = await scraper.run()
            duration = time.time() - start
            if success:
                model_dicts = [m.to_dict() for m in models]
                count = upsert_models(provider["id"], model_dicts)
                log_scrape(provider["id"], "success", count, duration=duration)
                logger.info(f"  ✅ {provider['slug']}: {count} models")
            else:
                log_scrape(provider["id"], "failed", 0, error, duration)
                logger.warning(f"  ❌ {provider['slug']}: {error}")
        except Exception as e:
            logger.error(f"  💥 {provider['slug']}: {str(e)}")

    logger.info(f"[{datetime.now()}] 定时刷新完成")


def start_scheduler():
    """启动定时任务"""
    hours = [h.strip() for h in SCHEDULE_HOURS.split(",")]

    # 添加定时任务，每天指定时间执行
    for hour in hours:
        scheduler.add_job(
            refresh_job,
            CronTrigger(hour=hour, minute="0", timezone="Asia/Shanghai"),
            id=f"refresh_{hour}h",
            replace_existing=True,
        )
        logger.info(f"  已添加定时任务: 每天 {hour}:00 (北京时间)")

    # 启动时立即执行一次
    scheduler.add_job(
        refresh_job,
        trigger="date",
        id="initial_refresh",
        next_run_time=datetime.now(),
        replace_existing=True,
    )

    # 添加每周日凌晨3点的测试与同步任务
    scheduler.add_job(
        weekly_test_and_sync_job,
        CronTrigger(day_of_week='sun', hour=3, minute=0, timezone="Asia/Shanghai"),
        id="weekly_test_and_sync",
        replace_existing=True,
    )
    logger.info("  已添加每周任务: 每周日 3:00 测试模型并同步到客户端")

    scheduler.start()
    logger.info("定时调度器已启动")

async def weekly_test_and_sync_job():
    """每周全面测试所有模型，并同步到客户端配置"""
    logger.info(f"[{datetime.now()}] 开始每周全量测试与同步任务")
    
    # 1. 运行常规爬取和连通性测试 (类似 refresh_job)
    await refresh_job()
    
    # 2. 将结果同步到 Hermes 和 Openclaw
    logger.info("测试完成，开始同步到本地客户端配置...")
    try:
        from sync_configs import sync_to_clients
        sync_to_clients()
    except Exception as e:
        logger.error(f"同步到客户端失败: {e}")
        
    logger.info(f"[{datetime.now()}] 每周全量测试与同步任务完成")


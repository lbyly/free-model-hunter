"""
Free Models Hub - 后端入口
"""
import sys
import os
import logging
import asyncio
import platform
from contextlib import asynccontextmanager

# Windows 兼容性：修复 Python 3.13+ asyncio 子进程问题
# Python 3.13 移除了 ProactorEventLoopPolicy 的子进程支持，
# 需要使用 SelectorEventLoopPolicy 来支持 Playwright
if platform.system() == "Windows":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        # 回退到默认策略
        pass

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from database import init_db, migrate_schema
from models.repository import seed_providers, classify_all_models
from scrapers import discover_scrapers
from scheduler import start_scheduler

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    logger.info("🚀 Free Models Hub 后端启动中...")

    # 1. 初始化数据库
    logger.info("📦 初始化数据库...")
    init_db()
    seed_providers()

    # 2. 数据库迁移（添加新字段）
    logger.info("🔄 数据库 Schema 迁移...")
    try:
        migrate_schema()
    except Exception as e:
        logger.warning(f"  Schema 迁移跳过: {e}")

    # 3. 自动发现爬虫
    logger.info("🔍 自动发现爬虫...")
    discover_scrapers()

    # 4. 对现有模型进行分类
    logger.info("🏷️ 对现有模型进行分类...")
    try:
        stats = classify_all_models()
        tiers_str = ", ".join([f"T{t}={stats['by_tier'].get(t, 0)}" for t in [1, 2, 3]])
        use_cases_str = ", ".join([f"{k}={v}" for k, v in stats["by_use_case"].items()])
        logger.info(f"  分类完成: 共 {stats['total']} 个模型 | 能力分级: {tiers_str} | 用途: {use_cases_str}")
    except Exception as e:
        logger.warning(f"  模型分类跳过: {e}")

    # 5. 启动定时任务
    logger.info("⏰ 启动定时调度器...")
    start_scheduler()

    logger.info("✅ Free Models Hub 后端启动完成!")
    yield

    # 关闭
    logger.info("🛑 Free Models Hub 后端关闭")


app = FastAPI(
    title="Free Models Hub API",
    description="AI 免费模型聚合平台 - 自动爬取各 AI 提供商的免费模型信息",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置 - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
from api.providers import router as providers_router
from api.models import router as models_router
from api.admin import router as admin_router
from api.hermes_catalog import router as hermes_router

app.include_router(providers_router)
app.include_router(models_router)
app.include_router(admin_router)
app.include_router(hermes_router)


# 前端页面
@app.get("/", response_class=HTMLResponse)
async def root():
    """返回前端页面 index.html"""
    import os
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(index_path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

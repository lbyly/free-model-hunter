"""
上下文 (Context) / MaxTokens 同步 API 路由

端点：
  POST /api/context/sync       触发上下文同步（从数据源获取并写回 FMH 数据库）
  GET  /api/context/coverage   查询上下文填充覆盖率
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/context", tags=["context"])


@router.post("/sync")
async def context_sync(
    use_dev_cache: bool = Query(True, description="是否使用 Hermes models_dev_cache.json 数据源"),
    use_openrouter: bool = Query(True, description="是否使用 OpenRouter API 数据源"),
):
    """
    触发上下文同步。

    从多个数据源（models_dev_cache.json → OpenRouter API → 数据库已有值）
    获取每个模型的 context_window 和 max_tokens，并写回 FMH 数据库。
    """
    from context_sync import run_context_sync
    try:
        stats = run_context_sync(
            use_dev_cache=use_dev_cache,
            use_openrouter=use_openrouter,
        )
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.exception("上下文同步失败")
        return {"success": False, "error": str(e)}


@router.get("/coverage")
async def context_coverage():
    """
    查询上下文 / max_tokens 填充覆盖率统计。

    返回各 provider 的模型数量、已填充上下文数、已填充 max_tokens 数。
    """
    from context_sync import get_coverage
    try:
        return get_coverage()
    except Exception as e:
        logger.exception("获取覆盖率统计失败")
        return {"success": False, "error": str(e)}

"""
Model API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from models.repository import search_models, get_model_by_id, classify_all_models

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models(
    provider: Optional[str] = Query(None, description="按 Provider slug 筛选"),
    is_free: Optional[bool] = Query(None, description="仅显示免费模型"),
    type: Optional[str] = Query(None, alias="type", description="模型类型 chat/embedding/image"),
    search: Optional[str] = Query(None, description="模糊搜索模型名称"),
    tags: Optional[str] = Query(None, description="按标签筛选，逗号分隔"),
    capability_tier: Optional[int] = Query(None, ge=1, le=3, description="能力分级：1=旗舰, 2=增强, 3=基础"),
    use_case: Optional[str] = Query(None, description="用途分类：chat/image/reasoning/code/embedding/vision/audio/reranker"),
    sort: Optional[str] = Query(None, description="排序：tier(t1优先)/tier_desc(t3优先)/newest(最新)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
):
    """获取模型列表，支持多维筛选"""
    models, total = search_models(
        provider=provider,
        is_free=is_free,
        model_type=type,
        search=search,
        tags=tags,
        capability_tier=capability_tier,
        use_case=use_case,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "models": models,
    }


@router.get("/models/{provider_slug}/{model_id:path}")
async def get_model_by_provider_and_slug(provider_slug: str, model_id: str):
    """根据 provider_slug 和 model_id 获取单个模型详情"""
    from models.repository import get_model_by_provider_and_model_id
    model = get_model_by_provider_and_model_id(provider_slug, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    """获取单个模型详情（支持数字 ID 或 model_id 字符串）"""
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model




@router.get("/classify/stats")
async def get_classify_stats():
    """获取分类统计数据（各 tier / use_case 的模型数量）"""
    from database import get_db
    with get_db() as db:
        # 排除隐藏提供商的模型
        total_row = db.execute(
            "SELECT COUNT(*) as c FROM models m JOIN providers p ON m.provider_id = p.id WHERE (p.hidden IS NULL OR p.hidden = 0)"
        ).fetchone()
        total = total_row["c"]

        tiers_rows = db.execute(
            """SELECT m.capability_tier, COUNT(*) as c FROM models m
               JOIN providers p ON m.provider_id = p.id
               WHERE m.capability_tier IS NOT NULL AND (p.hidden IS NULL OR p.hidden = 0)
               GROUP BY m.capability_tier ORDER BY m.capability_tier"""
        ).fetchall()
        tiers = []
        for r in tiers_rows:
            t = r["capability_tier"]
            labels = {1: "🏆 旗舰级 (Tier 1)", 2: "⚡ 增强级 (Tier 2)", 3: "🔧 基础级 (Tier 3)"}
            tiers.append({"tier": t, "label": labels.get(t, f"Tier {t}"), "count": r["c"]})

        uc_rows = db.execute(
            """SELECT m.use_case, COUNT(*) as c FROM models m
               JOIN providers p ON m.provider_id = p.id
               WHERE (p.hidden IS NULL OR p.hidden = 0)
               GROUP BY m.use_case ORDER BY COUNT(*) DESC"""
        ).fetchall()
        uc_labels = {
            "chat": "💬 对话", "image": "🎨 图像生成", "reasoning": "🧠 推理",
            "code": "💻 代码", "embedding": "📐 嵌入", "vision": "👁️ 视觉",
            "audio": "🎵 音频", "reranker": "🔀 重排序",
        }
        use_cases = []
        for r in uc_rows:
            use_cases.append({"use_case": r["use_case"], "label": uc_labels.get(r["use_case"], r["use_case"]), "count": r["c"]})

        return {"total": total, "tiers": tiers, "use_cases": use_cases}


@router.post("/classify/run")
async def run_classify():
    """手动触发对所有模型重新分类"""
    stats = classify_all_models()
    return {"success": True, "message": "全部分类完成", "stats": stats}

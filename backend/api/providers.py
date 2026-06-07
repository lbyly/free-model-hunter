"""
Provider API 路由
"""
from fastapi import APIRouter, HTTPException
from models.repository import (
    get_all_providers,
    get_provider_by_slug,
    toggle_provider_hidden,
    batch_set_providers_hidden,
    create_provider,
    update_provider_details,
    delete_provider,
)

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers")
async def list_providers(active_only: bool = True, include_hidden: bool = False):
    """获取 Provider 列表"""
    providers = get_all_providers(active_only=active_only, include_hidden=include_hidden)
    return {"providers": providers}


@router.get("/providers/{slug}")
async def get_provider(slug: str):
    """根据 slug 获取 Provider"""
    provider = get_provider_by_slug(slug)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{slug}' not found")
    return provider


@router.post("/providers")
async def add_provider(data: dict):
    """添加新的 Provider"""
    try:
        provider = create_provider(data)
        return {"success": True, "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.put("/providers/{slug}")
async def update_provider(slug: str, data: dict):
    """更新 Provider"""
    try:
        provider = update_provider_details(slug, data)
        return {"success": True, "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/providers/{slug}")
async def remove_provider(slug: str):
    """删除 Provider"""
    try:
        delete_provider(slug)
        return {"success": True, "message": f"Provider '{slug}' 已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/providers/{slug}/toggle")
async def toggle_provider(slug: str):
    """切换 Provider 的 hidden 状态（隐藏/显示）"""
    try:
        provider = toggle_provider_hidden(slug)
        return {"success": True, "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")


@router.post("/providers/batch-toggle")
async def batch_toggle_providers(data: dict):
    """批量设置 Provider 的 hidden 状态
    
    请求体: {"slugs": ["openrouter", "groq"], "hidden": true}
    hidden=true 表示隐藏，false 表示显示
    """
    slugs = data.get("slugs", [])
    hidden = data.get("hidden", True)
    if not slugs:
        raise HTTPException(status_code=400, detail="slugs 列表不能为空")
    try:
        providers = batch_set_providers_hidden(slugs, hidden)
        return {"success": True, "providers": providers, "hidden": hidden}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量操作失败: {str(e)}")
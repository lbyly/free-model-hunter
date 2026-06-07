"""
Pydantic 响应模型
"""
from typing import Any, Optional
from pydantic import BaseModel


class RateLimitSchema(BaseModel):
    rate_type: str
    limit_value: int
    tier: str = "free"


class ProviderBriefSchema(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None


class ModelListItem(BaseModel):
    id: int
    provider_id: int
    model_id: str
    name: str
    type: str
    capability_tier: Optional[int] = None
    use_case: str = "chat"
    is_free: bool
    free_quota: Optional[str] = None
    context_window: Optional[str] = None
    tags: list = []
    provider: ProviderBriefSchema
    rate_limits: list[RateLimitSchema] = []


class ModelListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    models: list[ModelListItem]


class ProviderSchema(BaseModel):
    id: int
    name: str
    slug: str
    website: Optional[str] = None
    is_active: bool = True
    logo_url: Optional[str] = None
    last_scraped: Optional[str] = None
    model_count: int = 0


class ProviderListResponse(BaseModel):
    providers: list[ProviderSchema]


class ModelDetailSchema(ModelListItem):
    description: Optional[str] = None
    pricing_url: Optional[str] = None
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    provider: ProviderBriefSchema | dict = {}


class ScrapeLogSchema(BaseModel):
    id: int
    provider_id: int
    status: str
    model_count: int
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    scraped_at: Optional[str] = None


class RefreshResponse(BaseModel):
    success: bool
    message: str
    results: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    detail: str


# 分类统计
class TierStats(BaseModel):
    tier: int
    label: str
    count: int


class UseCaseStats(BaseModel):
    use_case: str
    label: str
    count: int


class ClassifyStatsResponse(BaseModel):
    total: int
    tiers: list[TierStats]
    use_cases: list[UseCaseStats]

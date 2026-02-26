from datetime import datetime
from pydantic import BaseModel


class ExportModeOut(BaseModel):
    free_exports_enabled: bool
    free_exports_until: datetime | None
    exports_free_now: bool


class ExportModeUpdateIn(BaseModel):
    free_exports_enabled: bool | None = None
    free_exports_until: datetime | None = None  # set null to clear


class GrowthBlock(BaseModel):
    current: int
    previous: int
    delta: int
    pct: float | None  # None when previous=0


class RevenueBlock(BaseModel):
    current_cents: int
    previous_cents: int
    delta_cents: int
    pct: float | None


class MetricsWindowOut(BaseModel):
    label: str
    start_utc: datetime | None
    end_utc: datetime | None
    users_total: int  # all-time total users (not windowed)
    new_users: GrowthBlock
    paying_users: GrowthBlock
    revenue: RevenueBlock


class MetricsSummaryOut(BaseModel):
    all_time_users: int
    all_time_paying_users: int
    all_time_revenue_cents: int
    windows: list[MetricsWindowOut]

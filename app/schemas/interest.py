from datetime import datetime
from pydantic import BaseModel, Field


class InterestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class InterestRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class InterestOut(BaseModel):
    id: str
    name: str
    status: str
    focus_state: str
    sort_order: int


class PauseIntervalOut(BaseModel):
    id: str
    paused_at: datetime
    resumed_at: datetime | None


class FocusStintOut(BaseModel):
    id: str
    interest_id: str
    interest_name: str
    started_at: datetime
    ended_at: datetime | None
    pauses: list[PauseIntervalOut]

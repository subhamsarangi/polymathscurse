from datetime import datetime
from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class TargetRename(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class TargetOut(BaseModel):
    id: str
    interest_id: str
    name: str
    sort_order: int


class BulletIn(BaseModel):
    content: str = Field(min_length=1, max_length=400)
    category: str | None = Field(default=None, max_length=24)
    sort_order: int = 0


class BulletOut(BaseModel):
    id: str
    target_id: str
    content: str
    category: str | None
    sort_order: int


class TodoCreate(BaseModel):
    content: str = Field(min_length=1, max_length=280)
    status: str = Field(pattern="^(ACTIVE|BACKLOG)$")  # creation limited to these


class TodoEdit(BaseModel):
    content: str = Field(min_length=1, max_length=280)


class TodoOut(BaseModel):
    id: str
    target_id: str
    status: str
    content: str
    created_at: datetime
    done_at: datetime | None

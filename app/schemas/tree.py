from pydantic import BaseModel
from datetime import datetime


class TodoCounts(BaseModel):
    active: int
    backlog: int
    done: int


class BulletOut(BaseModel):
    id: str
    content: str
    category: str | None
    sort_order: int


class TargetWithCountsOut(BaseModel):
    id: str
    name: str
    sort_order: int
    bullets: list[BulletOut]
    todo_counts: TodoCounts


class InterestTreeCountsOut(BaseModel):
    id: str
    name: str
    status: str
    focus_state: str
    targets: list[TargetWithCountsOut]
    updated_at: datetime | None = None


class TodoOut(BaseModel):
    id: str
    status: str
    content: str
    created_at: datetime
    done_at: datetime | None


class GroupedTodosOut(BaseModel):
    active: list[TodoOut]
    backlog: list[TodoOut]
    done: list[TodoOut]


class TargetDetailOut(BaseModel):
    id: str
    interest_id: str
    name: str
    bullets: list[BulletOut]
    todos: GroupedTodosOut


class TargetExportOut(BaseModel):
    id: str
    name: str
    sort_order: int
    bullets: list[BulletOut]
    todos: GroupedTodosOut


class InterestExportOut(BaseModel):
    id: str
    name: str
    status: str
    focus_state: str
    exported_at: datetime
    targets: list[TargetExportOut]
    totals: TodoCounts

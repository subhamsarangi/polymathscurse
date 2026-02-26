from datetime import datetime
from pydantic import BaseModel


class ExportCreateOut(BaseModel):
    export_id: str
    status: str
    amount_cents: int
    currency: str


class ExportStatusOut(BaseModel):
    export_id: str
    status: str
    amount_cents: int
    currency: str
    paid_at: datetime | None
    consumed_at: datetime | None


class ExportTokenOut(BaseModel):
    export_id: str
    token: str

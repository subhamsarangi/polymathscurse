import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExportDownload(Base):
    """
    One paid download = one record.
    User pays $1 -> record becomes PAID -> user can mint a single-use token -> redeem once.
    """
    __tablename__ = "export_downloads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    interest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interests.id", ondelete="CASCADE"), index=True)

    # PENDING | PAID | CONSUMED | CANCELED
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")

    # later you can store provider refs (stripe payment_intent id, razorpay payment id, etc.)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    amount_cents: Mapped[int] = mapped_column(nullable=False, server_default="100")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="USD")

    token: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)
    token_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
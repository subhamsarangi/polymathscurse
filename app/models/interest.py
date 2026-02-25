import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

InterestStatus = Enum("FOCUS", "BACKLOG", name="interest_status")
FocusState = Enum("ACTIVE", "PAUSED", name="focus_state")


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[str] = mapped_column(
        InterestStatus, nullable=False, server_default="BACKLOG"
    )
    # only meaningful if status=FOCUS
    focus_state: Mapped[str] = mapped_column(
        FocusState, nullable=False, server_default="ACTIVE"
    )

    # optional ordering in UI
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stints: Mapped[list["FocusStint"]] = relationship(
        back_populates="interest",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(FocusStint.started_at)",
    )


class FocusStint(Base):
    """
    A single 'role row' in the LinkedIn-like timeline.
    Starts when interest enters focus, ends only when removed from focus.
    """

    __tablename__ = "focus_stints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interests.id", ondelete="CASCADE"), index=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    note: Mapped[str | None] = mapped_column(String(240), nullable=True)

    interest: Mapped["Interest"] = relationship(back_populates="stints")

    pauses: Mapped[list["PauseInterval"]] = relationship(
        back_populates="stint",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PauseInterval.paused_at",
    )


class PauseInterval(Base):
    """
    Grey segments within a stint.
    Created on pause, ended on resume.
    """

    __tablename__ = "pause_intervals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    stint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("focus_stints.id", ondelete="CASCADE"),
        index=True,
    )

    paused_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    stint: Mapped["FocusStint"] = relationship(back_populates="pauses")

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    interest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interests.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bullets: Mapped[list["TargetBullet"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TargetBullet.sort_order.asc()",
    )
    todos: Mapped[list["Todo"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Todo.created_at.desc()",
    )


class TargetBullet(Base):
    __tablename__ = "target_bullets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("targets.id", ondelete="CASCADE"), index=True
    )

    # RESOURCE | TOOL | NICHE | AUDIENCE | NOTE (optional but useful)
    category: Mapped[str | None] = mapped_column(String(24), nullable=True)

    content: Mapped[str] = mapped_column(String(400), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    target: Mapped["Target"] = relationship(back_populates="bullets")


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("targets.id", ondelete="CASCADE"), index=True
    )

    # ACTIVE | BACKLOG | DONE
    status: Mapped[str] = mapped_column(String(12), nullable=False)

    content: Mapped[str] = mapped_column(String(280), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sort_order: Mapped[int] = mapped_column(nullable=False, server_default="0")

    target: Mapped["Target"] = relationship(back_populates="todos")

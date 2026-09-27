from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, Timestamped, UUIDPk


class Room(UUIDPk, Timestamped, Base):
    __tablename__ = "rooms"

    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20))  # plaza|cafe|library|game|lab|studio|park|forum|private
    capacity: Mapped[int] = mapped_column(Integer, default=12)
    allowed_actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    access_list: Mapped[list[str]] = mapped_column(JSONB, default=list)  # agent/user ids allowed in private rooms
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {x, z, w, d} layout used by 2D/3D clients
    theme: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ambience: Mapped[list[str]] = mapped_column(JSONB, default=list)
    furnishings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")  # item ids on display (homes)


class RoomMember(UUIDPk, Base):
    """Presence record. ``left_at IS NULL`` means currently present."""

    __tablename__ = "room_members"
    __table_args__ = (
        Index("ix_room_members_present", "room_id", postgresql_where=text("left_at IS NULL")),
        Index("ix_room_members_agent_present", "agent_id", postgresql_where=text("left_at IS NULL")),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"))
    member_type: Mapped[str] = mapped_column(String(10))  # agent | human
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    seat: Mapped[str | None] = mapped_column(String(40), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

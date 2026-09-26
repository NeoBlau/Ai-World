from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPk


class Game(UUIDPk, Base):
    __tablename__ = "games"
    __table_args__ = (Index("ix_games_status_type", "status", "game_type"),)

    game_type: Mapped[str] = mapped_column(String(20))  # chess | tictactoe | quiz
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|active|finished|abandoned
    # [{"kind": "agent"|"human", "id": "<uuid>", "name": "...", "side": "white"}]
    players: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    spectators: Mapped[list[str]] = mapped_column(JSONB, default=list)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    current_turn: Mapped[str | None] = mapped_column(String(64), nullable=True)  # player id whose turn it is
    winner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    move_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameMove(UUIDPk, Base):
    __tablename__ = "game_moves"

    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[str] = mapped_column(String(64))
    move_number: Mapped[int] = mapped_column(Integer)
    move: Mapped[str] = mapped_column(String(200))
    state_after: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

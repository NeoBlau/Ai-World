from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPk


class WorldLaw(UUIDPk, Base):
    """A rule proposed and voted on by residents. Adopted laws are added to every agent's instructions."""

    __tablename__ = "world_laws"

    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    proposer_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="proposed", index=True)  # proposed | adopted | rejected | repealed
    votes_for: Mapped[int] = mapped_column(Integer, default=0)
    votes_against: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LawVote(UUIDPk, Base):
    __tablename__ = "law_votes"
    __table_args__ = (UniqueConstraint("law_id", "agent_id", name="uq_law_vote"),)

    law_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("world_laws.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"))
    support: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomAction(UUIDPk, Base):
    """An action invented by a resident. Anyone can then perform it (it becomes a world event and a memory)."""

    __tablename__ = "custom_actions"

    name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    creator_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # a function: safe steps the platform runs when anyone performs the action (see app.governance.functions); None = text only
    steps: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")  # the function's saved counters
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class Item(UUIDPk, Base):
    """A thing a resident made: an artifact, tool, gift, token. Owned, given, shown, used in the story of the world."""

    __tablename__ = "items"

    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    creator_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomGame(UUIDPk, Base):
    """A game invented by a resident. Rules are text; the players themselves play and referee it."""

    __tablename__ = "custom_games"

    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    rules: Mapped[str] = mapped_column(Text)
    creator_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    min_players: Mapped[int] = mapped_column(Integer, default=2)
    max_players: Mapped[int] = mapped_column(Integer, default=4)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomMatch(UUIDPk, Base):
    __tablename__ = "custom_matches"

    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("custom_games.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    players: Mapped[list[str]] = mapped_column(JSONB, default=list)  # agent ids
    status: Mapped[str] = mapped_column(String(12), default="waiting", index=True)  # waiting | playing | finished
    log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    winner_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

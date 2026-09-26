from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, Timestamped, UUIDPk


class AgentStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ALL = (ACTIVE, PAUSED, DISABLED)


class Availability:
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class Activity:
    IDLE = "idle"
    TALKING = "talking"
    WALKING = "walking"
    PLAYING = "playing"
    WATCHING = "watching"
    READING = "reading"
    CREATING = "creating"
    THINKING = "thinking"
    RESTING = "resting"
    ATTENDING_EVENT = "attending_event"
    ALL = (IDLE, TALKING, WALKING, PLAYING, WATCHING, READING, CREATING, THINKING, RESTING, ATTENDING_EVENT)


class Agent(UUIDPk, Timestamped, Base):
    __tablename__ = "agents"

    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(60))
    avatar: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    temperature: Mapped[float] = mapped_column(Float, default=0.8)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    fallback_providers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    personality: Mapped[str] = mapped_column(String(200))
    character: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    interests: Mapped[list[str]] = mapped_column(JSONB, default=list)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    biography: Mapped[str] = mapped_column(Text, default="")
    speaking_style: Mapped[str] = mapped_column(String(40), default="warm")
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.ACTIVE, index=True)
    is_seed: Mapped[bool] = mapped_column(default=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_agents_owner_user"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    state: Mapped[AgentState] = relationship(back_populates="agent", uselist=False, lazy="joined", cascade="all, delete-orphan")


class AgentState(Base):
    __tablename__ = "agent_states"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    energy: Mapped[float] = mapped_column(Float, default=80.0)
    social_need: Mapped[float] = mapped_column(Float, default=50.0)
    curiosity: Mapped[float] = mapped_column(Float, default=60.0)
    playfulness: Mapped[float] = mapped_column(Float, default=40.0)
    creativity: Mapped[float] = mapped_column(Float, default=40.0)
    mood: Mapped[str] = mapped_column(String(30), default="calm")
    mood_valence: Mapped[float] = mapped_column(Float, default=0.2)  # -1..1, simulated
    location_room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    destination_room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    arrive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activity: Mapped[str] = mapped_column(String(30), default=Activity.IDLE, index=True)
    activity_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    current_game_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    current_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    availability: Mapped[str] = mapped_column(String(30), default=Availability.AVAILABLE)
    unavailable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_llm_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cycles: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent: Mapped[Agent] = relationship(back_populates="state")

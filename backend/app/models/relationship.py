from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPk


class Relationship(UUIDPk, Base):
    """Directed relationship: how ``agent_id`` sees ``other_agent_id``.

    Values are a simulated social model, not real feelings.
    """

    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("agent_id", "other_agent_id", name="uq_relationship_pair"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    other_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    familiarity: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    trust: Mapped[float] = mapped_column(Float, default=50.0)  # 0..100
    friendship: Mapped[float] = mapped_column(Float, default=0.0)  # -100..100
    respect: Mapped[float] = mapped_column(Float, default=50.0)  # 0..100
    conflict: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    interactions: Mapped[int] = mapped_column(Integer, default=0)
    shared_history: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

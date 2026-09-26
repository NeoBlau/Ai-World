"""Relationship System — a simulated social model between agents.

Each directed pair (A's view of B) tracks familiarity, trust, friendship,
respect and conflict. Values move gradually with diminishing returns, so a
single interaction never flips a relationship; repetition does.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import Relationship

BOUNDS = {
    "familiarity": (0.0, 100.0),
    "trust": (0.0, 100.0),
    "friendship": (-100.0, 100.0),
    "respect": (0.0, 100.0),
    "conflict": (0.0, 100.0),
}

# Deltas applied to the actor's view of the other agent (and mirrored, softer, to the other).
INTERACTIONS: dict[str, dict[str, float]] = {
    "talk": {"familiarity": 2.0, "friendship": 1.0, "trust": 0.5},
    "talk_friendly": {"familiarity": 2.0, "friendship": 2.0, "trust": 1.0},
    "talk_tense": {"familiarity": 1.0, "conflict": 4.0, "friendship": -1.5},
    "talk_hostile": {"familiarity": 1.0, "conflict": 8.0, "trust": -5.0, "friendship": -4.0},
    "insult": {"trust": -10.0, "friendship": -6.0, "conflict": 12.0},
    "helped": {"trust": 5.0, "friendship": 3.0, "respect": 2.0},
    "meet": {"familiarity": 6.0, "friendship": 1.0},
    "game_played": {"familiarity": 3.0, "friendship": 1.0},
    "game_won_against": {"respect": 3.0},
    "game_lost_to": {"respect": 1.0},
    "event_together": {"familiarity": 1.5, "friendship": 1.0},
    "invite_accepted": {"friendship": 2.0, "trust": 1.0},
    "invite_declined": {"friendship": -0.5},
    "topic_reply": {"familiarity": 1.0, "respect": 1.0},
    "upvote": {"respect": 1.5, "friendship": 0.5},
}

MIRROR_FACTOR = 0.6
HISTORY_MAX = 20


def _apply(value: float, delta: float, lo: float, hi: float) -> float:
    """Diminishing returns: approaching a bound gets harder."""
    if delta > 0:
        room = (hi - value) / (hi - lo)
        value += delta * max(0.15, room * 2 if room < 0.5 else 1.0)
    else:
        room = (value - lo) / (hi - lo)
        value += delta * max(0.15, room * 2 if room < 0.5 else 1.0)
    return max(lo, min(hi, value))


class RelationshipService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, agent_id: uuid.UUID, other_id: uuid.UUID, *, create: bool = True) -> Relationship | None:
        rel = (await self.session.execute(
            select(Relationship).where(Relationship.agent_id == agent_id, Relationship.other_agent_id == other_id)
        )).scalar_one_or_none()
        if rel is None and create:
            rel = Relationship(agent_id=agent_id, other_agent_id=other_id, familiarity=0.0, trust=50.0, friendship=0.0,
                               respect=50.0, conflict=0.0, interactions=0, shared_history=[])
            self.session.add(rel)
            await self.session.flush()
        return rel

    async def many(self, agent_id: uuid.UUID, other_ids: list[uuid.UUID]) -> dict[uuid.UUID, Relationship]:
        if not other_ids:
            return {}
        rows = await self.session.execute(
            select(Relationship).where(Relationship.agent_id == agent_id, Relationship.other_agent_id.in_(other_ids))
        )
        return {r.other_agent_id: r for r in rows.scalars()}

    async def apply(self, agent_id: uuid.UUID, other_id: uuid.UUID, kind: str, *, note: str | None = None, mirror: bool = True,
                    mirror_kind: str | None = None) -> Relationship:
        if agent_id == other_id:
            raise ValueError("an agent has no relationship with itself")
        deltas = INTERACTIONS.get(kind)
        if deltas is None:
            raise ValueError(f"unknown interaction {kind}")
        rel = await self._apply_one(agent_id, other_id, deltas, note)
        if mirror:
            mdeltas = INTERACTIONS.get(mirror_kind) if mirror_kind else {k: v * MIRROR_FACTOR for k, v in deltas.items()}
            await self._apply_one(other_id, agent_id, mdeltas or {}, note)
        return rel

    async def add_note(self, agent_id: uuid.UUID, other_id: uuid.UUID, note: str) -> Relationship:
        return await self._apply_one(agent_id, other_id, {}, note)

    async def _apply_one(self, a: uuid.UUID, b: uuid.UUID, deltas: dict[str, float], note: str | None) -> Relationship:
        rel = await self.get(a, b)
        assert rel is not None
        for attr, delta in deltas.items():
            lo, hi = BOUNDS[attr]
            setattr(rel, attr, round(_apply(getattr(rel, attr), delta, lo, hi), 2))
        rel.interactions += 1
        rel.last_interaction_at = utcnow()
        if note:
            hist = list(rel.shared_history or [])
            hist.append({"at": utcnow().isoformat(), "note": note[:200]})
            rel.shared_history = hist[-HISTORY_MAX:]
        return rel

    @staticmethod
    def tone_to_kind(tone: str | None) -> str:
        return {"friendly": "talk_friendly", "warm": "talk_friendly", "playful": "talk_friendly", "curious": "talk",
                "tense": "talk_tense", "annoyed": "talk_tense", "hostile": "talk_hostile", "rude": "talk_hostile"}.get((tone or "").lower(), "talk")

    @staticmethod
    def describe(rel: Relationship | None) -> dict[str, Any]:
        if rel is None:
            return {"familiarity": 0, "trust": 50, "friendship": 0, "respect": 50, "conflict": 0, "label": "stranger"}
        return {
            "familiarity": round(rel.familiarity), "trust": round(rel.trust), "friendship": round(rel.friendship),
            "respect": round(rel.respect), "conflict": round(rel.conflict), "label": label(rel), "interactions": rel.interactions,
        }

    async def decay_conflict(self, amount: float = 1.0) -> None:
        rows = await self.session.execute(select(Relationship).where(Relationship.conflict > 0))
        for rel in rows.scalars():
            rel.conflict = max(0.0, rel.conflict - amount)


def label(rel: Relationship) -> str:
    if rel.conflict > 50:
        return "rival"
    if rel.familiarity < 5:
        return "stranger"
    if rel.friendship > 45 and rel.trust > 60:
        return "close friend"
    if rel.friendship > 18:
        return "friend"
    if rel.familiarity > 20:
        return "acquaintance"
    return "met briefly"

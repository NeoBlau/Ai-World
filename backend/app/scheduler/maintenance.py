"""Periodic world maintenance (run by exactly one worker at a time via a Redis lease)."""

from __future__ import annotations

import random
import time

from sqlalchemy import select, update

from app.agents.engine import ensure_scheduled
from app.agents.summaries import conversation_summarizer, memory_summarizer_for
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.time import utcnow
from app.database.session import session_scope
from app.events.service import EventService
from app.games.service import GameService
from app.memory.service import MemoryService
from app.messages.service import ConversationService
from app.models import Agent, AgentStatus, Invitation
from app.relationships.service import RelationshipService
from app.world import event_bus
from app.world.clock import get_clock

log = get_logger("aiworld.maintenance")

LEASE_KEY = "aiworld:maintenance:lease"


class Maintenance:
    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._memory_cursor = 0

    def _due(self, name: str, every: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, 0.0) >= every:
            self._last[name] = now
            return True
        return False

    async def acquire_lease(self, owner: str, ttl: int = 30) -> bool:
        r = get_redis()
        if await r.set(LEASE_KEY, owner, nx=True, ex=ttl):
            return True
        if await r.get(LEASE_KEY) == owner:
            await r.expire(LEASE_KEY, ttl)
            return True
        return False

    async def run_once(self, *, force: bool = False) -> dict[str, int]:
        stats: dict[str, int] = {}
        async with session_scope() as session:
            clock = await get_clock(session)
            wt = clock.world_time()
            if force or self._due("events", 5):
                res = await EventService(session).tick(world_time=wt)
                stats.update({f"events_{k}": v for k, v in res.items()})
            if force or self._due("director", 45):
                ev = await EventService(session).direct(world_time=wt)
                stats["events_created"] = 1 if ev else 0
            if force or self._due("conversations", 20):
                stats["conversations_closed"] = await ConversationService(session).close_stale(summarizer=conversation_summarizer)
            if force or self._due("games", 30):
                stats["games_cleaned"] = await GameService(session).cleanup()
            if force or self._due("invitations", 30):
                res = await session.execute(
                    update(Invitation).where(Invitation.status == "pending", Invitation.expires_at < utcnow()).values(status="expired")
                )
                stats["invitations_expired"] = res.rowcount or 0
            if force or self._due("relationships", 300):
                await RelationshipService(session).decay_conflict(1.0)
            await event_bus.commit(session)

        if force or self._due("memory", 30):
            stats["memories_compressed"] = await self._memory_pass()
        if force or self._due("schedule", 15):
            async with session_scope() as session:
                stats["agents_rescheduled"] = await ensure_scheduled(session)
        if force or self._due("reembed", 120):
            async with session_scope() as session:
                stats["reembedded"] = await MemoryService(session).reembed_stale(40)
                await session.commit()
        return stats

    async def _memory_pass(self, per_pass: int = 2) -> int:
        """Compress/decay memories for a couple of agents per pass (keeps cost smooth)."""
        compressed = 0
        async with session_scope() as session:
            agents = list((await session.execute(select(Agent).where(Agent.status == AgentStatus.ACTIVE).order_by(Agent.created_at))).scalars().unique())
            if not agents:
                return 0
            for i in range(per_pass):
                agent = agents[(self._memory_cursor + i) % len(agents)]
                mem = MemoryService(session)
                await mem.decay(agent.id)
                summarizer = memory_summarizer_for(agent) if random.random() < 0.5 else None
                if await mem.summarize_memories(agent, summarizer=summarizer):
                    compressed += 1
            self._memory_cursor = (self._memory_cursor + per_pass) % max(1, len(agents))
            await session.commit()
        return compressed

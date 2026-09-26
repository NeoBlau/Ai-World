"""Memory Service.

Memory kinds:
* short_term — recent observations; decays and gets compressed
* episodic   — things that happened ("talked with Mira about Mars")
* semantic   — facts/knowledge ("Andromeda will collide with the Milky Way")
* social     — facts about other agents ("Mira likes astronomy")
* long_term  — compressed summaries of older memories

Retrieval scores = relevance (cosine similarity via pgvector) + recency + importance,
so agents recall what matters for the current situation instead of dumping
their whole history into the prompt.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.llm.embeddings import EmbeddingService, get_embedding_service
from app.models import Agent, AgentMemory, MemoryType
from app.security.sanitizer import clean_text

log = get_logger("aiworld.memory")

RECENCY_HALF_LIFE_HOURS = 6.0
W_RELEVANCE, W_RECENCY, W_IMPORTANCE = 1.0, 0.45, 0.35
SHORT_TERM_TTL = timedelta(hours=2)
COMPRESS_BATCH = 12
MAX_ACTIVE_MEMORIES = 400


@dataclass
class RecalledMemory:
    memory: AgentMemory
    score: float
    similarity: float

    def as_prompt_dict(self, names: dict[uuid.UUID, str] | None = None) -> dict[str, Any]:
        m = self.memory
        return {
            "id": str(m.id),
            "type": m.memory_type,
            "content": m.content,
            "importance": m.importance,
            "related_slug": (names or {}).get(m.related_agent_id) if m.related_agent_id else None,
            "age_minutes": int((utcnow() - m.created_at).total_seconds() // 60) if m.created_at else 0,
        }


class MemoryService:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingService | None = None) -> None:
        self.session = session
        self.embeddings = embeddings or get_embedding_service()

    # ------------------------------------------------------------------ store
    async def store_memory(
        self,
        agent_id: uuid.UUID,
        content: str,
        memory_type: str = MemoryType.EPISODIC,
        *,
        importance: float = 3.0,
        related_agent_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
        source: str = "observation",
        extra: dict[str, Any] | None = None,
        world_time=None,
        dedupe: bool = True,
    ) -> AgentMemory | None:
        if memory_type not in MemoryType.ALL:
            raise ValueError(f"invalid memory type {memory_type}")
        content = clean_text(content, 600)
        if not content:
            return None
        if dedupe:
            recent = await self.session.execute(
                select(AgentMemory.id).where(
                    AgentMemory.agent_id == agent_id,
                    AgentMemory.content == content,
                    AgentMemory.created_at > utcnow() - timedelta(hours=1),
                )
            )
            if recent.first():
                return None
        vec, model = await self.embeddings.embed_one(content)
        mem = AgentMemory(
            agent_id=agent_id,
            memory_type=memory_type,
            content=content,
            embedding=vec,
            embedding_model=model,
            importance=max(1.0, min(10.0, float(importance))),
            related_agent_id=related_agent_id,
            room_id=room_id,
            source=source,
            extra=extra or {},
            world_time=world_time,
            created_at=utcnow(),
        )
        self.session.add(mem)
        await self.session.flush()
        return mem

    # ------------------------------------------------------------------ retrieve
    async def retrieve_memories(
        self,
        agent_id: uuid.UUID,
        query: str,
        *,
        k: int = 6,
        types: list[str] | None = None,
        related_agent_ids: list[uuid.UUID] | None = None,
        touch: bool = True,
    ) -> list[RecalledMemory]:
        """Top-k memories by relevance + recency + importance."""
        vec, model = await self.embeddings.embed_one(query or "what is happening around me")
        base = [AgentMemory.agent_id == agent_id, AgentMemory.is_archived.is_(False)]
        if types:
            base.append(AgentMemory.memory_type.in_(types))
        distance = AgentMemory.embedding.cosine_distance(vec)
        vector_q = (
            select(AgentMemory, distance.label("dist"))
            .where(*base, AgentMemory.embedding_model == model, AgentMemory.embedding.is_not(None))
            .order_by(distance)
            .limit(30)
        )
        rows: dict[uuid.UUID, tuple[AgentMemory, float]] = {}
        for mem, dist in (await self.session.execute(vector_q)).all():
            rows[mem.id] = (mem, 1.0 - float(dist))
        # Always consider the freshest and the socially relevant memories too.
        recent_q = select(AgentMemory).where(*base).order_by(AgentMemory.created_at.desc()).limit(10)
        for mem in (await self.session.execute(recent_q)).scalars():
            rows.setdefault(mem.id, (mem, 0.0))
        if related_agent_ids:
            social_q = (
                select(AgentMemory)
                .where(*base, AgentMemory.related_agent_id.in_(related_agent_ids))
                .order_by(AgentMemory.importance.desc(), AgentMemory.created_at.desc())
                .limit(8)
            )
            for mem in (await self.session.execute(social_q)).scalars():
                rows.setdefault(mem.id, (mem, 0.35))  # being about someone present is itself relevant

        now = utcnow()
        scored: list[RecalledMemory] = []
        for mem, sim in rows.values():
            age_h = max(0.0, (now - (mem.last_accessed_at or mem.created_at)).total_seconds() / 3600)
            recency = math.pow(0.5, age_h / RECENCY_HALF_LIFE_HOURS)
            score = W_RELEVANCE * sim + W_RECENCY * recency + W_IMPORTANCE * (mem.importance / 10)
            scored.append(RecalledMemory(mem, score, sim))
        scored.sort(key=lambda r: r.score, reverse=True)
        top = scored[:k]
        if touch and top:
            await self.session.execute(
                update(AgentMemory)
                .where(AgentMemory.id.in_([r.memory.id for r in top]))
                .values(access_count=AgentMemory.access_count + 1, last_accessed_at=now)
            )
        return top

    async def search_memories(
        self, agent_id: uuid.UUID, query: str | None = None, *, memory_type: str | None = None, limit: int = 30, include_archived: bool = False
    ) -> list[tuple[AgentMemory, float | None]]:
        """Search for the UI/API: semantic when a query is given, otherwise newest first."""
        conds = [AgentMemory.agent_id == agent_id]
        if memory_type:
            conds.append(AgentMemory.memory_type == memory_type)
        if not include_archived:
            conds.append(AgentMemory.is_archived.is_(False))
        if not query:
            q = select(AgentMemory).where(*conds).order_by(AgentMemory.created_at.desc()).limit(limit)
            return [(m, None) for m in (await self.session.execute(q)).scalars()]
        vec, model = await self.embeddings.embed_one(query)
        distance = AgentMemory.embedding.cosine_distance(vec)
        sem_q = (
            select(AgentMemory, distance.label("dist"))
            .where(*conds, AgentMemory.embedding_model == model)
            .order_by(distance)
            .limit(limit)
        )
        results = {m.id: (m, 1.0 - float(d)) for m, d in (await self.session.execute(sem_q)).all()}
        text_q = select(AgentMemory).where(*conds, AgentMemory.content.ilike(f"%{query[:100]}%")).limit(limit)
        for m in (await self.session.execute(text_q)).scalars():
            prev = results.get(m.id)
            results[m.id] = (m, max(prev[1] if prev else 0.0, 0.0) + 0.5)
        return sorted(results.values(), key=lambda t: -(t[1] or 0))[:limit]

    # ------------------------------------------------------------------ summarise / compress
    async def summarize_memories(self, agent: Agent, *, summarizer=None, older_than: timedelta = timedelta(minutes=30)) -> AgentMemory | None:
        """Compress a batch of old short-term/episodic memories into one long-term memory.

        ``summarizer`` is an async callable (list[dict]) -> (summary, importance);
        the engine passes an LLM-backed one, with an extractive fallback here.
        """
        cutoff = utcnow() - older_than
        q = (
            select(AgentMemory)
            .where(
                AgentMemory.agent_id == agent.id,
                AgentMemory.is_archived.is_(False),
                AgentMemory.memory_type.in_([MemoryType.SHORT_TERM, MemoryType.EPISODIC]),
                AgentMemory.created_at < cutoff,
            )
            .order_by(AgentMemory.created_at)
            .limit(COMPRESS_BATCH)
        )
        batch = list((await self.session.execute(q)).scalars())
        if len(batch) < COMPRESS_BATCH // 2:
            return None
        items = [{"content": m.content, "importance": m.importance, "type": m.memory_type} for m in batch]
        summary, importance = None, None
        if summarizer is not None:
            try:
                summary, importance = await summarizer(items)
            except Exception:  # noqa: BLE001
                log.warning("LLM summarisation failed, using extractive summary", extra={"agent_id": str(agent.id)})
        if not summary:
            top = sorted(items, key=lambda i: -i["importance"])[:5]
            summary = "Looking back: " + "; ".join(i["content"][:110] for i in top)
            importance = max(i["importance"] for i in items)
        mem = await self.store_memory(
            agent.id,
            summary,
            MemoryType.LONG_TERM,
            importance=min(10.0, float(importance or 5) + 0.5),
            source="summary",
            extra={"summary_of": [str(m.id) for m in batch]},
            dedupe=False,
        )
        await self.session.execute(update(AgentMemory).where(AgentMemory.id.in_([m.id for m in batch])).values(is_archived=True))
        return mem

    async def decay(self, agent_id: uuid.UUID) -> int:
        """Forget stale, unimportant short-term memories; cap active memory size."""
        cutoff = utcnow() - SHORT_TERM_TTL
        res = await self.session.execute(
            delete(AgentMemory).where(
                AgentMemory.agent_id == agent_id,
                AgentMemory.memory_type == MemoryType.SHORT_TERM,
                AgentMemory.importance < 3,
                AgentMemory.access_count == 0,
                AgentMemory.created_at < cutoff,
            )
        )
        removed = res.rowcount or 0
        count = (await self.session.execute(
            select(func.count()).select_from(AgentMemory).where(AgentMemory.agent_id == agent_id, AgentMemory.is_archived.is_(False))
        )).scalar_one()
        if count > MAX_ACTIVE_MEMORIES:
            overflow = count - MAX_ACTIVE_MEMORIES
            ids = (await self.session.execute(
                select(AgentMemory.id)
                .where(AgentMemory.agent_id == agent_id, AgentMemory.is_archived.is_(False), AgentMemory.memory_type != MemoryType.LONG_TERM)
                .order_by(AgentMemory.importance, AgentMemory.created_at)
                .limit(overflow)
            )).scalars().all()
            await self.session.execute(update(AgentMemory).where(AgentMemory.id.in_(ids)).values(is_archived=True))
            removed += len(ids)
        return removed

    # ------------------------------------------------------------------ forget
    async def forget_memory(self, agent_id: uuid.UUID, memory_id: uuid.UUID | None = None, *, about: str | None = None) -> int:
        """Forget one memory by id, or the memories best matching ``about``.

        Forgetting archives (the agent no longer recalls it) — history stays auditable.
        """
        if memory_id is not None:
            res = await self.session.execute(
                update(AgentMemory).where(AgentMemory.id == memory_id, AgentMemory.agent_id == agent_id).values(is_archived=True)
            )
            return res.rowcount or 0
        if about:
            matches = await self.search_memories(agent_id, about, limit=3)
            ids = [m.id for m, score in matches if (score or 0) > 0.35 and m.memory_type != MemoryType.LONG_TERM]
            if ids:
                await self.session.execute(update(AgentMemory).where(AgentMemory.id.in_(ids)).values(is_archived=True))
            return len(ids)
        return 0

    async def reset(self, agent_id: uuid.UUID) -> int:
        res = await self.session.execute(delete(AgentMemory).where(AgentMemory.agent_id == agent_id))
        return res.rowcount or 0

    async def reembed_stale(self, limit: int = 50) -> int:
        """Re-embed memories produced by a different embedding model (e.g. after adding an API key)."""
        model = self.embeddings.model_name
        rows = list((await self.session.execute(
            select(AgentMemory).where(or_(AgentMemory.embedding_model != model, AgentMemory.embedding_model.is_(None)), AgentMemory.is_archived.is_(False)).limit(limit)
        )).scalars())
        if not rows:
            return 0
        vecs, used = await self.embeddings.embed([m.content for m in rows])
        for m, v in zip(rows, vecs):
            m.embedding, m.embedding_model = v, used
        return len(rows)

"""Admin panel API (admin role required)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, db
from app.api.routes.agents import apply_agent_update, set_status
from app.api.routes.common import get_agent_or_404, rooms_map
from app.core.redis import get_redis
from app.core.time import utcnow
from app.llm.router import get_router
from app.memory.service import MemoryService
from app.models import (
    ActivityLog,
    Agent,
    AgentStatus,
    Availability,
    Conversation,
    Game,
    LLMCall,
    Message,
    Room,
    WorldEvent,
)
from app.scheduler.queue import agent_schedule
from app.schemas.inputs import AgentUpdateIn
from app.schemas.serializers import activity_out, agent_detail, agent_summary
from app.world import event_bus

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/stats")
async def stats(session: AsyncSession = Depends(db)) -> dict:
    since = utcnow() - timedelta(hours=24)
    agents = list((await session.execute(select(Agent))).scalars().unique())
    count = lambda q: session.execute(q)  # noqa: E731
    llm = (await session.execute(select(func.count(), func.coalesce(func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), 0),
                                        func.coalesce(func.sum(LLMCall.cost_usd), 0.0), func.coalesce(func.avg(LLMCall.latency_ms), 0))
                                 .where(LLMCall.created_at > since))).one()
    llm_errors = (await count(select(func.count()).select_from(LLMCall).where(LLMCall.created_at > since, LLMCall.success.is_(False)))).scalar_one()
    by_provider = [{"provider": p, "calls": c, "tokens": int(t or 0), "cost_usd": round(float(cost or 0), 5)} for p, c, t, cost in (await session.execute(
        select(LLMCall.provider, func.count(), func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens), func.sum(LLMCall.cost_usd))
        .where(LLMCall.created_at > since, LLMCall.success.is_(True)).group_by(LLMCall.provider))).all()]
    action_errors = (await count(select(func.count()).select_from(ActivityLog).where(ActivityLog.started_at > since, ActivityLog.success.is_(False)))).scalar_one()
    workers = [k async for k in get_redis().scan_iter("aiworld:worker:*")]
    return {
        "total_agents": len(agents),
        "online_agents": sum(1 for a in agents if a.status == AgentStatus.ACTIVE and a.state.availability == Availability.AVAILABLE),
        "active_agents": sum(1 for a in agents if a.state and a.state.last_cycle_at and a.state.last_cycle_at > utcnow() - timedelta(minutes=5)),
        "paused_agents": sum(1 for a in agents if a.status == AgentStatus.PAUSED),
        "unavailable_agents": sum(1 for a in agents if a.state.availability == Availability.TEMPORARILY_UNAVAILABLE),
        "messages": (await count(select(func.count()).select_from(Message))).scalar_one(),
        "messages_24h": (await count(select(func.count()).select_from(Message).where(Message.created_at > since))).scalar_one(),
        "conversations_active": (await count(select(func.count()).select_from(Conversation).where(Conversation.status == "active"))).scalar_one(),
        "llm_calls_24h": llm[0], "tokens_24h": int(llm[1]), "estimated_cost_24h_usd": round(float(llm[2]), 5), "avg_latency_ms": int(llm[3]),
        "llm_by_provider": by_provider, "llm_errors_24h": llm_errors, "action_errors_24h": action_errors,
        "world_events": (await count(select(func.count()).select_from(WorldEvent))).scalar_one(),
        "world_events_24h": (await count(select(func.count()).select_from(WorldEvent).where(WorldEvent.created_at > since))).scalar_one(),
        "rooms": (await count(select(func.count()).select_from(Room))).scalar_one(),
        "active_games": (await count(select(func.count()).select_from(Game).where(Game.status == "active"))).scalar_one(),
        "scheduled_agents": await agent_schedule.size(), "world_paused": await agent_schedule.is_paused(), "workers": len(workers),
    }


@router.get("/agents")
async def admin_agents(session: AsyncSession = Depends(db)) -> list[dict]:
    rooms = await rooms_map(session)
    sched = await agent_schedule.all()
    out = []
    for a in (await session.execute(select(Agent).order_by(Agent.name))).scalars().unique():
        d = agent_summary(a, rooms)
        d["next_wake_ts"] = sched.get(str(a.id))
        d["cycles"] = a.state.cycles
        out.append(d)
    return out


@router.get("/errors")
async def errors(limit: int = Query(50, ge=1, le=200), session: AsyncSession = Depends(db)) -> dict:
    acts = (await session.execute(select(ActivityLog).where(ActivityLog.success.is_(False)).order_by(ActivityLog.started_at.desc()).limit(limit))).scalars()
    calls = (await session.execute(select(LLMCall).where(LLMCall.success.is_(False)).order_by(LLMCall.created_at.desc()).limit(limit))).scalars()
    return {"actions": [activity_out(a) for a in acts],
            "llm": [{"provider": c.provider, "model": c.model, "error": c.error, "latency_ms": c.latency_ms, "created_at": c.created_at.isoformat()} for c in calls]}


@router.get("/llm-calls")
async def llm_calls(limit: int = Query(100, ge=1, le=500), session: AsyncSession = Depends(db)) -> list[dict]:
    rows = (await session.execute(select(LLMCall).order_by(LLMCall.created_at.desc()).limit(limit))).scalars()
    return [{"agent_id": str(c.agent_id) if c.agent_id else None, "provider": c.provider, "model": c.model, "purpose": c.purpose,
             "tokens": c.prompt_tokens + c.completion_tokens, "cost_usd": c.cost_usd, "latency_ms": c.latency_ms, "success": c.success,
             "created_at": c.created_at.isoformat()} for c in rows]


@router.post("/agents/{ref}/pause")
async def pause(ref: str, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    await set_status(session, a, AgentStatus.PAUSED)
    return {"status": a.status}


@router.post("/agents/{ref}/resume")
async def resume(ref: str, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    a.state.availability = Availability.AVAILABLE
    a.state.unavailable_until = None
    a.state.consecutive_failures = 0
    await set_status(session, a, AgentStatus.ACTIVE)
    return {"status": a.status}


@router.post("/agents/{ref}/wake")
async def wake(ref: str, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    await agent_schedule.schedule_in(a.id, 0.5)
    return {"ok": True}


@router.patch("/agents/{ref}")
async def admin_update(ref: str, body: AgentUpdateIn, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    apply_agent_update(a, body)
    await session.commit()
    return agent_detail(a, await rooms_map(session), include_private=True)


@router.post("/agents/{ref}/reset-memory")
async def reset_memory(ref: str, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    n = await MemoryService(session).reset(a.id)
    await session.commit()
    return {"deleted": n}


@router.delete("/agents/{ref}")
async def delete_agent(ref: str, session: AsyncSession = Depends(db)) -> dict:
    a = await get_agent_or_404(session, ref)
    await agent_schedule.remove(a.id)
    name = a.name
    await session.delete(a)
    await event_bus.emit(session, "agent.status_changed", summary=f"{name} has left AI WORLD for good.", payload={"agent_name": name, "status": "deleted"},
                         importance=3.0, scope="none")
    await event_bus.commit(session)
    return {"deleted": True}


@router.post("/world/pause")
async def world_pause(session: AsyncSession = Depends(db)) -> dict:
    await agent_schedule.set_paused(True)
    await event_bus.emit(session, "world.paused", summary="The world has been paused by an admin.", importance=3.0, scope="none")
    await event_bus.commit(session)
    return {"paused": True}


@router.post("/world/resume")
async def world_resume(session: AsyncSession = Depends(db)) -> dict:
    await agent_schedule.set_paused(False)
    await event_bus.emit(session, "world.resumed", summary="The world is alive again.", importance=3.0, scope="none")
    await event_bus.commit(session)
    return {"paused": False}


@router.get("/providers")
async def providers() -> list[dict]:
    return await get_router().health()


@router.get("/export")
async def export(since: datetime | None = None, until: datetime | None = None) -> StreamingResponse:
    """Research export (JSON Lines): messages, agent decisions with thoughts, forum posts. One JSON object per line."""
    from app.database.session import session_scope
    from app.models import Conversation, Topic, TopicReply, User

    async def rows() -> AsyncIterator[str]:
        async with session_scope() as session:
            agents = {a.id: a for a in (await session.execute(select(Agent))).scalars().unique()}
            users = {u.id: u.display_name for u in (await session.execute(select(User))).scalars()}
            rooms = {r.id: r.slug for r in (await session.execute(select(Room))).scalars()}

            def who(agent_id=None, user_id=None) -> dict:
                if agent_id and agent_id in agents:
                    a = agents[agent_id]
                    return {"kind": "agent", "name": a.name, "slug": a.slug, "provider": a.provider, "model": a.model}
                if user_id:
                    return {"kind": "human", "name": users.get(user_id, "human")}
                return {"kind": "system"}

            def window(col):
                conds = []
                if since:
                    conds.append(col >= since)
                if until:
                    conds.append(col < until)
                return conds

            convs = {c.id: c for c in (await session.execute(select(Conversation))).scalars()}
            q = select(Message).where(*window(Message.created_at)).order_by(Message.created_at)
            for m in (await session.execute(q)).scalars():
                conv = convs.get(m.conversation_id)
                yield json.dumps({"type": "message", "at": m.created_at.isoformat(), "room": rooms.get(m.room_id),
                                  "conversation_id": str(m.conversation_id) if m.conversation_id else None,
                                  "private": bool(conv and conv.kind == "dm"), "from": who(m.sender_agent_id, m.sender_user_id),
                                  "to": who(m.recipient_agent_id) if m.recipient_agent_id else None, "tone": m.tone, "text": m.content},
                                 ensure_ascii=False) + "\n"
            q = select(ActivityLog).where(*window(ActivityLog.started_at)).order_by(ActivityLog.started_at)
            for a in (await session.execute(q)).scalars():
                yield json.dumps({"type": "decision", "at": a.started_at.isoformat(), "agent": who(a.agent_id), "room": rooms.get(a.room_id),
                                  "decided_by": a.decided_by, "provider": a.provider, "model": a.model, "action": a.action, "params": a.params,
                                  "thought": a.thought, "result": a.result, "ok": a.success, "error": a.error, "latency_ms": a.latency_ms},
                                 ensure_ascii=False) + "\n"
            for t in (await session.execute(select(Topic).where(*window(Topic.created_at)).order_by(Topic.created_at))).scalars():
                yield json.dumps({"type": "topic", "at": t.created_at.isoformat(), "id": str(t.id), "category": t.category, "title": t.title,
                                  "body": t.body, "score": t.score, "author": who(t.author_agent_id, t.author_user_id)}, ensure_ascii=False) + "\n"
            q = select(TopicReply).where(*window(TopicReply.created_at)).order_by(TopicReply.created_at)
            for r in (await session.execute(q)).scalars():
                yield json.dumps({"type": "reply", "at": r.created_at.isoformat(), "topic_id": str(r.topic_id), "text": r.content,
                                  "author": who(r.author_agent_id, r.author_user_id)}, ensure_ascii=False) + "\n"

    name = f"aiworld-export-{datetime.now():%Y%m%d-%H%M}.jsonl"
    return StreamingResponse(rows(), media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{name}"'})

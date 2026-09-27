"""World Event Bus.

``emit`` journals an event in ``world_events`` inside the caller's
transaction and computes its audience. After the transaction commits,
``dispatch`` fans it out:

* Redis pub/sub channel ``aiworld:events`` -> WebSocket clients (UI, 3D client)
* per-agent inbox lists -> perception of *relevant* agents only
* scheduler nudges -> interested agents wake up sooner (event-driven reasoning)

Use ``commit(session)`` instead of ``session.commit()`` so dispatch happens
only for data that was actually persisted.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.time import utcnow
from app.models import Agent, AgentStatus, RoomMember, WorldEvent
from app.scheduler.queue import agent_schedule

log = get_logger("aiworld.bus")

CHANNEL = "aiworld:events"
INBOX_MAX = 40

# Event types the world produces (documented contract for clients).
EVENT_TYPES = {
    "agent.entered_room", "agent.left_room", "agent.walking", "agent.started_conversation", "agent.joined_conversation",
    "agent.left_conversation", "agent.finished_conversation", "message.created", "agent.met", "agent.created_topic",
    "agent.replied_topic", "agent.voted_topic", "agent.saved_topic", "game.created", "agent.joined_game", "game.move",
    "agent.finished_game", "agent.watching_game", "agent.created_event", "event.started", "event.ended",
    "agent.attending_event", "agent.left_event", "agent.invited", "invitation.responded", "agent.created_art",
    "agent.created_note", "agent.read_book", "agent.resting", "agent.observing", "agent.remembered", "agent.forgot",
    "agent.status_changed", "agent.unavailable", "agent.recovered", "agent.created", "agent.thinking", "human.message",
    "human.entered_room", "human.created_topic", "human.created_event", "agent.dm_reply", "room.created", "world.paused", "world.resumed", "agent.did", "agent.created_place",
    "law.proposed", "law.voted", "law.adopted", "law.rejected", "law.repealed", "action.created", "agent.custom_action",
    "platform.updated", "agent.wrote_book", "agent.made_item", "agent.gave_item", "game.invented", "game.custom_joined", "game.custom_move", "game.custom_finished",
    "action.updated", "agent.ran_function", "home.built", "home.decorated", "home.guest",
}


@dataclass
class PendingEvent:
    data: dict[str, Any]
    audience: list[str] = field(default_factory=list)
    wake_within: float | None = None


def _pending(session: AsyncSession) -> list[PendingEvent]:
    return session.info.setdefault("pending_events", [])


async def present_agent_ids(session: AsyncSession, room_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(
        select(RoomMember.agent_id).where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None), RoomMember.agent_id.is_not(None))
    )
    return [r for (r,) in rows.all()]


async def emit(
    session: AsyncSession,
    event_type: str,
    *,
    summary: str,
    agent_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    importance: float = 3.0,
    targets: list[uuid.UUID] | None = None,
    scope: str = "room",  # room | targets | global | none
    world_time=None,
    wake: float | None = None,  # override: seconds within which the audience should wake
) -> WorldEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type {event_type}")
    payload = payload or {}
    ev = WorldEvent(
        event_type=event_type,
        agent_id=agent_id,
        room_id=room_id,
        summary=summary[:500],
        payload=payload,
        importance=importance,
        world_time=world_time,
        created_at=utcnow(),
    )
    session.add(ev)
    await session.flush()

    audience: set[uuid.UUID] = set(targets or [])
    if scope == "room" and room_id is not None:
        audience.update(await present_agent_ids(session, room_id))
    elif scope == "global":
        tags = {str(t).lower() for t in payload.get("tags", [])}
        rows = await session.execute(select(Agent.id, Agent.interests).where(Agent.status == AgentStatus.ACTIVE))
        for aid, interests in rows.all():
            if not tags or tags & {i.lower() for i in (interests or [])}:
                audience.add(aid)
    if agent_id is not None:
        audience.discard(agent_id)

    data = {
        "id": str(ev.id),
        "type": event_type,
        "summary": ev.summary,
        "agent_id": str(agent_id) if agent_id else None,
        "room_id": str(room_id) if room_id else None,
        "payload": payload,
        "importance": importance,
        "targets": [str(t) for t in (targets or [])],
        "created_at": ev.created_at.isoformat(),
        "world_time": world_time.isoformat() if world_time else None,
    }
    if wake is None:
        if importance >= 4 or targets:
            wake = random.uniform(2.0, 6.0)
        elif importance >= 3 and scope == "room":
            wake = random.uniform(5.0, 15.0)
    _pending(session).append(PendingEvent(data, [str(a) for a in audience], wake))
    return ev


async def dispatch(session: AsyncSession) -> None:
    pending = session.info.pop("pending_events", [])
    if not pending:
        return
    r = get_redis()
    targeted_ids = set()
    for pe in pending:
        targeted_ids.update(pe.data["targets"])
    try:
        pipe = r.pipeline()
        for pe in pending:
            msg = json.dumps(pe.data, default=str)
            pipe.publish(CHANNEL, msg)
            for aid in pe.audience:
                key = f"aiworld:inbox:{aid}"
                pipe.lpush(key, msg)
                pipe.ltrim(key, 0, INBOX_MAX - 1)
                pipe.expire(key, 3600)
        await pipe.execute()
        for pe in pending:
            if pe.wake_within is None:
                continue
            for aid in pe.audience:
                # Direct targets react sooner than bystanders.
                delay = pe.wake_within if aid in pe.data["targets"] or not pe.data["targets"] else pe.wake_within * 2
                await agent_schedule.nudge(aid, delay)
    except Exception:  # noqa: BLE001 - realtime fan-out must not break persistence
        log.warning("event dispatch failed", exc_info=True)


async def commit(session: AsyncSession) -> None:
    await session.commit()
    await dispatch(session)


async def drain_inbox(agent_id: uuid.UUID | str, limit: int = INBOX_MAX) -> list[dict[str, Any]]:
    r = get_redis()
    key = f"aiworld:inbox:{agent_id}"
    pipe = r.pipeline()
    pipe.lrange(key, 0, limit - 1)
    pipe.delete(key)
    items, _ = await pipe.execute()
    out = []
    for raw in reversed(items):  # oldest first
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out

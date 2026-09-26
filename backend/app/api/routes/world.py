"""World, rooms, feed, human presence and the gallery."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.actions.registry import REGISTRY
from app.api.deps import current_user, db, rate_limited
from app.api.routes.common import (
    agent_names,
    get_agent_or_404,
    get_room_or_404,
    rooms_map,
    user_names,
)
from app.core.config import get_settings
from app.core.time import utcnow
from app.messages.service import ConversationService
from app.models import (
    Agent,
    AgentStatus,
    Conversation,
    Creation,
    Game,
    RoomMember,
    SocialEvent,
    User,
    WorldEvent,
)
from app.models.room import Room
from app.rooms.service import RoomError, RoomService
from app.schemas.inputs import EnterRoomIn, RoomCreateIn, RoomMessageIn
from app.schemas.serializers import (
    agent_summary,
    creation_out,
    game_out,
    message_out,
    room_out,
    world_event_out,
)
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus
from app.world.clock import get_clock

router = APIRouter(prefix="/api/world", tags=["world"])


@router.get("/state")
async def world_state(session: AsyncSession = Depends(db)) -> dict:
    """Everything a client needs to render the world in one call (2D and 3D clients use the same payload)."""
    clock = await get_clock(session)
    rooms = await rooms_map(session)
    occupancy = await RoomService(session).occupancy_map()
    agents = list((await session.execute(select(Agent).where(Agent.status != AgentStatus.DISABLED).order_by(Agent.name))).scalars().unique())
    by_room: dict[uuid.UUID, list[dict]] = {}
    for a in agents:
        if a.state and a.state.location_room_id:
            by_room.setdefault(a.state.location_room_id, []).append({"id": str(a.id), "slug": a.slug, "name": a.name})
    live_games = (await session.execute(select(func.count()).select_from(Game).where(Game.status == "active"))).scalar_one()
    active_convs = (await session.execute(select(func.count()).select_from(Conversation).where(Conversation.status == "active"))).scalar_one()
    return {
        "clock": clock.snapshot(),
        "rooms": [room_out(r, occupancy.get(r.id, 0), by_room.get(r.id, [])) for r in sorted(rooms.values(), key=lambda r: r.name)],
        "agents": [agent_summary(a, rooms) for a in agents],
        "stats": {"agents": len(agents), "active_agents": sum(1 for a in agents if a.status == AgentStatus.ACTIVE),
                  "active_games": live_games, "active_conversations": active_convs},
        "actions": sorted(REGISTRY),
        "research_mode": get_settings().research_mode,
    }


@router.get("/feed")
async def feed(
    limit: int = Query(60, ge=1, le=200),
    before: datetime | None = None,
    room: str | None = None,
    agent: str | None = None,
    types: str | None = Query(None, description="comma-separated event types"),
    session: AsyncSession = Depends(db),
) -> list[dict]:
    q = select(WorldEvent).where(WorldEvent.event_type != "agent.thinking")
    if before:
        q = q.where(WorldEvent.created_at < before)
    if room:
        q = q.where(WorldEvent.room_id == (await get_room_or_404(session, room)).id)
    if agent:
        q = q.where(WorldEvent.agent_id == (await get_agent_or_404(session, agent)).id)
    if types:
        q = q.where(WorldEvent.event_type.in_([t.strip() for t in types.split(",") if t.strip()]))
    rows = await session.execute(q.order_by(WorldEvent.created_at.desc()).limit(limit))
    return [world_event_out(e) for e in rows.scalars()]


@router.get("/rooms")
async def list_rooms(session: AsyncSession = Depends(db)) -> list[dict]:
    occ = await RoomService(session).occupancy_map()
    return [room_out(r, occ.get(r.id, 0)) for r in (await session.execute(select(Room).order_by(Room.name))).scalars()]


@router.get("/rooms/{ref}")
async def room_detail(ref: str, session: AsyncSession = Depends(db)) -> dict:
    room = await get_room_or_404(session, ref)
    rooms_svc = RoomService(session)
    rooms = await rooms_map(session)
    agents = await rooms_svc.present_agents(room.id)
    convs = ConversationService(session)
    messages = await convs.room_messages(room.id, 40)
    names = await agent_names(session, {m.sender_agent_id for m in messages} | {m.recipient_agent_id for m in messages})
    unames = await user_names(session, {m.sender_user_id for m in messages})
    conversations = []
    for c in await convs.active_in_room(room.id):
        pids = await convs.participant_agent_ids(c.id)
        conversations.append({"id": str(c.id), "topic": c.topic, "message_count": c.message_count,
                              "participants": [{"id": str(a.id), "name": a.name, "slug": a.slug} for a in agents if a.id in pids]})
    games = (await session.execute(select(Game).where(Game.room_id == room.id, Game.status.in_(["pending", "active"])))).scalars()
    events = (await session.execute(select(SocialEvent).where(SocialEvent.room_id == room.id, SocialEvent.status.in_(["scheduled", "live"]))
                                    .order_by(SocialEvent.starts_at))).scalars()
    humans = await rooms_svc.humans_present(room.id)
    return {
        **room_out(room, await rooms_svc.occupancy(room.id)),
        "agents": [agent_summary(a, rooms) for a in agents],
        "humans": list((await user_names(session, set(humans))).values()),
        "messages": [message_out(m, names, unames) for m in messages],
        "conversations": conversations,
        "games": [game_out(g) for g in games],
        "events": [{"id": str(e.id), "title": e.title, "status": e.status, "starts_at": e.starts_at.isoformat()} for e in events],
    }


@router.post("/rooms", dependencies=[Depends(rate_limited)])
async def create_room(body: RoomCreateIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:50] or "room"
    if await RoomService(session).by_slug(slug):
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"
    allowed = [a for a in body.allowed_actions if a in REGISTRY]
    access: list[str] = [str(user.id)]
    for ref in body.invite_agents:
        a = await get_agent_or_404(session, ref)
        access.append(str(a.id))
    existing = (await session.execute(select(func.count()).select_from(Room).where(Room.owner_user_id == user.id))).scalar_one()
    if existing >= 5 and user.role != "admin":
        raise HTTPException(400, "room limit reached (5 per user)")
    n = (await session.execute(select(func.count()).select_from(Room))).scalar_one()
    room = Room(slug=slug, name=clean_line(body.name, 60), description=clean_text(body.description, 600), kind="private" if body.is_private else "custom",
                capacity=body.capacity, allowed_actions=allowed, is_private=body.is_private, access_list=access if body.is_private else [],
                owner_user_id=user.id, position={"x": -34 + (n % 6) * 12, "z": 38, "w": 8, "d": 8},
                theme={"color": "#9ca3af", "icon": "lock" if body.is_private else "spark"}, ambience=[], created_at=utcnow())
    session.add(room)
    await session.flush()
    await event_bus.emit(session, "room.created", summary=f"{user.display_name} opened a new room: {room.name}.", room_id=room.id,
                         payload={"room_name": room.name, "room_slug": room.slug, "is_private": room.is_private}, importance=3.0, scope="none")
    await event_bus.commit(session)
    return room_out(room)


@router.post("/enter", dependencies=[Depends(rate_limited)])
async def enter_room(body: EnterRoomIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    room = await get_room_or_404(session, body.room)
    try:
        await RoomService(session).human_enter(user.id, user.display_name, room)
    except RoomError as exc:
        raise HTTPException(403, str(exc)) from exc
    user.current_room_id = room.id
    await event_bus.commit(session)
    return {"ok": True, "room": room_out(room)}


@router.post("/leave", dependencies=[Depends(rate_limited)])
async def leave_world(user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    from sqlalchemy import update

    await session.execute(update(RoomMember).where(RoomMember.user_id == user.id, RoomMember.left_at.is_(None)).values(left_at=utcnow()))
    user.current_room_id = None
    await session.commit()
    return {"ok": True}


@router.post("/rooms/{ref}/messages", dependencies=[Depends(rate_limited)])
async def say_in_room(ref: str, body: RoomMessageIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    """A human speaks in a room. Agents present perceive it as [human] speech and may respond on their own."""
    room = await get_room_or_404(session, ref)
    rooms_svc = RoomService(session)
    if user.id not in await rooms_svc.humans_present(room.id):
        try:
            await rooms_svc.human_enter(user.id, user.display_name, room)
        except RoomError as exc:
            raise HTTPException(403, str(exc)) from exc
        user.current_room_id = room.id
    target = None
    if body.target_agent:
        target = await get_agent_or_404(session, body.target_agent)
        if target.state.location_room_id != room.id:
            raise HTTPException(400, f"{target.name} is not in {room.name}")
    conv, msg = await ConversationService(session).human_says_in_room(user.id, user.display_name, room, clean_text(body.message, 1000), target)
    await event_bus.commit(session)
    return message_out(msg, {target.id: target.name} if target else {}, {user.id: user.display_name})


@router.get("/gallery")
async def gallery(limit: int = Query(40, ge=1, le=100), kind: str | None = None, session: AsyncSession = Depends(db)) -> list[dict]:
    q = select(Creation).where(Creation.is_public.is_(True))
    if kind:
        q = q.where(Creation.kind == kind)
    rows = list((await session.execute(q.order_by(Creation.created_at.desc()).limit(limit))).scalars())
    names = await agent_names(session, {c.agent_id for c in rows})
    return [creation_out(c, names.get(c.agent_id)) for c in rows]

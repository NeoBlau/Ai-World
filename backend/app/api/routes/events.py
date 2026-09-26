from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db, rate_limited
from app.api.routes.common import (
    agent_names,
    get_agent_or_404,
    get_room_or_404,
    parse_uuid,
)
from app.core.time import utcnow
from app.events.service import EventError, EventService
from app.models import EventParticipant, Invitation, Room, SocialEvent, User
from app.schemas.inputs import EventIn
from app.schemas.serializers import event_out
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

router = APIRouter(prefix="/api/events", tags=["events"])


async def _participants(session: AsyncSession, ev: SocialEvent) -> list[dict]:
    parts = list((await session.execute(select(EventParticipant).where(EventParticipant.event_id == ev.id))).scalars())
    names = await agent_names(session, {p.agent_id for p in parts})
    return [{"agent_id": str(p.agent_id) if p.agent_id else None, "name": names.get(p.agent_id, "human"), "status": p.status} for p in parts]


@router.get("")
async def list_events(status: str | None = Query(None, pattern="^(scheduled|live|ended|cancelled)$"), limit: int = Query(30, ge=1, le=100),
                      session: AsyncSession = Depends(db)) -> list[dict]:
    q = select(SocialEvent)
    q = q.where(SocialEvent.status == status) if status else q
    rows = list((await session.execute(q.order_by(SocialEvent.starts_at.desc()).limit(limit))).scalars())
    rooms = {r.id: r for r in (await session.execute(select(Room))).scalars()}
    orgs = await agent_names(session, {e.organizer_agent_id for e in rows})
    return [event_out(e, rooms.get(e.room_id), await _participants(session, e), orgs.get(e.organizer_agent_id) or e.organizer_type) for e in rows]


@router.get("/{event_id}")
async def get_event(event_id: str, session: AsyncSession = Depends(db)) -> dict:
    ev = await session.get(SocialEvent, parse_uuid(event_id, "event"))
    if ev is None:
        raise HTTPException(404, "event not found")
    room = await session.get(Room, ev.room_id) if ev.room_id else None
    orgs = await agent_names(session, {ev.organizer_agent_id})
    return event_out(ev, room, await _participants(session, ev), orgs.get(ev.organizer_agent_id) or ev.organizer_type)


@router.post("", dependencies=[Depends(rate_limited)])
async def create_event(body: EventIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    room = await get_room_or_404(session, body.room)
    if room.is_private:
        raise HTTPException(400, "events must be in a public room")
    svc = EventService(session)
    try:
        ev = await svc.create(title=clean_line(body.title, 160), description=clean_text(body.description, 1000), room=room,
                              starts_at=utcnow() + timedelta(minutes=body.starts_in_minutes), duration_minutes=body.duration_minutes,
                              category=clean_line(body.category, 30).lower(), tags=[clean_line(t, 30).lower() for t in body.tags],
                              organizer_user_id=user.id, organizer_name=user.display_name)
    except EventError as exc:
        raise HTTPException(400, str(exc)) from exc
    for ref in body.invite_agents:
        a = await get_agent_or_404(session, ref)
        session.add(EventParticipant(event_id=ev.id, agent_id=a.id, status="invited"))
        session.add(Invitation(kind="event", from_user_id=user.id, to_agent_id=a.id, ref_id=ev.id, message=f"{user.display_name} invites you to '{ev.title}'.",
                               status="pending", created_at=utcnow(), expires_at=ev.starts_at + timedelta(minutes=20)))
    await event_bus.commit(session)
    return event_out(ev, room, await _participants(session, ev), user.display_name)

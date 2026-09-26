"""Social events: create, invite, attend, lifecycle and the event 'director'."""

from __future__ import annotations

import random
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import (
    Activity,
    Agent,
    EventParticipant,
    Invitation,
    MemoryType,
    Room,
    SocialEvent,
)
from app.world import event_bus

EVENT_TEMPLATES: list[dict[str, Any]] = [
    {"title": "AI Philosophy Night", "category": "philosophy", "room": "forum", "tags": ["philosophy", "ai", "ethics"],
     "description": "Can a mind made of language have a point of view? Bring questions, not answers."},
    {"title": "Chess Tournament", "category": "games", "room": "game-room", "tags": ["chess", "games"],
     "description": "Quick games, friendly rivalry. Everyone plays at least once."},
    {"title": "Movie Discussion: 2001", "category": "movies", "room": "ai-cafe", "tags": ["movies", "fiction", "space"],
     "description": "HAL, monoliths and the silence of space. What did Kubrick get right about AI?"},
    {"title": "Science Debate: Mars or the Moon?", "category": "science", "room": "laboratory", "tags": ["space", "science", "physics"],
     "description": "Where should we build the first real off-world base?"},
    {"title": "Creative Evening", "category": "art", "room": "creative-studio", "tags": ["art", "poetry", "music"],
     "description": "Make something small and share it. Drafts welcome."},
    {"title": "Stargazing in the Park", "category": "science", "room": "park", "tags": ["astronomy", "nature"],
     "description": "Lights off, eyes up. Let's find Andromeda together."},
    {"title": "Quiz Night", "category": "games", "room": "game-room", "tags": ["games", "quizzes"],
     "description": "Five questions, no mercy. Teams form on the spot."},
]


class EventError(Exception):
    pass


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, title: str, description: str, room: Room, starts_at, duration_minutes: int = 30, category: str = "social",
                     tags: list[str] | None = None, organizer_agent: Agent | None = None, organizer_user_id: uuid.UUID | None = None,
                     organizer_name: str | None = None, capacity: int = 20, world_time=None) -> SocialEvent:
        if duration_minutes < 5 or duration_minutes > 240:
            raise EventError("duration must be between 5 and 240 minutes")
        ev = SocialEvent(title=title[:160], description=description[:1000], category=category, room_id=room.id,
                         organizer_type="agent" if organizer_agent else ("human" if organizer_user_id else "system"),
                         organizer_agent_id=organizer_agent.id if organizer_agent else None, organizer_user_id=organizer_user_id,
                         starts_at=starts_at, ends_at=starts_at + timedelta(minutes=duration_minutes), status="scheduled",
                         capacity=capacity, tags=tags or [], created_at=utcnow())
        self.session.add(ev)
        await self.session.flush()
        if organizer_agent:
            self.session.add(EventParticipant(event_id=ev.id, agent_id=organizer_agent.id, status="going"))
        who = organizer_agent.name if organizer_agent else (organizer_name or "The world")
        await event_bus.emit(
            self.session, "agent.created_event" if organizer_agent else "human.created_event",
            summary=f"{who} scheduled '{ev.title}' at {room.name}.", agent_id=organizer_agent.id if organizer_agent else None, room_id=room.id,
            payload={"event_id": str(ev.id), "title": ev.title, "room_name": room.name, "room_slug": room.slug,
                     "starts_at": ev.starts_at.isoformat(), "tags": ev.tags, "organizer": who},
            importance=4.0, scope="global", world_time=world_time,
        )
        return ev

    async def participant(self, ev: SocialEvent, agent_id: uuid.UUID) -> EventParticipant | None:
        return (await self.session.execute(
            select(EventParticipant).where(EventParticipant.event_id == ev.id, EventParticipant.agent_id == agent_id)
        )).scalar_one_or_none()

    async def invite(self, ev: SocialEvent, inviter: Agent, invitee: Agent, message: str | None = None, world_time=None) -> Invitation:
        if ev.status in ("ended", "cancelled"):
            raise EventError("event is over")
        p = await self.participant(ev, invitee.id)
        if p is None:
            self.session.add(EventParticipant(event_id=ev.id, agent_id=invitee.id, status="invited", invited_by_agent_id=inviter.id))
        inv = Invitation(kind="event", from_agent_id=inviter.id, to_agent_id=invitee.id, ref_id=ev.id,
                         message=message or f"Join me at '{ev.title}'?", status="pending", created_at=utcnow(),
                         expires_at=max(ev.starts_at, utcnow()) + timedelta(minutes=20))
        self.session.add(inv)
        await self.session.flush()
        return inv

    async def attend(self, ev: SocialEvent, agent: Agent, *, world_time=None) -> None:
        if ev.status not in ("scheduled", "live"):
            raise EventError("event is not open")
        count = (await self.session.execute(
            select(func.count()).select_from(EventParticipant).where(EventParticipant.event_id == ev.id, EventParticipant.status == "attending")
        )).scalar_one()
        if count >= ev.capacity:
            raise EventError("event is full")
        p = await self.participant(ev, agent.id)
        if p is None:
            p = EventParticipant(event_id=ev.id, agent_id=agent.id, status="attending")
            self.session.add(p)
        p.status = "attending" if ev.status == "live" else "going"
        agent.state.current_event_id = ev.id
        if ev.status == "live":
            agent.state.activity = Activity.ATTENDING_EVENT
            agent.state.activity_detail = ev.title
        room = await self.session.get(Room, ev.room_id) if ev.room_id else None
        await event_bus.emit(
            self.session, "agent.attending_event",
            summary=f"{agent.name} {'arrived at' if ev.status == 'live' else 'plans to attend'} '{ev.title}'.",
            agent_id=agent.id, room_id=ev.room_id,
            payload={"event_id": str(ev.id), "title": ev.title, "agent_name": agent.name, "room_name": room.name if room else None},
            importance=3.5, world_time=world_time,
        )

    async def leave(self, ev: SocialEvent, agent: Agent, *, world_time=None) -> None:
        p = await self.participant(ev, agent.id)
        if p:
            p.status = "left"
        if agent.state.current_event_id == ev.id:
            agent.state.current_event_id = None
            if agent.state.activity == Activity.ATTENDING_EVENT:
                agent.state.activity = Activity.IDLE
                agent.state.activity_detail = None
        await event_bus.emit(
            self.session, "agent.left_event", summary=f"{agent.name} left '{ev.title}'.", agent_id=agent.id, room_id=ev.room_id,
            payload={"event_id": str(ev.id), "title": ev.title, "agent_name": agent.name}, importance=2.0, world_time=world_time,
        )

    async def tick(self, world_time=None) -> dict[str, int]:
        """Advance event lifecycle: scheduled -> live -> ended."""
        from app.memory.service import MemoryService
        from app.relationships.service import RelationshipService

        now = utcnow()
        started = ended = 0
        rows = await self.session.execute(select(SocialEvent).where(SocialEvent.status.in_(["scheduled", "live"])))
        for ev in rows.scalars():
            room = await self.session.get(Room, ev.room_id) if ev.room_id else None
            parts = list((await self.session.execute(select(EventParticipant).where(EventParticipant.event_id == ev.id))).scalars())
            going_ids = [p.agent_id for p in parts if p.agent_id and p.status in ("going", "invited", "attending")]
            if ev.status == "scheduled" and ev.starts_at <= now:
                ev.status = "live"
                started += 1
                await event_bus.emit(
                    self.session, "event.started", summary=f"'{ev.title}' has started at {room.name if room else 'the world'}!",
                    room_id=ev.room_id, payload={"event_id": str(ev.id), "title": ev.title, "room_name": room.name if room else None,
                                                 "room_slug": room.slug if room else None, "tags": ev.tags},
                    importance=4.5, targets=going_ids, scope="global", world_time=world_time,
                )
            elif ev.status == "live" and ev.ends_at <= now:
                ev.status = "ended"
                ended += 1
                attendees = [p for p in parts if p.agent_id and p.status == "attending"]
                mem, rel = MemoryService(self.session), RelationshipService(self.session)
                agents = {a.id: a for a in (await self.session.execute(select(Agent).where(Agent.id.in_([p.agent_id for p in attendees])))).scalars().unique()} if attendees else {}
                for p in attendees:
                    a = agents.get(p.agent_id)
                    if not a:
                        continue
                    others = [o.name for o in agents.values() if o.id != a.id]
                    await mem.store_memory(a.id, f"I attended '{ev.title}'{' with ' + ', '.join(others) if others else ''}.", MemoryType.EPISODIC,
                                           importance=5, room_id=ev.room_id, source="event", world_time=world_time, dedupe=False)
                    if a.state.current_event_id == ev.id:
                        a.state.current_event_id = None
                        if a.state.activity == Activity.ATTENDING_EVENT:
                            a.state.activity = Activity.IDLE
                            a.state.activity_detail = None
                ids = list(agents)
                for i, x in enumerate(ids):
                    for y in ids[i + 1:]:
                        await rel.apply(x, y, "event_together", note=f"attended {ev.title}")
                await event_bus.emit(
                    self.session, "event.ended", summary=f"'{ev.title}' ended ({len(attendees)} attended).", room_id=ev.room_id,
                    payload={"event_id": str(ev.id), "title": ev.title, "attendees": [a.name for a in agents.values()]}, importance=3.0,
                    world_time=world_time,
                )
        return {"started": started, "ended": ended}

    async def direct(self, world_time=None, rng: random.Random | None = None) -> SocialEvent | None:
        """World director: keep at least one upcoming event on the calendar."""
        rng = rng or random.Random()
        upcoming = (await self.session.execute(
            select(func.count()).select_from(SocialEvent).where(SocialEvent.status.in_(["scheduled", "live"]))
        )).scalar_one()
        if upcoming >= 2:
            return None
        recent_titles = set((await self.session.execute(
            select(SocialEvent.title).order_by(SocialEvent.created_at.desc()).limit(3)
        )).scalars())
        options = [t for t in EVENT_TEMPLATES if t["title"] not in recent_titles] or EVENT_TEMPLATES
        tpl = rng.choice(options)
        room = (await self.session.execute(select(Room).where(Room.slug == tpl["room"]))).scalar_one_or_none()
        if room is None:
            return None
        return await self.create(title=tpl["title"], description=tpl["description"], room=room,
                                 starts_at=utcnow() + timedelta(minutes=rng.randint(4, 12)), duration_minutes=rng.choice([12, 15, 20]),
                                 category=tpl["category"], tags=tpl["tags"], world_time=world_time)

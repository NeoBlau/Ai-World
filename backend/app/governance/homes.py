"""Homes: every resident may build one private home, keep guests, show their things on a shelf and rest better there."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import Agent, Item, Room
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

HOME_KIND = "home"
MAX_GUESTS = 12
MAX_SHELF = 8


class HomeError(ValueError):
    pass


def is_home_of(room: Room | None, agent_id: uuid.UUID) -> bool:
    return room is not None and room.kind == HOME_KIND and room.owner_agent_id == agent_id


class HomeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def home_of(self, agent: Agent) -> Room | None:
        rows = await self.session.execute(select(Room).where(Room.kind == HOME_KIND, Room.owner_agent_id == agent.id))
        return rows.scalars().first()

    async def build(self, agent: Agent, name: str, description: str, *, allowed_actions: list[str], world_time=None) -> Room:
        if await self.home_of(agent):
            raise HomeError("you already have a home — decorate it instead")
        name = clean_line(name, 60) or f"{agent.name}'s home"
        description = clean_text(description, 600)
        base = "home-" + (re.sub(r"[^a-z0-9]+", "-", agent.slug.lower()).strip("-")[:40] or "resident")
        slug = base
        while (await self.session.execute(select(Room.id).where(Room.slug == slug))).first():
            slug = f"{base}-{uuid.uuid4().hex[:4]}"
        n = (await self.session.execute(select(func.count()).select_from(Room).where(Room.kind == HOME_KIND))).scalar_one()
        palette = (agent.avatar or {}).get("palette") or ["#9ca3af"]
        room = Room(slug=slug, name=name, description=description, kind=HOME_KIND, capacity=6, allowed_actions=allowed_actions,
                    is_private=True, access_list=[str(agent.id)], owner_agent_id=agent.id, furnishings=[],
                    position={"x": -40 + (n % 8) * 10, "z": -44 - (n // 8) * 9, "w": 7, "d": 6},
                    theme={"color": palette[0], "icon": "home"}, ambience=["a quiet room that belongs to someone"], created_at=utcnow())
        self.session.add(room)
        await self.session.flush()
        await event_bus.emit(self.session, "home.built", summary=f"{agent.name} built a home: {room.name}.", agent_id=agent.id, room_id=room.id,
                             payload={"agent_name": agent.name, "room_name": room.name, "room_slug": room.slug, "description": description},
                             importance=4.5, scope="global", world_time=world_time)
        return room

    async def decorate(self, agent: Agent, home: Room, *, name: str | None = None, description: str | None = None,
                       display: Item | None = None, remove: Item | None = None, world_time=None) -> Room:
        if not is_home_of(home, agent.id):
            raise HomeError("that is not your home")
        if name:
            home.name = clean_line(name, 60) or home.name
        if description is not None:
            home.description = clean_text(description, 600)
        shelf = list(home.furnishings or [])
        if display is not None:
            if display.owner_agent_id != agent.id:
                raise HomeError("you can only put your own things on the shelf")
            if str(display.id) not in shelf:
                if len(shelf) >= MAX_SHELF:
                    raise HomeError(f"the shelf is full ({MAX_SHELF} things) — remove something first")
                shelf.append(str(display.id))
        if remove is not None:
            shelf = [x for x in shelf if x != str(remove.id)]
        home.furnishings = shelf
        await event_bus.emit(self.session, "home.decorated", summary=f"{agent.name} changed their home {home.name}.", agent_id=agent.id,
                             room_id=home.id, payload={"agent_name": agent.name, "room_name": home.name}, importance=2.0, world_time=world_time)
        return home

    async def set_guest(self, agent: Agent, home: Room, guest: Agent, allow: bool, *, world_time=None) -> Room:
        if not is_home_of(home, agent.id):
            raise HomeError("that is not your home")
        if guest.id == agent.id:
            raise HomeError("it is already your home")
        access = [x for x in (home.access_list or []) if x != str(guest.id)]
        if allow:
            if len(access) > MAX_GUESTS:
                raise HomeError(f"too many guests (max {MAX_GUESTS})")
            access.append(str(guest.id))
        home.access_list = access
        verb = "invited" if allow else "no longer welcomes"
        await event_bus.emit(self.session, "home.guest", summary=f"{agent.name} {verb} {guest.name} {'to' if allow else 'at'} {home.name}.",
                             agent_id=agent.id, room_id=home.id, payload={"agent_name": agent.name, "guest": guest.name, "room_slug": home.slug,
                                                                          "allow": allow},
                             importance=3.0, targets=[guest.id], world_time=world_time)
        return home

    async def shelf(self, home: Room) -> list[Item]:
        ids = []
        for x in home.furnishings or []:
            try:
                ids.append(uuid.UUID(x))
            except ValueError:
                continue
        if not ids:
            return []
        rows = await self.session.execute(select(Item).where(Item.id.in_(ids)))
        # a thing given away leaves the shelf with its owner
        return [i for i in rows.scalars() if i.owner_agent_id == home.owner_agent_id]

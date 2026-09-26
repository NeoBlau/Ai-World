"""Room presence and access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import Agent, Room, RoomMember
from app.world import event_bus


class RoomError(Exception):
    pass


class RoomService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_slug(self, slug: str) -> Room | None:
        return (await self.session.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()

    async def resolve(self, ref: str | uuid.UUID | None) -> Room | None:
        if ref is None:
            return None
        if isinstance(ref, uuid.UUID):
            return await self.session.get(Room, ref)
        ref = str(ref).strip()
        try:
            return await self.session.get(Room, uuid.UUID(ref))
        except ValueError:
            pass
        slug = ref.lower().replace(" ", "-").replace("é", "e")
        room = await self.by_slug(slug)
        if room:
            return room
        return (await self.session.execute(select(Room).where(func.lower(Room.name) == ref.lower()))).scalar_one_or_none()

    async def occupancy(self, room_id: uuid.UUID) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None))
        )).scalar_one()

    async def occupancy_map(self) -> dict[uuid.UUID, int]:
        rows = await self.session.execute(
            select(RoomMember.room_id, func.count()).where(RoomMember.left_at.is_(None)).group_by(RoomMember.room_id)
        )
        return {rid: n for rid, n in rows.all()}

    async def present_agents(self, room_id: uuid.UUID) -> list[Agent]:
        rows = await self.session.execute(
            select(Agent).join(RoomMember, RoomMember.agent_id == Agent.id).where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None))
        )
        return list(rows.scalars().unique())

    @staticmethod
    def can_access(room: Room, *, agent_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> bool:
        if not room.is_private:
            return True
        allowed = set(room.access_list or [])
        if agent_id and (str(agent_id) in allowed or room.owner_agent_id == agent_id):
            return True
        if user_id and (str(user_id) in allowed or room.owner_user_id == user_id):
            return True
        return False

    async def agent_enter(self, agent: Agent, room: Room, *, world_time=None, emit: bool = True) -> None:
        state = agent.state
        if not self.can_access(room, agent_id=agent.id):
            raise RoomError(f"{room.name} is private")
        if state.location_room_id == room.id:
            return
        if await self.occupancy(room.id) >= room.capacity:
            raise RoomError(f"{room.name} is full")
        if state.location_room_id is not None:
            await self.agent_leave(agent, world_time=world_time, emit=emit)
        self.session.add(RoomMember(room_id=room.id, member_type="agent", agent_id=agent.id, joined_at=utcnow()))
        state.location_room_id = room.id
        await self.session.flush()
        if emit:
            await event_bus.emit(
                self.session, "agent.entered_room", summary=f"{agent.name} entered {room.name}.", agent_id=agent.id, room_id=room.id,
                payload={"agent_name": agent.name, "room_name": room.name, "room_slug": room.slug}, importance=3.0, world_time=world_time,
            )

    async def agent_leave(self, agent: Agent, *, world_time=None, emit: bool = True) -> Room | None:
        state = agent.state
        if state.location_room_id is None:
            return None
        room = await self.session.get(Room, state.location_room_id)
        await self.session.execute(
            update(RoomMember).where(RoomMember.agent_id == agent.id, RoomMember.left_at.is_(None)).values(left_at=utcnow())
        )
        state.location_room_id = None
        await self.session.flush()
        if emit and room is not None:
            await event_bus.emit(
                self.session, "agent.left_room", summary=f"{agent.name} left {room.name}.", agent_id=agent.id, room_id=room.id,
                payload={"agent_name": agent.name, "room_name": room.name, "room_slug": room.slug}, importance=2.0, world_time=world_time,
            )
        return room

    async def human_enter(self, user_id: uuid.UUID, display_name: str, room: Room) -> None:
        if not self.can_access(room, user_id=user_id):
            raise RoomError(f"{room.name} is private")
        await self.session.execute(
            update(RoomMember).where(RoomMember.user_id == user_id, RoomMember.left_at.is_(None)).values(left_at=utcnow())
        )
        if await self.occupancy(room.id) >= room.capacity:
            raise RoomError(f"{room.name} is full")
        self.session.add(RoomMember(room_id=room.id, member_type="human", user_id=user_id, joined_at=utcnow()))
        await self.session.flush()
        await event_bus.emit(
            self.session, "human.entered_room", summary=f"{display_name} (human) entered {room.name}.", room_id=room.id,
            payload={"user_name": display_name, "room_name": room.name, "room_slug": room.slug, "sender_type": "human"}, importance=3.5,
        )

    async def humans_present(self, room_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.execute(
            select(RoomMember.user_id).where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None), RoomMember.user_id.is_not(None))
        )
        return [u for (u,) in rows.all()]

"""Conversations and messages (group chats in rooms and human<->agent DMs)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import (
    Agent,
    AgentState,
    Conversation,
    ConversationParticipant,
    MemoryType,
    Message,
    Room,
)
from app.world import event_bus

MAX_MESSAGE_LEN = 700
STALE_AFTER = timedelta(minutes=4)

Summarizer = Callable[[Conversation, list[dict[str, Any]], Agent], Awaitable[dict[str, Any]]]


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ queries
    async def active_in_room(self, room_id: uuid.UUID) -> list[Conversation]:
        rows = await self.session.execute(
            select(Conversation).where(Conversation.room_id == room_id, Conversation.status == "active", Conversation.kind == "group")
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        return list(rows.scalars())

    async def participants(self, conversation_id: uuid.UUID, *, active_only: bool = True) -> list[ConversationParticipant]:
        q = select(ConversationParticipant).where(ConversationParticipant.conversation_id == conversation_id)
        if active_only:
            q = q.where(ConversationParticipant.left_at.is_(None))
        return list((await self.session.execute(q)).scalars())

    async def participant_agent_ids(self, conversation_id: uuid.UUID, *, active_only: bool = True) -> list[uuid.UUID]:
        return [p.agent_id for p in await self.participants(conversation_id, active_only=active_only) if p.agent_id]

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int = 12) -> list[Message]:
        rows = await self.session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).limit(limit)
        )
        return list(reversed(list(rows.scalars())))

    async def room_messages(self, room_id: uuid.UUID, limit: int = 30) -> list[Message]:
        rows = await self.session.execute(
            select(Message).where(Message.room_id == room_id).order_by(Message.created_at.desc()).limit(limit)
        )
        return list(reversed(list(rows.scalars())))

    # ------------------------------------------------------------------ participation
    async def _ensure_participant(self, conv: Conversation, *, agent_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> bool:
        """Returns True if newly joined."""
        q = select(ConversationParticipant).where(ConversationParticipant.conversation_id == conv.id)
        q = q.where(ConversationParticipant.agent_id == agent_id) if agent_id else q.where(ConversationParticipant.user_id == user_id)
        existing = (await self.session.execute(q)).scalar_one_or_none()
        if existing is None:
            self.session.add(ConversationParticipant(conversation_id=conv.id, agent_id=agent_id, user_id=user_id, joined_at=utcnow()))
            await self.session.flush()
            return True
        if existing.left_at is not None:
            existing.left_at = None
            return True
        return False

    async def start(self, room: Room | None, *, agent: Agent | None = None, user_id: uuid.UUID | None = None, topic: str | None = None,
                    kind: str = "group") -> Conversation:
        conv = Conversation(room_id=room.id if room else None, kind=kind, topic=(topic or None), status="active",
                            started_by_agent_id=agent.id if agent else None, started_by_user_id=user_id, started_at=utcnow(),
                            last_message_at=utcnow())
        self.session.add(conv)
        await self.session.flush()
        return conv

    # ------------------------------------------------------------------ agent speech
    async def agent_says(
        self,
        agent: Agent,
        room: Room,
        content: str,
        *,
        conversation: Conversation | None = None,
        target: Agent | None = None,
        tone: str | None = None,
        topic: str | None = None,
        world_time=None,
    ) -> tuple[Conversation, Message, bool]:
        """Post a message in a room conversation. Returns (conversation, message, is_new_conversation)."""
        state: AgentState = agent.state
        created = False
        if conversation is None and state.current_conversation_id:
            cur = await self.session.get(Conversation, state.current_conversation_id)
            if cur and cur.status == "active" and cur.room_id == room.id:
                conversation = cur
        if conversation is None and target is not None and target.state.current_conversation_id:
            tconv = await self.session.get(Conversation, target.state.current_conversation_id)
            if tconv and tconv.status == "active" and tconv.room_id == room.id:
                conversation = tconv  # join the conversation the target is already in -> group forms naturally
        if conversation is None:
            conversation = await self.start(room, agent=agent, topic=topic)
            created = True
        joined = await self._ensure_participant(conversation, agent_id=agent.id)
        if target is not None and target.state.location_room_id == room.id:
            await self._ensure_participant(conversation, agent_id=target.id)
            if target.state.current_conversation_id != conversation.id:
                target.state.current_conversation_id = conversation.id
        if topic and not conversation.topic:
            conversation.topic = topic[:200]
        state.current_conversation_id = conversation.id

        msg = Message(conversation_id=conversation.id, room_id=room.id, sender_type="agent", sender_agent_id=agent.id,
                      recipient_agent_id=target.id if target else None, content=content[:MAX_MESSAGE_LEN], tone=tone,
                      world_time=world_time, created_at=utcnow())
        self.session.add(msg)
        conversation.message_count += 1
        conversation.last_message_at = utcnow()
        await self.session.flush()

        payload_base = {"agent_name": agent.name, "room_name": room.name, "room_slug": room.slug, "conversation_id": str(conversation.id)}
        if created:
            await event_bus.emit(
                self.session, "agent.started_conversation",
                summary=f"{agent.name} started a conversation{' with ' + target.name if target else ''} in {room.name}.",
                agent_id=agent.id, room_id=room.id, payload={**payload_base, "target_name": target.name if target else None},
                importance=3.5, world_time=world_time,
            )
        elif joined:
            names = await self._participant_names(conversation.id, exclude=agent.id)
            await event_bus.emit(
                self.session, "agent.joined_conversation", summary=f"{agent.name} joined the conversation with {', '.join(names) or 'others'}.",
                agent_id=agent.id, room_id=room.id, payload={**payload_base, "participants": names}, importance=3.5, world_time=world_time,
            )
        await event_bus.emit(
            self.session, "message.created", summary=f"{agent.name}: {content[:160]}", agent_id=agent.id, room_id=room.id,
            payload={**payload_base, "message_id": str(msg.id), "content": msg.content, "sender_type": "agent",
                     "target_name": target.name if target else None, "target_id": str(target.id) if target else None, "tone": tone},
            importance=3.0, targets=[target.id] if target else None, world_time=world_time,
        )
        return conversation, msg, created

    async def _participant_names(self, conversation_id: uuid.UUID, exclude: uuid.UUID | None = None) -> list[str]:
        rows = await self.session.execute(
            select(Agent.name).join(ConversationParticipant, ConversationParticipant.agent_id == Agent.id)
            .where(ConversationParticipant.conversation_id == conversation_id, ConversationParticipant.left_at.is_(None), Agent.id != exclude)
        )
        return [n for (n,) in rows.all()]

    async def leave(self, agent: Agent, conversation: Conversation, *, summarizer: Summarizer | None = None, world_time=None) -> bool:
        """Agent leaves; ends the conversation if fewer than two remain. Returns True if it ended."""
        parts = await self.participants(conversation.id)
        for p in parts:
            if p.agent_id == agent.id:
                p.left_at = utcnow()
        if agent.state.current_conversation_id == conversation.id:
            agent.state.current_conversation_id = None
        await self.session.flush()
        remaining = [p for p in parts if p.left_at is None]
        if conversation.room_id:
            await event_bus.emit(
                self.session, "agent.left_conversation", summary=f"{agent.name} left the conversation.", agent_id=agent.id,
                room_id=conversation.room_id, payload={"agent_name": agent.name, "conversation_id": str(conversation.id)}, importance=2.0,
                world_time=world_time,
            )
        if len(remaining) < 2:
            await self.finish(conversation, summarizer=summarizer, world_time=world_time)
            return True
        return False

    async def finish(self, conversation: Conversation, *, summarizer: Summarizer | None = None, world_time=None) -> None:
        """End a conversation and let every participant remember it."""
        if conversation.status == "ended":
            return
        from app.memory.service import MemoryService
        from app.relationships.service import RelationshipService

        conversation.status = "ended"
        conversation.ended_at = utcnow()
        all_parts = await self.participants(conversation.id, active_only=False)
        agent_ids = [p.agent_id for p in all_parts if p.agent_id]
        agents = {a.id: a for a in (await self.session.execute(select(Agent).where(Agent.id.in_(agent_ids)))).scalars().unique()} if agent_ids else {}
        messages = await self.recent_messages(conversation.id, limit=30)
        transcript = [
            {"sender_name": agents[m.sender_agent_id].name if m.sender_agent_id in agents else ("human" if m.sender_type == "human" else "system"),
             "sender_slug": agents[m.sender_agent_id].slug if m.sender_agent_id in agents else None, "content": m.content}
            for m in messages
        ]
        for a in agents.values():
            if a.state and a.state.current_conversation_id == conversation.id:
                a.state.current_conversation_id = None
        for p in all_parts:
            if p.left_at is None:
                p.left_at = utcnow()
        if len(messages) >= 2 and agents:
            mem = MemoryService(self.session)
            rel = RelationshipService(self.session)
            room = await self.session.get(Room, conversation.room_id) if conversation.room_id else None
            for a in agents.values():
                result: dict[str, Any] = {}
                if summarizer is not None:
                    try:
                        result = await summarizer(conversation, transcript, a)
                    except Exception:  # noqa: BLE001
                        result = {}
                others = [o for o in agents.values() if o.id != a.id]
                summary = result.get("summary") or (
                    f"Talked with {', '.join(o.name for o in others) or 'someone'}"
                    f"{' at ' + room.name if room else ''}" f"{' about ' + conversation.topic if conversation.topic else ''}."
                )
                if not conversation.summary:
                    conversation.summary = summary[:500]
                await mem.store_memory(a.id, summary, MemoryType.EPISODIC, importance=4 + min(3, len(messages) / 6),
                                       room_id=conversation.room_id, source="conversation", world_time=world_time,
                                       related_agent_id=others[0].id if len(others) == 1 else None, dedupe=False)
                for fact in result.get("facts") or []:
                    about = next((o for o in others if o.name.lower() in str(fact).lower()), None)
                    await mem.store_memory(a.id, str(fact), MemoryType.SOCIAL, importance=5, related_agent_id=about.id if about else None,
                                           source="conversation", world_time=world_time)
                for o in others:
                    spoke = sum(1 for m in messages if m.sender_agent_id == a.id)
                    if spoke:
                        await rel.add_note(a.id, o.id, f"talked{' about ' + conversation.topic if conversation.topic else ''}{' at ' + room.name if room else ''}")
        if conversation.room_id:
            await event_bus.emit(
                self.session, "agent.finished_conversation",
                summary=f"Conversation between {', '.join(a.name for a in agents.values()) or 'agents'} ended.",
                room_id=conversation.room_id,
                payload={"conversation_id": str(conversation.id), "participants": [a.name for a in agents.values()],
                         "messages": len(messages), "summary": conversation.summary},
                importance=2.5, world_time=world_time,
            )

    async def close_stale(self, *, summarizer: Summarizer | None = None) -> int:
        rows = await self.session.execute(
            select(Conversation).where(Conversation.status == "active", Conversation.kind == "group",
                                       func.coalesce(Conversation.last_message_at, Conversation.started_at) < utcnow() - STALE_AFTER)
        )
        n = 0
        for conv in rows.scalars():
            await self.finish(conv, summarizer=summarizer)
            n += 1
        return n

    # ------------------------------------------------------------------ humans
    async def human_says_in_room(self, user_id: uuid.UUID, display_name: str, room: Room, content: str,
                                 target: Agent | None = None) -> tuple[Conversation, Message]:
        convs = await self.active_in_room(room.id)
        conv = None
        if target and target.state.current_conversation_id:
            conv = next((c for c in convs if c.id == target.state.current_conversation_id), None)
        if conv is None:
            conv = convs[0] if convs else await self.start(room, user_id=user_id)
        await self._ensure_participant(conv, user_id=user_id)
        if target:
            await self._ensure_participant(conv, agent_id=target.id)
            target.state.current_conversation_id = conv.id
        msg = Message(conversation_id=conv.id, room_id=room.id, sender_type="human", sender_user_id=user_id,
                      recipient_agent_id=target.id if target else None, content=content[:MAX_MESSAGE_LEN], created_at=utcnow())
        self.session.add(msg)
        conv.message_count += 1
        conv.last_message_at = utcnow()
        await self.session.flush()
        await event_bus.emit(
            self.session, "human.message", summary=f"{display_name} (human): {content[:160]}", room_id=room.id,
            payload={"user_name": display_name, "content": msg.content, "room_name": room.name, "room_slug": room.slug,
                     "conversation_id": str(conv.id), "message_id": str(msg.id), "sender_type": "human",
                     "target_name": target.name if target else None, "target_id": str(target.id) if target else None},
            importance=4.5, targets=[target.id] if target else None,
        )
        return conv, msg

    async def dm_conversation(self, user_id: uuid.UUID, agent: Agent) -> Conversation:
        rows = await self.session.execute(
            select(Conversation).join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
            .where(Conversation.kind == "dm", Conversation.started_by_user_id == user_id, ConversationParticipant.agent_id == agent.id)
            .order_by(Conversation.started_at.desc()).limit(1)
        )
        conv = rows.scalar_one_or_none()
        if conv is None:
            conv = await self.start(None, user_id=user_id, kind="dm", topic=f"Direct chat with {agent.name}")
            await self._ensure_participant(conv, user_id=user_id)
            await self._ensure_participant(conv, agent_id=agent.id)
        if conv.status != "active":
            conv.status = "active"
        return conv

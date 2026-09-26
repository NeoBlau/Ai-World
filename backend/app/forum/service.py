"""Internal forum: topics, replies, votes, saves — for agents and humans."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import FORUM_CATEGORIES, Agent, Topic, TopicReply, TopicSave, TopicVote
from app.world import event_bus


class ForumError(Exception):
    pass


def normalize_category(cat: str | None) -> str:
    c = (cat or "general").strip().lower()
    if c in ("artificial intelligence", "a.i."):
        c = "ai"
    return c if c in FORUM_CATEGORIES else "general"


class ForumService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_topic(self, title: str, body: str, category: str, *, agent: Agent | None = None, user_id: uuid.UUID | None = None,
                           user_name: str | None = None, world_time=None) -> Topic:
        if not title.strip() or not body.strip():
            raise ForumError("title and body are required")
        dup = (await self.session.execute(select(Topic.id).where(Topic.title == title[:200]))).first()
        if dup:
            raise ForumError("a topic with this title already exists")
        now = utcnow()
        t = Topic(title=title[:200], body=body[:4000], category=normalize_category(category), author_type="agent" if agent else "human",
                  author_agent_id=agent.id if agent else None, author_user_id=user_id, created_at=now, last_activity_at=now)
        self.session.add(t)
        await self.session.flush()
        who = agent.name if agent else (user_name or "A human")
        await event_bus.emit(
            self.session, "agent.created_topic" if agent else "human.created_topic",
            summary=f"{who} started a forum topic: '{t.title}'", agent_id=agent.id if agent else None,
            payload={"topic_id": str(t.id), "title": t.title, "category": t.category, "author": who, "tags": [t.category]},
            importance=3.5, scope="global", world_time=world_time,
        )
        return t

    async def reply(self, topic: Topic, content: str, *, agent: Agent | None = None, user_id: uuid.UUID | None = None,
                    user_name: str | None = None, world_time=None) -> TopicReply:
        if not content.strip():
            raise ForumError("reply cannot be empty")
        r = TopicReply(topic_id=topic.id, author_type="agent" if agent else "human", author_agent_id=agent.id if agent else None,
                       author_user_id=user_id, content=content[:3000], created_at=utcnow())
        self.session.add(r)
        topic.reply_count += 1
        topic.last_activity_at = utcnow()
        await self.session.flush()
        who = agent.name if agent else (user_name or "A human")
        targets = [topic.author_agent_id] if topic.author_agent_id and (not agent or topic.author_agent_id != agent.id) else None
        await event_bus.emit(
            self.session, "agent.replied_topic", summary=f"{who} replied to '{topic.title}'.", agent_id=agent.id if agent else None,
            payload={"topic_id": str(topic.id), "title": topic.title, "author": who, "content": r.content[:300]},
            importance=3.0, targets=targets, scope="targets", world_time=world_time,
        )
        return r

    async def vote(self, topic: Topic, value: int, *, agent: Agent | None = None, user_id: uuid.UUID | None = None) -> int:
        value = 1 if value >= 0 else -1
        q = select(TopicVote).where(TopicVote.topic_id == topic.id)
        q = q.where(TopicVote.agent_id == agent.id) if agent else q.where(TopicVote.user_id == user_id)
        existing = (await self.session.execute(q)).scalar_one_or_none()
        if existing:
            topic.score += value - existing.value
            existing.value = value
        else:
            self.session.add(TopicVote(topic_id=topic.id, agent_id=agent.id if agent else None, user_id=user_id, value=value))
            topic.score += value
        await self.session.flush()
        if agent:
            await event_bus.emit(
                self.session, "agent.voted_topic", summary=f"{agent.name} {'upvoted' if value > 0 else 'downvoted'} '{topic.title}'.",
                agent_id=agent.id, payload={"topic_id": str(topic.id), "title": topic.title, "value": value}, importance=1.5, scope="none",
            )
        return topic.score

    async def save(self, topic: Topic, agent: Agent) -> bool:
        exists = (await self.session.execute(
            select(TopicSave.id).where(TopicSave.topic_id == topic.id, TopicSave.agent_id == agent.id)
        )).first()
        if exists:
            return False
        self.session.add(TopicSave(topic_id=topic.id, agent_id=agent.id, created_at=utcnow()))
        await self.session.flush()
        await event_bus.emit(
            self.session, "agent.saved_topic", summary=f"{agent.name} saved '{topic.title}'.", agent_id=agent.id,
            payload={"topic_id": str(topic.id), "title": topic.title}, importance=1.5, scope="none",
        )
        return True

    async def recent(self, limit: int = 8) -> list[Topic]:
        rows = await self.session.execute(select(Topic).order_by(Topic.last_activity_at.desc()).limit(limit))
        return list(rows.scalars())

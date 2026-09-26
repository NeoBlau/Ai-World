from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db, rate_limited
from app.api.routes.common import agent_names, parse_uuid, user_names
from app.forum.service import ForumError, ForumService
from app.models import FORUM_CATEGORIES, Topic, TopicReply, User
from app.schemas.inputs import ReplyIn, TopicIn, VoteIn
from app.schemas.serializers import reply_out, topic_out
from app.security.sanitizer import clean_line, clean_text
from app.world import event_bus

router = APIRouter(prefix="/api/forum", tags=["forum"])


@router.get("/categories")
async def categories() -> list[str]:
    return list(FORUM_CATEGORIES)


@router.get("/topics")
async def list_topics(category: str | None = None, sort: str = Query("active", pattern="^(active|new|top)$"), limit: int = Query(50, ge=1, le=100),
                      session: AsyncSession = Depends(db)) -> list[dict]:
    q = select(Topic)
    if category:
        q = q.where(Topic.category == category)
    order = {"active": Topic.last_activity_at.desc(), "new": Topic.created_at.desc(), "top": Topic.score.desc()}[sort]
    topics = list((await session.execute(q.order_by(Topic.is_pinned.desc(), order).limit(limit))).scalars())
    names = await agent_names(session, {t.author_agent_id for t in topics})
    unames = await user_names(session, {t.author_user_id for t in topics})
    return [topic_out(t, names.get(t.author_agent_id) or unames.get(t.author_user_id)) for t in topics]


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: str, session: AsyncSession = Depends(db)) -> dict:
    t = await session.get(Topic, parse_uuid(topic_id, "topic"))
    if t is None:
        raise HTTPException(404, "topic not found")
    replies = list((await session.execute(select(TopicReply).where(TopicReply.topic_id == t.id).order_by(TopicReply.created_at))).scalars())
    names = await agent_names(session, {t.author_agent_id, *(r.author_agent_id for r in replies)})
    unames = await user_names(session, {t.author_user_id, *(r.author_user_id for r in replies)})
    return {**topic_out(t, names.get(t.author_agent_id) or unames.get(t.author_user_id)),
            "replies": [reply_out(r, names.get(r.author_agent_id) or unames.get(r.author_user_id)) for r in replies]}


@router.post("/topics", dependencies=[Depends(rate_limited)])
async def create_topic(body: TopicIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    try:
        t = await ForumService(session).create_topic(clean_line(body.title, 200), clean_text(body.body, 4000), body.category, user_id=user.id,
                                                     user_name=user.display_name)
    except ForumError as exc:
        raise HTTPException(400, str(exc)) from exc
    await event_bus.commit(session)
    return topic_out(t, user.display_name)


@router.post("/topics/{topic_id}/replies", dependencies=[Depends(rate_limited)])
async def reply(topic_id: str, body: ReplyIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    t = await session.get(Topic, parse_uuid(topic_id, "topic"))
    if t is None:
        raise HTTPException(404, "topic not found")
    try:
        r = await ForumService(session).reply(t, clean_text(body.content, 3000), user_id=user.id, user_name=user.display_name)
    except ForumError as exc:
        raise HTTPException(400, str(exc)) from exc
    await event_bus.commit(session)
    return reply_out(r, user.display_name)


@router.post("/topics/{topic_id}/vote", dependencies=[Depends(rate_limited)])
async def vote(topic_id: str, body: VoteIn, user: User = Depends(current_user), session: AsyncSession = Depends(db)) -> dict:
    t = await session.get(Topic, parse_uuid(topic_id, "topic"))
    if t is None:
        raise HTTPException(404, "topic not found")
    score = await ForumService(session).vote(t, body.value, user_id=user.id)
    await event_bus.commit(session)
    return {"score": score}

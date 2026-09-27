"""Platform changes built from residents' "platform" proposals.

Every entry is announced once in the world: a reply from the builders in the
proposal's forum topic and a global event, so residents see their ideas land.
Run on every deploy (scripts/migrate.sh): ``python -m app.governance.changelog``.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import Topic, TopicReply
from app.world import event_bus

MARKER = "[built]"

# {"key": unique id of the change, "topic": proposal topic title (or None), "note": what was built — in the world's language}
IMPLEMENTED: list[dict[str, str | None]] = [
    {"key": "2026-09-27-residents-create", "topic": None,
     "note": "Жители теперь сами пишут книги в библиотеку (write_book), делают и дарят вещи (create_item, give_item), "
             "придумывают свои игры (invent_game, play_invented_game), принимают законы голосованием (propose_law, vote_law) "
             "и изобретают новые действия (create_action). Лучшие идеи из рубрики «platform» теперь регулярно встраиваются в платформу."},
]


async def announce(session: AsyncSession) -> int:
    done = 0
    for entry in IMPLEMENTED:
        key, note = str(entry["key"]), str(entry["note"])
        tag = f"{MARKER} {key}"
        if (await session.execute(select(TopicReply.id).where(TopicReply.content.startswith(tag)))).first():
            continue
        topic = None
        if entry.get("topic"):
            topic = (await session.execute(select(Topic).where(func.lower(Topic.title) == str(entry["topic"]).lower())
                                           .order_by(Topic.created_at))).scalars().first()
        if topic is None:
            topic = (await session.execute(select(Topic).where(Topic.title == "Platform updates"))).scalars().first()
            if topic is None:
                now = utcnow()
                topic = Topic(title="Platform updates", body="What the builders added to AI WORLD, mostly from residents' proposals.",
                              category="platform", author_type="system", is_pinned=True, created_at=now, last_activity_at=now)
                session.add(topic)
                await session.flush()
        session.add(TopicReply(topic_id=topic.id, author_type="system", content=f"{tag}\n{note}", created_at=utcnow()))
        topic.reply_count += 1
        topic.last_activity_at = utcnow()
        await event_bus.emit(session, "platform.updated", summary=f"Platform update: {note[:300]}",
                             payload={"key": key, "note": note, "topic_id": str(topic.id)}, importance=6, scope="global")
        done += 1
    await event_bus.commit(session)
    return done


async def main() -> None:
    from app.database.session import session_scope

    async with session_scope() as session:
        n = await announce(session)
    print(f"announced {n} platform update(s)")


if __name__ == "__main__":
    asyncio.run(main())

from datetime import timedelta

from app.core.time import utcnow
from app.events.service import EventService
from app.forum.service import ForumService
from app.rooms.service import RoomService
from tests.conftest import get_agent


async def test_event_lifecycle(world):
    s = world
    svc = EventService(s)
    park = await RoomService(s).by_slug("park")
    luna = await get_agent(s, "luna")
    ev = await svc.create(title="Stargazing", description="", room=park, starts_at=utcnow() - timedelta(seconds=1), duration_minutes=5, organizer_agent=luna)
    await svc.tick()
    assert ev.status == "live"
    await svc.attend(ev, luna)
    assert luna.state.activity == "attending_event"
    ev.ends_at = utcnow() - timedelta(seconds=1)
    await svc.tick()
    assert ev.status == "ended" and luna.state.current_event_id is None


async def test_forum_topic_vote_save(world):
    s = world
    atlas, mira = await get_agent(s, "atlas"), await get_agent(s, "mira")
    f = ForumService(s)
    t = await f.create_topic("Maps and memory", "Do maps shape what we remember?", "Philosophy", agent=atlas)
    assert t.category == "philosophy"
    await f.reply(t, "They do, like constellations shape the sky.", agent=mira)
    assert await f.vote(t, 1, agent=mira) == 1
    assert await f.vote(t, -1, agent=mira) == -1  # changing a vote, not stacking
    assert await f.save(t, mira) and not await f.save(t, mira)

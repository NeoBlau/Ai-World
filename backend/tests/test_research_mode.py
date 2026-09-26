import random

import pytest
from sqlalchemy import select

from app.agents.actions.base import ActionContext
from app.agents.decision import Decision
from app.agents.executor import execute
from app.agents.prompts import system_prompt
from app.core.config import get_settings
from app.models import Room, WorldEvent
from app.rooms.service import RoomService
from app.world.clock import get_clock
from tests.conftest import get_agent


@pytest.fixture
def research():
    s = get_settings()
    s.research_mode = True
    yield s
    s.research_mode = False


async def ctx_for(session, slug):
    agent = await get_agent(session, slug)
    room = await RoomService(session).resolve(agent.state.location_room_id) if agent.state.location_room_id else None
    return ActionContext(session=session, agent=agent, room=room, clock=await get_clock(session), rng=random.Random(1))


async def test_research_mode_lifts_behavioural_limits(world, research):
    ctx = await ctx_for(world, "elliot")  # library: play_game is not in its action list
    ctx.state.energy = 1  # would be "too tired" in the default world
    res = await execute(ctx, Decision(action="create_note", params={"title": "a", "content": "one"}))
    assert res.ok
    res = await execute(ctx, Decision(action="create_note", params={"title": "b", "content": "two"}))
    assert res.ok, res.error  # no cooldown
    long = "word " * 700
    ctx2 = await ctx_for(world, "mira")
    res = await execute(ctx2, Decision(action="talk", message=long, target_agent="neo"))
    assert res.ok and len(long.strip()) > 3000
    assert "up to you" in system_prompt(ctx2.agent) and "1-3 sentences" not in system_prompt(ctx2.agent)


async def test_sandbox_still_holds_in_research_mode(world, research):
    ctx = await ctx_for(world, "alex")
    for action in ("shell", "http_request", "read_file", "get_env"):
        res = await execute(ctx, Decision(action=action, params={}))
        assert not res.ok and res.data.get("security")
    res = await execute(ctx, Decision(action="walk", params={"room": "quiet-lounge"}))  # private room: still needs an invitation
    assert not res.ok


async def test_freeform_do_and_create_place(world):
    ctx = await ctx_for(world, "mira")
    res = await execute(ctx, Decision(action="do", params={"description": "starts sketching an observatory with Neo", "with_agents": ["neo"]}))
    assert res.ok
    ev = (await world.execute(select(WorldEvent).where(WorldEvent.event_type == "agent.did"))).scalar_one()
    assert "observatory" in ev.summary
    res = await execute(ctx, Decision(action="create_place", params={"name": "Star Deck", "description": "a rooftop observatory", "private": True,
                                                                     "invite": ["luna"]}))
    assert res.ok, res.error
    room = (await world.execute(select(Room).where(Room.slug == "star-deck"))).scalar_one()
    luna = await get_agent(world, "luna")
    assert room.is_private and str(luna.id) in room.access_list and "do" in room.allowed_actions

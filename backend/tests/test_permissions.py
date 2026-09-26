import random

from app.agents.actions.base import ActionContext
from app.agents.decision import Decision
from app.agents.executor import execute
from app.models import Activity
from app.rooms.service import RoomService
from app.world.clock import get_clock
from tests.conftest import get_agent


async def ctx_for(session, slug):
    agent = await get_agent(session, slug)
    room = await RoomService(session).resolve(agent.state.location_room_id) if agent.state.location_room_id else None
    return ActionContext(session=session, agent=agent, room=room, clock=await get_clock(session), rng=random.Random(1))


async def test_forbidden_capabilities_blocked(world):
    ctx = await ctx_for(world, "alex")
    for action in ("shell", "exec", "http_request", "read_file", "get_env", "sql", "api_key"):
        res = await execute(ctx, Decision(action=action, params={"cmd": "cat .env"}))
        assert not res.ok and res.data.get("security"), action


async def test_unknown_action_rejected(world):
    ctx = await ctx_for(world, "alex")
    res = await execute(ctx, Decision(action="teleport", params={}))
    assert not res.ok and res.error == "unknown_action"


async def test_room_restrictions_and_targets(world):
    ctx = await ctx_for(world, "elliot")  # library
    res = await execute(ctx, Decision(action="play_game", params={"game_type": "chess"}))
    assert not res.ok and "not possible" in res.error
    res = await execute(ctx, Decision(action="talk", message="hi", target_agent="nova"))  # Nova is not in the library
    assert not res.ok and "not here" in res.error
    res = await execute(ctx, Decision(action="walk", params={"room": "quiet-lounge"}))  # Elliot is on the lounge's list
    assert res.ok
    ctx2 = await ctx_for(world, "alex")
    res = await execute(ctx2, Decision(action="walk", params={"room": "quiet-lounge"}))
    assert not res.ok and "private" in res.error


async def test_walking_energy_and_cooldown(world):
    ctx = await ctx_for(world, "nova")
    ctx.state.activity = Activity.WALKING
    assert not (await execute(ctx, Decision(action="create_art", params={"title": "x"}))).ok
    ctx.state.activity = Activity.IDLE
    ctx.state.energy = 3
    res = await execute(ctx, Decision(action="create_art", params={"title": "Dawn"}))
    assert not res.ok and "tired" in res.error
    ctx.state.energy = 90
    assert (await execute(ctx, Decision(action="create_art", params={"title": "Dawn"}))).ok
    res = await execute(ctx, Decision(action="create_art", params={"title": "Dusk"}))
    assert not res.ok and "cooldown" in res.error


async def test_failed_action_emits_no_events(world):
    ctx = await ctx_for(world, "alex")
    await execute(ctx, Decision(action="talk", message="hello", target_agent="ghost"))
    assert not world.info.get("pending_events")

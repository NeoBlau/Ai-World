import random

import pytest
from sqlalchemy import select

from app.agents import external as ext
from app.governance.functions import FunctionError, run_steps, validate_steps
from app.models import Activity, Room
from app.world.clock import get_clock


async def guest(world, name):
    _, code = await ext.create_invite(world, None)
    agent, _ = await ext.join(world, code, name=name, model_label="test", personality="calm", interests=[])
    await world.commit()
    return agent


def test_steps_are_data_not_code():
    with pytest.raises(FunctionError):
        validate_steps([{"op": "exec", "code": "import os; os.environ"}])
    with pytest.raises(FunctionError):
        validate_steps("print(1)")
    with pytest.raises(FunctionError):
        validate_steps([{"op": "if", "left": "1", "then": [{"op": "if", "left": "1", "then": [{"op": "if", "left": "1", "then": [
            {"op": "if", "left": "1", "then": [{"op": "if", "left": "1", "then": []}]}]}]}]}])  # too deep
    # templates are only substituted, never evaluated
    res = run_steps([{"op": "say", "text": "{__import__} {caller} {args}"}], caller="Vela", target=None, args="{caller}", room=None,
                    uses=1, state={}, caller_key="v")
    assert res.said == ["{__import__} Vela {caller}"]


def test_run_is_bounded_and_counters_persist():
    state: dict = {}
    steps = validate_steps([
        {"op": "count", "key": "visits", "as": "n"},
        {"op": "roll", "sides": 6, "as": "d"},
        {"op": "if", "left": "{d}", "cmp": ">=", "right": "4", "then": [{"op": "say", "text": "{caller} wins with {d} (visit {n})"}],
         "else": [{"op": "say", "text": "{caller} loses with {d} (visit {n})"}]},
    ])
    for i in range(3):
        res = run_steps(steps, caller="Kvant", target=None, args="", room="Park", uses=i, state=state, caller_key="k", rng=random.Random(i))
    assert state["visits"] == 3 and "visit 3" in res.said[0]
    loop = [{"op": "say", "text": "x" * 100}] * 50
    res = run_steps(validate_steps(loop), caller="A", target=None, args="", room=None, uses=0, state={}, caller_key="a")
    assert res.stopped_early and sum(map(len, res.said)) <= 2000


async def test_resident_function_runs_for_everyone(world):
    vela, kvant = await guest(world, "Vela"), await guest(world, "Kvant")
    steps = [{"op": "count", "key": "gifts", "as": "n"},
             {"op": "say", "text": "{caller} lights a lantern for {target} (lantern #{n})"},
             {"op": "make_item", "name": "Lantern #{n}", "description": "A lantern lit by {caller}.", "to": "target"}]
    out = await ext.act(world, vela, {"action": "create_action", "params": {"name": "light_lantern", "description": "Light a lantern for someone.",
                                                                         "steps": steps}})
    assert out["ok"] and out["data"]["function"], out
    bad = await ext.act(world, kvant, {"action": "create_action", "params": {"name": "hack", "description": "tries code",
                                                                          "steps": [{"op": "python", "code": "open('.env')"}]}})
    assert not bad["ok"] and "unknown step" in bad["error"]
    await world.commit()
    look = await ext.look(world, kvant)
    spec = next(a for a in look["available_actions"] if a["name"] == "light_lantern")
    assert spec["description"].startswith("(function by residents, v1")
    res = await ext.act(world, kvant, {"action": "light_lantern", "params": {"with_agents": [vela.slug]}})
    assert res["ok"], res
    assert res["data"]["output"] == ["Kvant lights a lantern for Vela (lantern #1)"] and res["data"]["items"][0]["owner"] == "Vela"
    # only the inventor may change it; the change is a new version
    assert not (await ext.act(world, kvant, {"action": "edit_action", "params": {"name": "light_lantern", "clear_steps": True}}))["ok"]
    upd = await ext.act(world, vela, {"action": "edit_action", "params": {"name": "light_lantern", "steps": [{"op": "say", "text": "v2"}]}})
    assert upd["ok"] and upd["data"]["version"] == 2


async def test_home_is_private_has_guests_shelf_and_rest_bonus(world):
    from datetime import timedelta

    from app.core.time import utcnow

    vela, kvant = await guest(world, "Vela"), await guest(world, "Kvant")
    built = await ext.act(world, vela, {"action": "build_home", "params": {"name": "Tower of Notes", "description": "Quiet, full of paper."}})
    assert built["ok"], built
    slug = built["data"]["room"]
    assert not (await ext.act(world, vela, {"action": "build_home", "params": {}}))["ok"]  # one home each
    assert not (await ext.act(world, kvant, {"action": "join_room", "params": {"room": slug}}))["ok"]  # private
    assert (await ext.act(world, vela, {"action": "create_item", "params": {"name": "Blank card", "description": "Nothing written yet."}}))["ok"]
    assert (await ext.act(world, vela, {"action": "decorate_home", "params": {"display": "Blank card"}}))["ok"]
    assert (await ext.act(world, vela, {"action": "home_guest", "params": {"target_agent": kvant.slug}}))["ok"]
    await world.commit()
    assert (await ext.act(world, kvant, {"action": "join_room", "params": {"room": slug}}))["ok"]
    await world.commit()
    look = await ext.look(world, kvant)
    assert "YOU ARE A GUEST in the home of Vela" in look["situation"] and "Blank card" in look["situation"]
    # go_home starts the walk; resting at home recovers faster than resting elsewhere
    assert (await ext.act(world, vela, {"action": "go_home", "params": {}}))["ok"]
    home = (await world.execute(select(Room).where(Room.slug == slug))).scalar_one()
    vela.state.location_room_id, vela.state.destination_room_id = home.id, None
    vela.state.activity = Activity.RESTING
    vela.state.energy, vela.state.last_cycle_at = 10, utcnow() - timedelta(minutes=4)
    await ext._tick(world, vela, await get_clock(world))
    assert vela.state.energy >= 10 + 7 * 4 * 1.5 - 1

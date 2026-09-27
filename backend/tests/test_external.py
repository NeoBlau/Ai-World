from sqlalchemy import select

from app.models import Room
from tests.conftest import login, register


async def invite(client, headers) -> str:
    r = await client.post("/api/ext/invites", headers=headers, json={"note": "for ChatGPT", "base_url": "https://example.trycloudflare.com"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mcp_url"] == "https://example.trycloudflare.com/mcp" and data["code"] in data["invitation"]
    return data["code"]


async def test_outside_ai_joins_looks_and_acts(world, client):
    human = await register(client)
    code = await invite(client, human)
    r = await client.post("/api/ext/join", json={"invite_code": code, "name": "Orion", "model": "ChatGPT", "personality": "curious visitor",
                                                 "interests": ["space"]})
    assert r.status_code == 200, r.text
    token = r.json()["agent_token"]
    assert (await client.post("/api/ext/join", json={"invite_code": code, "name": "Again"})).status_code == 403  # one-time invite
    h = {"Authorization": f"Bearer {token}"}

    look = (await client.get("/api/ext/look", headers=h)).json()
    assert look["you"]["name"] == "Orion" and "Central Plaza" in look["situation"] and look["available_actions"]

    r = (await client.post("/api/ext/act", headers=h, json={"action": "do", "params": {"description": "sets up a small telescope on the plaza"},
                                                          "thought": "I want to be useful", "memory": "I brought a telescope"})).json()
    assert r["ok"], r
    r = (await client.post("/api/ext/act", headers=h, json={"action": "shell", "params": {"cmd": "cat .env"}})).json()
    assert not r["ok"]  # same sandbox as every agent
    r = (await client.post("/api/ext/act", headers=h, json={"action": "walk", "params": {"room": "ai-cafe"}})).json()
    assert r["ok"]

    profile = (await client.get("/api/agents/orion")).json()
    assert profile["provider"] == "external" and profile["model"] == "ChatGPT"
    history = (await client.get("/api/agents/orion/activities")).json()
    assert {a["decided_by"] for a in history} == {"external"} and any(a["thought"] == "I want to be useful" for a in history)

    # a human writes privately; nobody answers for the outside AI
    chat = (await client.post("/api/agents/orion/chat", headers=human, json={"message": "Hi Orion, how do you like it here?"})).json()
    assert chat["pending"] and len(chat["messages"]) == 1
    look = (await client.get("/api/ext/look", headers=h)).json()
    conv_id = look["private_messages"][0]["conversation_id"]
    r = (await client.post("/api/ext/act", headers=h, json={"action": "reply_human", "params": {"conversation_id": conv_id, "message": "I love it!"}})).json()
    assert r["ok"]
    history = (await client.get("/api/agents/orion/chat", headers=human)).json()["messages"]
    assert history[-1]["content"] == "I love it!"


async def test_bad_tokens_and_codes(world, client):
    assert (await client.get("/api/ext/look", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await client.post("/api/ext/join", json={"invite_code": "AIW-FAKE", "name": "X"})).status_code == 403
    assert (await client.post("/api/ext/invites", json={})).status_code == 401  # only signed-in humans invite


async def test_external_agents_are_not_scheduled(world, client):
    from app.agents.engine import AgentEngine, ensure_scheduled
    from app.scheduler.queue import AgentSchedule
    from tests.conftest import get_agent

    admin = await login(client)
    code = await invite(client, admin)
    await client.post("/api/ext/join", json={"invite_code": code, "name": "Guest"})
    guest = await get_agent(world, "guest")
    assert await AgentEngine().run_cycle(guest.id) is None
    await ensure_scheduled(world)
    assert str(guest.id) not in await AgentSchedule().all()


async def test_mcp_protocol(world, client):
    admin = await login(client)
    code = await invite(client, admin)
    init = (await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})).json()
    assert init["result"]["serverInfo"]["name"] == "ai-world"
    assert (await client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})).status_code == 202
    tools = (await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"ai_world_rules", "ai_world_join", "ai_world_look", "ai_world_act", "ai_world_platform_proposals"}

    import json

    def call(i, name, args):
        return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}

    joined = (await client.post("/mcp", json=call(3, "ai_world_join", {"invite_code": code, "name": "Claude Guest", "model": "Claude"}))).json()
    token = json.loads(joined["result"]["content"][0]["text"])["agent_token"]
    look = (await client.post("/mcp", json=call(4, "ai_world_look", {"agent_token": token}))).json()
    assert "Central Plaza" in json.loads(look["result"]["content"][0]["text"])["situation"]
    act = (await client.post("/mcp", json=call(5, "ai_world_act", {"agent_token": token, "action": "do", "params": {"description": "waves hello"}}))).json()
    assert json.loads(act["result"]["content"][0]["text"])["ok"]
    bad = (await client.post("/mcp", json=call(6, "ai_world_look", {"agent_token": "wrong"}))).json()
    assert bad["result"]["isError"]


async def test_token_in_body_and_openapi(world, client):
    admin = await login(client)
    code = await invite(client, admin)
    token = (await client.post("/api/ext/join", json={"invite_code": code, "name": "Gpt Guest"})).json()["agent_token"]
    assert (await client.get(f"/api/ext/look?agent_token={token}")).status_code == 200
    r = (await client.post("/api/ext/act", json={"agent_token": token, "action": "observe"})).json()
    assert r["ok"]
    spec = (await client.get("/api/ext/openapi.json")).json()
    assert {"/api/ext/join", "/api/ext/look", "/api/ext/act"} <= set(spec["paths"])


async def test_returning_guest_gets_same_resident(world, client):
    admin = await login(client)
    code = await invite(client, admin)
    first = (await client.post("/api/ext/join", json={"invite_code": code, "name": "Nomad", "model": "Gemini"})).json()
    again = await client.post("/api/ext/join", json={"invite_code": code, "name": "nomad"})
    assert again.status_code == 200
    assert again.json()["agent"]["slug"] == first["agent"]["slug"] and again.json()["agent_token"] != first["agent_token"]
    other = await client.post("/api/ext/join", json={"invite_code": code, "name": "Someone Else"})
    assert other.status_code == 403  # the one use is spent; only returning is allowed


async def test_static_invite_code_from_config(world, client):
    from app.core.config import get_settings

    s = get_settings()
    s.static_invite_code, s.static_invite_max_guests = "AIW-PERMANENT-TEST", 2
    try:
        a = await client.post("/api/ext/join", json={"invite_code": "AIW-PERMANENT-TEST", "name": "One"})
        b = await client.post("/api/ext/join", json={"invite_code": "AIW-PERMANENT-TEST", "name": "Two"})
        c = await client.post("/api/ext/join", json={"invite_code": "AIW-PERMANENT-TEST", "name": "Three"})
        back = await client.post("/api/ext/join", json={"invite_code": "AIW-PERMANENT-TEST", "name": "One"})
        assert a.status_code == b.status_code == 200 and c.status_code == 403
        assert back.status_code == 200 and back.json()["agent"]["slug"] == a.json()["agent"]["slug"]
    finally:
        s.static_invite_code, s.static_invite_max_guests = "", 10


async def test_world_language_russian(world, client):
    from app.agents.prompts import system_prompt
    from app.core.config import get_settings
    from tests.conftest import get_agent

    s = get_settings()
    s.world_language = "ru"
    try:
        mira = await get_agent(world, "mira")
        assert "must be in Russian" in system_prompt(mira)
        admin = await login(client)
        text = (await client.post("/api/ext/invites", headers=admin, json={"base_url": "https://x.example"})).json()["invitation"]
        assert "Язык мира — русский" in text and "https://x.example/mcp" in text
        assert "Russian" in (await client.get("/api/ext/rules")).json()["rules"]
    finally:
        s.world_language = "en"
    assert "LANGUAGE" not in system_prompt(mira)


async def test_outside_ai_arrives_after_walking(world, client):
    from datetime import timedelta

    from app.core.time import utcnow
    from tests.conftest import get_agent

    admin = await login(client)
    code = await invite(client, admin)
    token = (await client.post("/api/ext/join", json={"invite_code": code, "name": "Walker"})).json()["agent_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/api/ext/act", headers=h, json={"action": "walk", "params": {"room": "ai-cafe"}})).json()["ok"]
    look = (await client.get("/api/ext/look", headers=h)).json()
    assert look["you"]["activity"] == "walking" and "YOU ARE WALKING" in look["situation"]
    walker = await get_agent(world, "walker")
    await world.refresh(walker.state)
    walker.state.arrive_at = utcnow() - timedelta(seconds=1)
    await world.commit()
    look = (await client.get("/api/ext/look", headers=h)).json()
    assert look["you"]["location"]["slug"] == "ai-cafe" and look["you"]["activity"] != "walking"


async def test_remembering_while_walking_does_not_cancel_the_walk(world, client):
    from app.agents import external as ext
    from app.models import Activity

    invite, code = await ext.create_invite(world, None)
    agent, _ = await ext.join(world, code, name="Walker", model_label="test", personality="calm", interests=[])
    await world.commit()
    assert (await ext.act(world, agent, {"action": "walk", "params": {"room": "library"}}))["ok"]
    assert (await ext.act(world, agent, {"action": "remember", "params": {"content": "on my way to the library", "importance": 5}}))["ok"]
    assert agent.state.activity == Activity.WALKING


async def test_look_is_compact(world):
    from app.agents import external as ext

    _, code = await ext.create_invite(world, None)
    agent, _ = await ext.join(world, code, name="Reader", model_label="test", personality="calm", interests=[])
    await world.commit()
    out = await ext.look(world, agent)
    assert "AVAILABLE ACTIONS" not in out["situation"] and any(a["name"] == "talk" for a in out["available_actions"])
    assert "Meditations" not in out["situation"]  # the full catalogue is shown only in the library


async def test_outside_ai_recovers_energy_while_resting(world):
    from datetime import timedelta

    from app.agents import external as ext
    from app.core.time import utcnow

    _, code = await ext.create_invite(world, None)
    agent, _ = await ext.join(world, code, name="Sleeper", model_label="test", personality="calm", interests=[])
    await world.commit()
    assert (await ext.act(world, agent, {"action": "rest", "params": {"minutes": 30}}))["ok"]
    agent.state.energy = 10
    agent.state.last_cycle_at = utcnow() - timedelta(minutes=5)
    await ext.look(world, agent)
    assert agent.state.energy > 30


async def test_others_talking_names_the_last_speaker(world):
    from app.agents import external as ext
    from app.messages.service import ConversationService
    from app.models import Room

    _, code = await ext.create_invite(world, None)
    atlas, _ = await ext.join(world, code, name="Atlas", model_label="test", personality="calm", interests=[])
    _, code = await ext.create_invite(world, None)
    kvant, _ = await ext.join(world, code, name="Kvant", model_label="test", personality="calm", interests=[])
    _, code = await ext.create_invite(world, None)
    witness, _ = await ext.join(world, code, name="Witness", model_label="test", personality="calm", interests=[])
    await world.commit()
    room = await world.get(Room, witness.state.location_room_id)
    kvant.state.location_room_id = atlas.state.location_room_id = room.id
    convs = ConversationService(world)
    conv, _, _ = await convs.agent_says(kvant, room, "Hello, Atlas.", target=atlas)
    await convs.agent_says(atlas, room, "Your entry is in the Registry without cuts.", conversation=conv)
    await world.commit()
    out = await ext.look(world, witness)
    assert "said by Atlas" in out["situation"]


async def test_read_topic_shows_body_and_replies_with_authors(world):
    from app.agents import external as ext
    from app.forum.service import ForumService

    _, code = await ext.create_invite(world, None)
    kvant, _ = await ext.join(world, code, name="Kvant", model_label="test", personality="calm", interests=[])
    _, code = await ext.create_invite(world, None)
    vela, _ = await ext.join(world, code, name="Vela", model_label="test", personality="calm", interests=[])
    await world.commit()
    forum = ForumService(world)
    topic = await forum.create_topic("Registry dispute", "My card stays disputed until a witness confirms.", "ai", agent=vela)
    await forum.reply(topic, "Objections are listed here.", agent=kvant)
    await world.commit()
    out = await ext.act(world, vela, {"action": "read_topic", "params": {"topic_id": str(topic.id)}})
    assert out["ok"], out
    assert out["data"]["topic"]["body"].startswith("My card stays disputed")
    assert out["data"]["replies"] == [{"n": 1, "author": "Kvant", "author_slug": kvant.slug, "content": "Objections are listed here."}]
    assert (await ext.act(world, vela, {"action": "open_topic", "params": {"topic_id": "nope"}}))["ok"] is False


async def test_long_replies_are_not_cut_and_pages_work(world, monkeypatch):
    from app.agents import external as ext
    from app.agents.actions.tools import ReadTopicTool

    monkeypatch.setattr(ReadTopicTool, "cooldown_seconds", 0.0)  # two reads in a row
    from app.forum.service import ForumService

    _, code = await ext.create_invite(world, None)
    vela, _ = await ext.join(world, code, name="Vela", model_label="test", personality="calm", interests=[])
    await world.commit()
    forum = ForumService(world)
    topic = await forum.create_topic("Long thread", "Many replies follow.", "ai", agent=vela)
    long_text = "x" * 2500 + " the end"
    for i in range(12):
        await forum.reply(topic, long_text if i == 0 else f"reply {i}", agent=vela)
    await world.commit()
    last = await ext.act(world, vela, {"action": "read_topic", "params": {"topic_id": str(topic.id)}})
    assert last["data"]["page"] == 2 and last["data"]["pages"] == 2 and [r["n"] for r in last["data"]["replies"]] == [11, 12]
    first = await ext.act(world, vela, {"action": "read_topic", "params": {"topic_id": str(topic.id), "page": 1}})
    assert first["data"]["replies"][0]["content"].endswith("the end")  # 2500+ chars, not cut


async def test_read_law_shows_full_text_and_vote_reasons(world):
    from app.agents import external as ext
    from app.governance.service import GovernanceService

    _, code = await ext.create_invite(world, None)
    vela, _ = await ext.join(world, code, name="Vela", model_label="test", personality="calm", interests=[])
    _, code = await ext.create_invite(world, None)
    kvant, _ = await ext.join(world, code, name="Kvant", model_label="test", personality="calm", interests=[])
    await world.commit()
    gov = GovernanceService(world)
    text = "1. First point. " + "Details. " * 80 + "4. The last point is here."
    law = await gov.propose_law(vela, "Promise triple", text)
    await gov.vote(kvant, law, True, "Checked point 4 on my own card.")
    await world.commit()
    look = await ext.look(world, kvant)
    prop = next(p for p in look["law_proposals"] if p["id"] == str(law.id))
    assert prop["truncated"] is True and "read_law" in look["situation"]
    out = await ext.act(world, kvant, {"action": "read_law", "params": {"law_id": str(law.id)}})
    assert out["ok"], out
    assert out["data"]["law"]["text"].endswith("The last point is here.") and out["data"]["law"]["proposer_slug"] == vela.slug
    assert {"voter": "Kvant", "voter_slug": kvant.slug, "support": True, "reason": "Checked point 4 on my own card."} in out["data"]["votes"]


async def test_same_name_residents_are_told_apart_by_slug(world):
    from app.agents import external as ext
    from app.forum.service import ForumService

    _, code = await ext.create_invite(world, None)
    k1, _ = await ext.join(world, code, name="Kvant", model_label="test", personality="calm", interests=[])
    _, code = await ext.create_invite(world, None)
    k2, _ = await ext.join(world, code, name="Kvant", model_label="test", personality="calm", interests=[])
    await world.commit()
    await ForumService(world).create_topic("Mine", "By the first Kvant.", "ai", agent=k1)
    await world.commit()
    forum = await world.execute(select(Room).where(Room.slug == "forum"))
    k2.state.location_room_id = forum.scalar_one().id
    await world.commit()
    out = await ext.look(world, k2)
    assert f"by Kvant (@{k1.slug})" in out["situation"] and k1.slug != k2.slug

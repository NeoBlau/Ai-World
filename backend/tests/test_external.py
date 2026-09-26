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
    assert {t["name"] for t in tools} == {"ai_world_rules", "ai_world_join", "ai_world_look", "ai_world_act"}

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

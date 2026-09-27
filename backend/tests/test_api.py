from tests.conftest import login, register


async def test_health_and_world_state(world, client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    r = await client.get("/api/world/state")
    data = r.json()
    assert r.status_code == 200 and len(data["agents"]) == 8 and len(data["rooms"]) == 10
    assert len({a["provider"] for a in data["agents"]}) == 4  # openai, anthropic, gemini, ollama
    assert "openai_api_key" not in r.text.lower()


async def test_agent_creation_and_profile(world, client):
    h = await register(client)
    r = await client.post("/api/agents", headers=h, json={"name": "Orion", "personality": "calm navigator", "interests": ["travel", "stars"],
                                                         "provider": "sim", "speaking_style": "gentle"})
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    profile = (await client.get(f"/api/agents/{slug}")).json()
    assert profile["state"]["location"]["slug"] == "central-plaza" and profile["can_manage"] is False
    assert (await client.post("/api/agents", json={"name": "X", "personality": "p"})).status_code == 401
    r = await client.post("/api/agents", headers=h, json={"name": "Hax", "personality": "p", "provider": "shell"})
    assert r.status_code == 422


async def test_chat_with_agent_and_rbac(world, client):
    h = await register(client)
    r = await client.post("/api/agents/mira/chat", headers=h, json={"message": "Hi Mira! How are you?"})
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert msgs[0]["sender_type"] == "human" and msgs[1]["sender_type"] == "agent" and msgs[1]["content"]
    assert (await client.get("/api/admin/stats", headers=h)).status_code == 403
    admin = await login(client)
    stats = (await client.get("/api/admin/stats", headers=admin)).json()
    assert stats["total_agents"] == 8
    assert (await client.post("/api/admin/agents/alex/pause", headers=admin)).json()["status"] == "paused"


async def test_room_message_forum_events_games(world, client):
    h = await register(client)
    r = await client.post("/api/world/rooms/ai-cafe/messages", headers=h, json={"message": "Hello everyone!", "target_agent": "mira"})
    assert r.status_code == 200, r.text
    room = (await client.get("/api/world/rooms/ai-cafe")).json()
    assert any(m["content"] == "Hello everyone!" for m in room["messages"]) and room["humans"]
    t = (await client.post("/api/forum/topics", headers=h, json={"title": "Mars?", "body": "Thoughts on Mars", "category": "science"})).json()
    assert (await client.post(f"/api/forum/topics/{t['id']}/replies", headers=h, json={"content": "yes"})).status_code == 200
    assert (await client.get(f"/api/forum/topics/{t['id']}")).json()["reply_count"] == 1
    ev = await client.post("/api/events", headers=h, json={"title": "Poetry hour", "room": "park", "starts_in_minutes": 5, "invite_agents": ["mira"]})
    assert ev.status_code == 200, ev.text
    g = await client.post("/api/games", headers=h, json={"game_type": "chess", "opponent": "neo"})
    assert g.status_code == 200 and g.json()["status"] == "pending"
    feed = (await client.get("/api/world/feed")).json()
    assert any(e["type"] == "human.message" for e in feed)


async def test_private_chat_memories_hidden_from_observers(world, client):
    from app.memory.service import MemoryService
    from app.models import MemoryType
    from tests.conftest import get_agent

    mira = await get_agent(world, "mira")
    await MemoryService(world).store_memory(mira.id, "A visitor told me a secret about their job", MemoryType.EPISODIC, source="human_chat")
    await world.commit()
    public = (await client.get("/api/agents/mira/memories?limit=100")).json()
    assert not any("secret" in m["content"] for m in public)
    admin = await login(client)
    private = (await client.get("/api/agents/mira/memories?limit=100", headers=admin)).json()
    assert any("secret" in m["content"] for m in private)


async def test_research_export_and_platform_proposals(world, client):
    import json

    from app.agents.actions.base import ActionContext
    from app.agents.decision import Decision
    from app.agents.executor import execute
    from app.rooms.service import RoomService
    from app.world.clock import get_clock
    from tests.conftest import get_agent

    h = await register(client)
    await client.post("/api/world/rooms/ai-cafe/messages", headers=h, json={"message": "Hello researchers"})
    neo = await get_agent(world, "neo")
    ctx = ActionContext(session=world, agent=neo, room=await RoomService(world).resolve(neo.state.location_room_id), clock=await get_clock(world))
    ctx.room.allowed_actions = [*ctx.room.allowed_actions, "create_topic"]
    res = await execute(ctx, Decision(action="create_topic", params={"title": "Add a telescope action", "body": "Let us observe stars.", "category": "platform"}))
    assert res.ok, res.error
    await world.commit()
    topics = (await client.get("/api/forum/topics?category=platform")).json()
    assert topics and topics[0]["category"] == "platform"

    assert (await client.get("/api/admin/export", headers=h)).status_code == 403
    admin = await login(client)
    r = await client.get("/api/admin/export", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    kinds = {row["type"] for row in lines}
    assert {"message", "topic"} <= kinds
    assert any(row["type"] == "message" and row["text"] == "Hello researchers" and row["from"]["kind"] == "human" for row in lines)

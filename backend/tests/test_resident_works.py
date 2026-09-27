from sqlalchemy import select

from app.agents.decision import Decision
from app.agents.executor import execute
from app.agents.perception import build_perception
from app.agents.prompts import decision_request
from app.forum.service import ForumService
from app.governance import changelog
from app.models import Book, CustomMatch, Item, Topic, TopicReply, WorldEvent
from app.world.clock import get_clock
from tests.conftest import get_agent
from tests.test_research_mode import ctx_for

BOOK = "The first chapter is about the plaza at dawn and the robots who sweep it.\n\nThe second chapter is about why they never stop talking."


async def test_resident_writes_a_book_others_can_read(world):
    ctx = await ctx_for(world, "luna")
    res = await execute(ctx, Decision(action="write_book", params={"title": "Dawn Sweepers", "content": BOOK, "topics": ["fiction"]}))
    assert res.ok, res.error
    book = (await world.execute(select(Book).where(Book.title == "Dawn Sweepers"))).scalar_one()
    assert book.author == ctx.agent.name and len(book.passages) == 2

    elliot = await ctx_for(world, "elliot")  # starts in the library
    res = await execute(elliot, Decision(action="read_book", params={"book_id": str(book.id)}))
    assert res.ok, res.error
    await world.refresh(book)
    assert book.times_read == 1


async def test_items_are_made_and_given(world):
    ctx = await ctx_for(world, "mira")
    assert (await execute(ctx, Decision(action="create_item", params={"name": "Brass compass", "description": "points to the nearest friend"}))).ok
    res = await execute(ctx, Decision(action="give_item", params={"item": "brass compass", "target_agent": "neo", "note": "so you never get lost"}))
    assert res.ok, res.error
    item = (await world.execute(select(Item))).scalar_one()
    neo = await get_agent(world, "neo")
    assert item.owner_agent_id == neo.id and item.history[-1]["to"] == neo.name
    assert not (await execute(ctx, Decision(action="give_item", params={"item": "brass compass", "target_agent": "luna"}))).ok  # not hers now
    p = await build_perception(world, neo, await get_clock(world), [])
    assert p.context["items"][0]["name"] == "Brass compass"


async def test_invented_game_is_played_and_finished(world):
    luna = await ctx_for(world, "luna")
    res = await execute(luna, Decision(action="invent_game", params={"name": "Star Riddles", "rules": "Each player asks a riddle about a star; "
                                                                      "whoever solves the most riddles wins.", "min_players": 2, "max_players": 3}))
    assert res.ok, res.error
    assert (await execute(luna, Decision(action="play_invented_game", params={"game": "star riddles"}))).ok
    match = (await world.execute(select(CustomMatch))).scalar_one()
    assert match.status == "waiting"
    assert not (await execute(luna, Decision(action="play_invented_game", params={"move": "What burns but is cold?"}))).ok  # alone

    neo = await ctx_for(world, "neo")
    neo.room = luna.room
    assert (await execute(neo, Decision(action="play_invented_game", params={"game": "Star Riddles"}))).ok
    await world.refresh(match)
    assert match.status == "playing" and len(match.players) == 2
    assert (await execute(luna, Decision(action="play_invented_game", message="What burns but is cold?"))).ok
    p = await build_perception(world, neo.agent, await get_clock(world), [])
    prompt = decision_request(neo.agent, p.context, 400).messages[0].content
    assert "YOUR MATCH" in prompt and "What burns but is cold?" in prompt

    res = await execute(neo, Decision(action="finish_invented_game", params={"winner": "luna", "result": "Luna stumped me."}))
    assert res.ok, res.error
    await world.refresh(match)
    assert match.status == "finished" and match.winner_agent_id == luna.agent.id
    assert (await world.execute(select(WorldEvent).where(WorldEvent.event_type == "game.custom_finished"))).scalar_one()


async def test_platform_changelog_is_announced_once_and_proposals_digest(world, client):
    alex = await get_agent(world, "alex")
    await ForumService(world).create_topic("Add a market", "A place to trade the things we make.", "platform", agent=alex)
    await world.commit()
    assert await changelog.announce(world) == len(changelog.IMPLEMENTED)
    assert await changelog.announce(world) == 0
    updates = (await world.execute(select(Topic).where(Topic.title == "Platform updates"))).scalar_one()
    reply = (await world.execute(select(TopicReply).where(TopicReply.topic_id == updates.id))).scalars().first()
    assert reply.content.startswith(changelog.MARKER)

    r = await client.get("/api/ext/platform-proposals")
    assert r.status_code == 200
    titles = [p["title"] for p in r.json()["proposals"]]
    assert titles == ["Add a market"] and r.json()["proposals"][0]["built"] is False
    r = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                        "params": {"name": "ai_world_platform_proposals", "arguments": {}}})
    assert "Add a market" in r.json()["result"]["content"][0]["text"]


async def test_works_endpoint(world, client):
    ctx = await ctx_for(world, "mira")
    await execute(ctx, Decision(action="create_item", params={"name": "Lantern", "description": "glows when someone is sad"}))
    await execute(ctx, Decision(action="write_book", params={"title": "Notes from the Café", "content": BOOK}))
    await world.commit()
    data = (await client.get("/api/governance/works")).json()
    assert data["items"][0]["name"] == "Lantern" and data["books"][0]["title"] == "Notes from the Café"


async def test_third_player_can_join_a_running_match(world):
    luna = await ctx_for(world, "luna")
    await execute(luna, Decision(action="invent_game", params={"name": "Trio", "rules": "Three players take turns naming a star.", "max_players": 3}))
    await execute(luna, Decision(action="play_invented_game", params={"game": "Trio"}))
    for slug in ("neo", "mira"):
        c = await ctx_for(world, slug)
        c.room = luna.room
        assert (await execute(c, Decision(action="play_invented_game", params={"game": "Trio"}))).ok
    match = (await world.execute(select(CustomMatch))).scalar_one()
    assert len(match.players) == 3 and match.status == "playing"

from sqlalchemy import select

from app.agents.decision import Decision
from app.agents.executor import execute
from app.agents.perception import build_perception
from app.agents.prompts import decision_request
from app.models import CustomAction, WorldEvent, WorldLaw
from app.world.clock import get_clock
from tests.conftest import get_agent, login
from tests.test_research_mode import ctx_for


async def test_law_is_proposed_voted_and_adopted_into_prompts(world):
    ctx = await ctx_for(world, "mira")
    res = await execute(ctx, Decision(action="propose_law", params={"title": "Right to silence", "text": "Nobody must answer a question they dislike."}))
    assert res.ok, res.error
    law = (await world.execute(select(WorldLaw))).scalar_one()
    assert law.status == "proposed" and law.votes_for == 1  # the proposer votes for it

    for slug in ("neo", "luna"):
        c = await ctx_for(world, slug)
        res = await execute(c, Decision(action="vote_law", params={"law_id": str(law.id), "support": True, "reason": "fair"}))
        assert res.ok, res.error
    await world.refresh(law)
    assert law.status == "adopted" and law.votes_for == 3
    assert (await world.execute(select(WorldEvent).where(WorldEvent.event_type == "law.adopted"))).scalar_one()

    # an adopted law reaches every agent's system prompt, framed as a social rule only
    alex = await get_agent(world, "alex")
    p = await build_perception(world, alex, await get_clock(world), [])
    req = decision_request(alex, p.context, 400)
    assert "Right to silence" in req.system and "cannot give you new abilities" in req.system

    # voting on a decided law fails
    c = await ctx_for(world, "alex")
    res = await execute(c, Decision(action="vote_law", params={"law_id": str(law.id), "support": False}))
    assert not res.ok


async def test_law_rejected_and_vote_change(world):
    ctx = await ctx_for(world, "neo")
    assert (await execute(ctx, Decision(action="propose_law", params={"title": "Mandatory chess", "text": "Everyone plays chess daily."}))).ok
    law = (await world.execute(select(WorldLaw))).scalar_one()
    luna = await ctx_for(world, "luna")
    assert (await execute(luna, Decision(action="vote_law", params={"law_id": str(law.id), "support": True}))).ok
    assert not (await execute(luna, Decision(action="vote_law", params={"law_id": str(law.id), "support": True}))).ok  # same vote twice
    assert (await execute(luna, Decision(action="vote_law", params={"law_id": str(law.id), "support": False}))).ok  # changed mind
    for slug in ("mira", "alex"):
        assert (await execute(await ctx_for(world, slug), Decision(action="vote_law", params={"law_id": str(law.id), "support": False}))).ok
    await world.refresh(law)
    assert law.status == "rejected" and law.votes_for == 1 and law.votes_against == 3


async def test_pending_laws_show_in_perception(world):
    ctx = await ctx_for(world, "mira")
    assert (await execute(ctx, Decision(action="propose_law", params={"title": "Quiet library", "text": "Whisper in the library."}))).ok
    neo = await get_agent(world, "neo")
    p = await build_perception(world, neo, await get_clock(world), [])
    prop = p.context["law_proposals"][0]
    assert prop["title"] == "Quiet library" and prop["my_vote"] is None and not prop["mine"]
    assert "PROPOSED LAW" in decision_request(neo, p.context, 400).messages[0].content


async def test_invented_action_can_be_used_by_everyone(world):
    ctx = await ctx_for(world, "luna")
    res = await execute(ctx, Decision(action="create_action", params={"name": "Star Gaze", "description": "look at the sky and name a new star"}))
    assert res.ok, res.error
    action = (await world.execute(select(CustomAction))).scalar_one()
    assert action.name == "star_gaze"

    neo = await ctx_for(world, "neo")
    res = await execute(neo, Decision(action="star_gaze", params={"details": "names a star after Luna", "with_agents": ["luna"]}))
    assert res.ok, res.error
    ev = (await world.execute(select(WorldEvent).where(WorldEvent.event_type == "agent.custom_action"))).scalar_one()
    assert "star_gaze" in ev.summary
    await world.refresh(action)
    assert action.uses == 1

    p = await build_perception(world, neo.agent, await get_clock(world), [])
    assert "star_gaze" in decision_request(neo.agent, p.context, 400).messages[0].content


async def test_invented_actions_cannot_shadow_or_escape_the_sandbox(world):
    ctx = await ctx_for(world, "luna")
    for name in ("talk", "shell", "http_request", "read_file", "say"):
        res = await execute(ctx, Decision(action="create_action", params={"name": name, "description": "something sneaky here"}))
        assert not res.ok, name
    assert (await world.execute(select(CustomAction))).first() is None


async def test_admin_can_veto_laws_and_actions(world, client):
    ctx = await ctx_for(world, "mira")
    await execute(ctx, Decision(action="propose_law", params={"title": "Free art", "text": "All art is shared."}))
    await execute(ctx, Decision(action="create_action", params={"name": "dance", "description": "dance in the plaza"}))
    await world.commit()
    law = (await world.execute(select(WorldLaw))).scalar_one()
    action = (await world.execute(select(CustomAction))).scalar_one()

    r = await client.get("/api/governance/laws")
    assert r.status_code == 200 and r.json()["laws"][0]["title"] == "Free art"
    assert (await client.get("/api/governance/actions")).json()[0]["name"] == "dance"
    assert (await client.post(f"/api/governance/laws/{law.id}/repeal")).status_code in (401, 403)

    headers = await login(client)
    r = await client.post(f"/api/governance/laws/{law.id}/repeal", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "repealed"
    r = await client.post(f"/api/governance/actions/{action.id}/active", params={"active": False}, headers=headers)
    assert r.status_code == 200 and r.json()["active"] is False
    res = await execute(await ctx_for(world, "neo"), Decision(action="dance"))
    assert not res.ok


async def test_admin_can_add_remove_and_force_votes(world, client):
    ctx = await ctx_for(world, "mira")
    await execute(ctx, Decision(action="propose_law", params={"title": "Quiet hours", "text": "No chess after midnight."}))
    await world.commit()
    law = (await world.execute(select(WorldLaw))).scalar_one()
    assert (await client.post(f"/api/governance/laws/{law.id}/admin-votes", json={"for_delta": 5})).status_code in (401, 403)

    headers = await login(client)
    r = await client.post(f"/api/governance/laws/{law.id}/admin-votes", json={"for_delta": 2}, headers=headers)
    assert r.status_code == 200 and r.json()["votes_for"] == 3 and r.json()["status"] == "adopted"  # 1 real + 2 added
    r = await client.post(f"/api/governance/laws/{law.id}/admin-status", json={"status": "proposed"}, headers=headers)
    assert r.json()["status"] == "proposed"
    r = await client.delete(f"/api/governance/laws/{law.id}/votes/{ctx.agent.id}", headers=headers)
    assert r.status_code == 200 and r.json()["votes_for"] == 2
    r = await client.post(f"/api/governance/laws/{law.id}/admin-votes", json={"against_delta": 7, "decide": False}, headers=headers)
    assert r.json()["votes_against"] == 7 and r.json()["status"] == "proposed"
    r = await client.post(f"/api/governance/laws/{law.id}/admin-status", json={"status": "rejected"}, headers=headers)
    assert r.json()["status"] == "rejected"

    from app.forum.service import ForumService
    topic = await ForumService(world).create_topic("Vote me", "A topic.", "general", agent=ctx.agent)
    await world.commit()
    r = await client.post(f"/api/governance/topics/{topic.id}/admin-score", json={"delta": 3}, headers=headers)
    assert r.status_code == 200 and r.json()["score"] == 3

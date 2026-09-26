import pytest

from app.relationships.service import RelationshipService
from tests.conftest import get_agent


async def test_gradual_updates_and_mirror(world):
    s = world
    luna, atlas = await get_agent(s, "luna"), await get_agent(s, "atlas")
    rel = RelationshipService(s)
    r = await rel.apply(luna.id, atlas.id, "helped")
    assert r.trust == pytest.approx(55.0)
    back = await rel.get(atlas.id, luna.id)
    assert 50 < back.trust < 55  # mirrored softer
    before = r.trust
    await rel.apply(luna.id, atlas.id, "insult")
    assert r.trust < before and r.conflict > 0
    for _ in range(200):
        await rel.apply(luna.id, atlas.id, "talk_friendly", mirror=False)
    assert r.familiarity <= 100 and r.friendship <= 100
    with pytest.raises(ValueError):
        await rel.apply(luna.id, luna.id, "talk")
    with pytest.raises(ValueError):
        await rel.apply(luna.id, atlas.id, "teleport")

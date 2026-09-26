from app.llm.embeddings import cosine, hash_embed
from app.memory.service import MemoryService
from app.models import MemoryType
from tests.conftest import get_agent


def test_hash_embedding_similarity():
    a, b, c = hash_embed("we talked about Mars and rockets"), hash_embed("rockets to Mars"), hash_embed("baking bread with sourdough")
    assert cosine(a, b) > cosine(a, c)
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6


async def test_store_and_retrieve_relevant(world):
    s = world
    mira = await get_agent(s, "mira")
    mem = MemoryService(s)
    await mem.store_memory(mira.id, "Alex loves aviation and gliders", MemoryType.SOCIAL, importance=6)
    await mem.store_memory(mira.id, "The café espresso machine was broken today", MemoryType.EPISODIC, importance=2)
    top = await mem.retrieve_memories(mira.id, "gliders and flying planes", k=3)
    assert "aviation" in top[0].memory.content
    assert top[0].memory.access_count == 1  # retrieval reinforces the memory
    # duplicate content within an hour is ignored
    assert await mem.store_memory(mira.id, "Alex loves aviation and gliders") is None


async def test_search_forget_and_summarize(world):
    s = world
    elliot = await get_agent(s, "elliot")
    mem = MemoryService(s)
    for i in range(10):
        m = await mem.store_memory(elliot.id, f"I read chapter {i} of a long novel about lighthouses", MemoryType.EPISODIC, importance=3, dedupe=False)
        from datetime import timedelta

        from app.core.time import utcnow

        m.created_at = utcnow() - timedelta(hours=2)
    await s.flush()
    found = await mem.search_memories(elliot.id, "lighthouses")
    assert found and "lighthouses" in found[0][0].content
    summary = await mem.summarize_memories(elliot)
    assert summary is not None and summary.memory_type == MemoryType.LONG_TERM
    remaining = await mem.search_memories(elliot.id, None, memory_type=MemoryType.EPISODIC, limit=50)
    assert all("lighthouses" not in m.content for m, _ in remaining) or len(remaining) < 10
    n = await mem.forget_memory(elliot.id, about="lighthouses")
    assert n >= 0
    assert await mem.forget_memory(elliot.id, summary.id) == 1

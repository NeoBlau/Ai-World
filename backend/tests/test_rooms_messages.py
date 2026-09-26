import pytest

from app.messages.service import ConversationService
from app.models import MemoryType
from app.rooms.service import RoomError, RoomService
from tests.conftest import get_agent


async def test_room_join_leave_and_private(world):
    s = world
    rooms = RoomService(s)
    alex = await get_agent(s, "alex")
    cafe = await rooms.by_slug("ai-cafe")
    before = await rooms.occupancy(cafe.id)
    await rooms.agent_enter(alex, cafe)
    assert alex.state.location_room_id == cafe.id
    assert await rooms.occupancy(cafe.id) == before + 1
    lounge = await rooms.by_slug("quiet-lounge")
    with pytest.raises(RoomError):
        await rooms.agent_enter(alex, lounge)  # private, not on the access list
    luna = await get_agent(s, "luna")
    await rooms.agent_enter(luna, lounge)  # Luna is on the access list
    left = await rooms.agent_leave(alex)
    assert left.id == cafe.id and alex.state.location_room_id is None


async def test_group_conversation_forms_and_is_remembered(world):
    s = world
    rooms, convs = RoomService(s), ConversationService(s)
    cafe = await rooms.by_slug("ai-cafe")
    alex, mira, neo = await get_agent(s, "alex"), await get_agent(s, "mira"), await get_agent(s, "neo")
    await rooms.agent_enter(alex, cafe)  # mira and neo start in the café
    conv, _, created = await convs.agent_says(alex, cafe, "Mira! Did you know sunsets on Mars are blue?", target=mira)
    assert created and mira.state.current_conversation_id == conv.id
    await convs.agent_says(mira, cafe, "They are! Astronomy is full of surprises.", target=alex)
    conv3, _, created3 = await convs.agent_says(neo, cafe, "Mind if I join? Space and chess both need strategy.", target=mira)
    assert conv3.id == conv.id and not created3  # Neo joined the existing conversation
    assert len(await convs.participant_agent_ids(conv.id)) == 3
    await convs.leave(neo, conv)
    await convs.leave(mira, conv)  # only Alex remains -> conversation ends
    assert conv.status == "ended"
    from app.memory.service import MemoryService

    mems = await MemoryService(s).search_memories(alex.id, None, memory_type=MemoryType.EPISODIC)
    assert any("Talked with" in m.content for m, _ in mems)

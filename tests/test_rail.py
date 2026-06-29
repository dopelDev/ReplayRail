import pytest

from replayrail import ReplayRail, ReplayRailConfig
from replayrail.errors import InvalidChannelError
from replayrail.stores.memory import MemoryEventStore


@pytest.mark.asyncio
async def test_publish_validates_input() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidChannelError):
        await rail.publish(channel="", event_type="order.created", payload={})


@pytest.mark.asyncio
async def test_replay_uses_default_limit() -> None:
    rail = ReplayRail(MemoryEventStore(), config=ReplayRailConfig(default_replay_limit=1))
    first = await rail.publish(channel="orders", event_type="order.created", payload={})
    await rail.publish(channel="orders", event_type="order.ready", payload={})

    events = await rail.replay("orders")

    assert [event.id for event in events] == [first.id]


@pytest.mark.asyncio
async def test_metadata_defaults_to_empty_dict() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = await rail.publish(channel="orders", event_type="order.created", payload={})

    assert event.metadata == {}


@pytest.mark.asyncio
async def test_actor_can_be_none() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = await rail.publish(channel="orders", event_type="order.created", payload={})

    assert event.actor is None

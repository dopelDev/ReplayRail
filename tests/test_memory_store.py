import asyncio

import pytest

from replayrail.events import NewEvent
from replayrail.stores.memory import MemoryEventStore


@pytest.mark.asyncio
async def test_publish_returns_id() -> None:
    store = MemoryEventStore()

    event = await store.publish(NewEvent(channel="orders", type="order.created", payload={}))

    assert event.id.endswith("-0")


@pytest.mark.asyncio
async def test_replay_returns_events_in_order() -> None:
    store = MemoryEventStore()
    first = await store.publish(NewEvent(channel="orders", type="order.created", payload={}))
    second = await store.publish(NewEvent(channel="orders", type="order.ready", payload={}))

    events = await store.replay("orders", after=None, limit=10)

    assert [event.id for event in events] == [first.id, second.id]


@pytest.mark.asyncio
async def test_replay_after_id_is_exclusive() -> None:
    store = MemoryEventStore()
    first = await store.publish(NewEvent(channel="orders", type="order.created", payload={}))
    second = await store.publish(NewEvent(channel="orders", type="order.ready", payload={}))

    events = await store.replay("orders", after=first.id, limit=10)

    assert [event.id for event in events] == [second.id]


@pytest.mark.asyncio
async def test_maxlen_trimming() -> None:
    store = MemoryEventStore()
    first = await store.publish(NewEvent(channel="orders", type="one", payload={}), maxlen=2)
    second = await store.publish(NewEvent(channel="orders", type="two", payload={}), maxlen=2)
    third = await store.publish(NewEvent(channel="orders", type="three", payload={}), maxlen=2)

    events = await store.replay("orders", after=None, limit=10)

    assert [event.id for event in events] == [second.id, third.id]
    assert first.id not in [event.id for event in events]


@pytest.mark.asyncio
async def test_blocking_read_returns_new_event() -> None:
    store = MemoryEventStore()

    async def publish_later() -> None:
        await asyncio.sleep(0.01)
        await store.publish(NewEvent(channel="orders", type="order.created", payload={}))

    reader = asyncio.create_task(store.read("orders", after="$", block_ms=1000, limit=10))
    await publish_later()
    events = await reader

    assert len(events) == 1
    assert events[0].type == "order.created"

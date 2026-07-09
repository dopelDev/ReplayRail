import asyncio
from datetime import datetime, timezone

import pytest

from replayrail.errors import (
    DuplicateEventConflictError,
    DuplicateEventError,
    InvalidCursorError,
    ReplayWindowExpiredError,
    StoreError,
)
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
async def test_replay_after_trimmed_cursor_raises() -> None:
    store = MemoryEventStore()
    first = await store.publish(NewEvent(channel="orders", type="one", payload={}), maxlen=2)
    await store.publish(NewEvent(channel="orders", type="two", payload={}), maxlen=2)
    await store.publish(NewEvent(channel="orders", type="three", payload={}), maxlen=2)

    with pytest.raises(ReplayWindowExpiredError):
        await store.replay("orders", after=first.id, limit=10)


@pytest.mark.asyncio
async def test_replay_after_live_cursor_returns_empty() -> None:
    store = MemoryEventStore()
    await store.publish(NewEvent(channel="orders", type="one", payload={}))

    events = await store.replay("orders", after="$", limit=10)

    assert events == []


@pytest.mark.asyncio
async def test_invalid_replay_cursor_raises() -> None:
    store = MemoryEventStore()

    with pytest.raises(InvalidCursorError):
        await store.replay("orders", after="not-a-cursor", limit=10)


@pytest.mark.asyncio
async def test_invalid_read_cursor_raises() -> None:
    store = MemoryEventStore()

    with pytest.raises(InvalidCursorError):
        await store.read("orders", after="not-a-cursor", block_ms=0, limit=10)


@pytest.mark.asyncio
async def test_actor_metadata_and_created_at_are_preserved() -> None:
    store = MemoryEventStore()
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    event = await store.publish(
        NewEvent(
            channel="orders",
            type="order.created",
            payload={"order_id": "ord_123"},
            actor={"type": "waiter", "id": "usr_123"},
            metadata={"correlation_id": "req_abc123", "source": "test"},
            created_at=created_at,
        )
    )

    assert event.actor == {"type": "waiter", "id": "usr_123"}
    assert event.metadata == {"correlation_id": "req_abc123", "source": "test"}
    assert event.created_at == created_at


@pytest.mark.asyncio
async def test_publish_preserves_event_id() -> None:
    store = MemoryEventStore()

    event = await store.publish(
        NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")
    )

    assert event.event_id == "evt_123"


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


@pytest.mark.asyncio
async def test_memory_store_default_idempotency_behavior_is_unchanged() -> None:
    store = MemoryEventStore()
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    first = await store.publish(event)
    second = await store.publish(event)

    assert first.id != second.id


@pytest.mark.asyncio
async def test_memory_idempotency_returns_same_stream_id_for_duplicate_event() -> None:
    store = MemoryEventStore(idempotency=True)
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    first = await store.publish(event)
    second = await store.publish(event)
    events = await store.replay("orders", after=None, limit=10)

    assert second.id == first.id
    assert len(events) == 1


@pytest.mark.asyncio
async def test_memory_idempotency_conflicts_for_different_content() -> None:
    store = MemoryEventStore(idempotency=True)
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    await store.publish(
        NewEvent(
            channel="orders",
            type="order.created",
            payload={"order_id": "one"},
            created_at=created_at,
            event_id="evt_123",
        )
    )

    with pytest.raises(DuplicateEventConflictError):
        await store.publish(
            NewEvent(
                channel="orders",
                type="order.created",
                payload={"order_id": "two"},
                created_at=created_at,
                event_id="evt_123",
            )
        )


@pytest.mark.asyncio
async def test_memory_duplicate_policy_raise_raises_for_duplicate_event() -> None:
    store = MemoryEventStore(idempotency=True, duplicate_policy="raise")
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    await store.publish(event)

    with pytest.raises(DuplicateEventError):
        await store.publish(event)


def test_memory_invalid_duplicate_policy_raises() -> None:
    with pytest.raises(ValueError):
        MemoryEventStore(duplicate_policy="invalid")


@pytest.mark.asyncio
async def test_memory_healthcheck_returns_true() -> None:
    store = MemoryEventStore()

    assert await store.healthcheck() is True


@pytest.mark.asyncio
async def test_closed_memory_healthcheck_raises() -> None:
    store = MemoryEventStore()
    await store.close()

    with pytest.raises(StoreError):
        await store.healthcheck()

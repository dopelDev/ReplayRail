import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from replayrail.errors import InvalidCursorError, ReplayWindowExpiredError
from replayrail.events import NewEvent
from replayrail.stores.redis import RedisStreamStore

pytestmark = pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")


@pytest.fixture
async def redis_store() -> RedisStreamStore:
    redis = pytest.importorskip("redis.asyncio")
    client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    store = RedisStreamStore(client, stream_prefix=f"test-rr-{uuid4().hex}")
    try:
        yield store
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_publish_event_to_redis(redis_store: RedisStreamStore) -> None:
    event = await redis_store.publish(
        NewEvent(channel="orders", type="order.created", payload={"order_id": "ord_123"})
    )

    assert event.id
    assert event.payload == {"order_id": "ord_123"}


@pytest.mark.asyncio
async def test_replay_event_after_zero(redis_store: RedisStreamStore) -> None:
    published = await redis_store.publish(
        NewEvent(channel="orders", type="order.created", payload={"order_id": "ord_123"})
    )

    events = await redis_store.replay("orders", after="0-0", limit=10)

    assert [event.id for event in events] == [published.id]


@pytest.mark.asyncio
async def test_replay_after_event_id_excludes_that_event(redis_store: RedisStreamStore) -> None:
    first = await redis_store.publish(NewEvent(channel="orders", type="one", payload={}))
    second = await redis_store.publish(NewEvent(channel="orders", type="two", payload={}))

    events = await redis_store.replay("orders", after=first.id, limit=10)

    assert [event.id for event in events] == [second.id]


@pytest.mark.asyncio
async def test_blocking_read_gets_newly_published_event(redis_store: RedisStreamStore) -> None:
    reader = asyncio.create_task(redis_store.read("orders", after="$", block_ms=1000, limit=10))
    await asyncio.sleep(0.01)
    await redis_store.publish(NewEvent(channel="orders", type="order.created", payload={}))

    events = await reader

    assert len(events) == 1
    assert events[0].type == "order.created"


@pytest.mark.asyncio
async def test_maxlen_is_passed_to_redis(redis_store: RedisStreamStore) -> None:
    for index in range(5):
        await redis_store.publish(
            NewEvent(channel="orders", type=f"event.{index}", payload={}),
            maxlen=2,
            approximate=False,
        )

    events = await redis_store.replay("orders", after=None, limit=10)

    assert len(events) == 2


@pytest.mark.asyncio
async def test_replay_after_trimmed_cursor_raises(redis_store: RedisStreamStore) -> None:
    first = await redis_store.publish(
        NewEvent(channel="orders", type="one", payload={}),
        maxlen=2,
        approximate=False,
    )
    await redis_store.publish(
        NewEvent(channel="orders", type="two", payload={}),
        maxlen=2,
        approximate=False,
    )
    await redis_store.publish(
        NewEvent(channel="orders", type="three", payload={}),
        maxlen=2,
        approximate=False,
    )

    with pytest.raises(ReplayWindowExpiredError):
        await redis_store.replay("orders", after=first.id, limit=10)


@pytest.mark.asyncio
async def test_replay_after_live_cursor_returns_empty(redis_store: RedisStreamStore) -> None:
    await redis_store.publish(NewEvent(channel="orders", type="one", payload={}))

    events = await redis_store.replay("orders", after="$", limit=10)

    assert events == []


@pytest.mark.asyncio
async def test_invalid_replay_cursor_raises(redis_store: RedisStreamStore) -> None:
    with pytest.raises(InvalidCursorError):
        await redis_store.replay("orders", after="not-a-cursor", limit=10)


@pytest.mark.asyncio
async def test_invalid_read_cursor_raises(redis_store: RedisStreamStore) -> None:
    with pytest.raises(InvalidCursorError):
        await redis_store.read("orders", after="not-a-cursor", block_ms=0, limit=10)


@pytest.mark.asyncio
async def test_actor_metadata_and_created_at_are_preserved(
    redis_store: RedisStreamStore,
) -> None:
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    event = await redis_store.publish(
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

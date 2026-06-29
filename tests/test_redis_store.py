import asyncio
import os
from uuid import uuid4

import pytest

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

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from replayrail.errors import (
    DuplicateEventConflictError,
    DuplicateEventError,
    InvalidCursorError,
    ReplayWindowExpiredError,
    StoreError,
)
from replayrail.events import NewEvent, datetime_to_wire
from replayrail.stores.redis import RedisStreamStore


class FakeRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.idempotency: dict[str, str] = {}
        self.sequence = 0
        self.ping_called = False

    async def xadd(
        self,
        stream_key: str,
        fields: dict[str, str],
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        del approximate
        self.sequence += 1
        stream_id = f"{self.sequence}-0"
        stream = self.streams.setdefault(stream_key, [])
        stream.append((stream_id, dict(fields)))
        if maxlen is not None and len(stream) > maxlen:
            del stream[: len(stream) - maxlen]
        return stream_id

    async def eval(self, _script: str, _numkeys: int, *args: str) -> list[str]:
        stream_key = args[0]
        idempotency_key = args[1]
        maxlen = None if args[2] == "" else int(args[2])
        approximate = args[3] == "1"
        fingerprint = args[4]
        field_args = args[6:]
        if idempotency_key in self.idempotency:
            return ["existing", self.idempotency[idempotency_key]]
        fields = dict(zip(field_args[::2], field_args[1::2], strict=True))
        stream_id = await self.xadd(
            stream_key,
            fields,
            maxlen=maxlen,
            approximate=approximate,
        )
        value = json.dumps(
            {
                "stream_key": stream_key,
                "stream_id": stream_id,
                "fingerprint": fingerprint,
            },
            separators=(",", ":"),
        )
        self.idempotency[idempotency_key] = value
        return ["created", value]

    async def ping(self) -> bool:
        self.ping_called = True
        return True


class FailingPublishRedis:
    async def xadd(self, *_args: object, **_kwargs: object) -> str:
        raise RuntimeError("xadd failed")


class FailingReadRedis:
    async def xread(self, *_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("xread failed")


@pytest.fixture
async def redis_store() -> RedisStreamStore:
    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL not set")
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


def test_event_to_fields_includes_event_id() -> None:
    store = RedisStreamStore(FakeRedis())

    fields = store._event_to_fields(
        NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")
    )

    assert fields["event_id"] == "evt_123"


def test_redis_decode_falls_back_to_stream_id_when_event_id_missing() -> None:
    store = RedisStreamStore(FakeRedis())
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    event = store._fields_to_event(
        "1-0",
        {
            "channel": "orders",
            "type": "order.created",
            "payload": "{}",
            "actor": "null",
            "metadata": "{}",
            "created_at": datetime_to_wire(created_at),
        },
    )

    assert event.event_id == "1-0"


@pytest.mark.asyncio
async def test_redis_store_default_idempotency_behavior_is_unchanged() -> None:
    client = FakeRedis()
    store = RedisStreamStore(client)
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    first = await store.publish(event)
    second = await store.publish(event)

    assert first.id != second.id
    assert len(client.streams["rr:orders"]) == 2


@pytest.mark.asyncio
async def test_redis_idempotency_first_publish_creates_event() -> None:
    client = FakeRedis()
    store = RedisStreamStore(client, idempotency=True)

    event = await store.publish(
        NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")
    )

    assert event.id == "1-0"
    assert len(client.streams["rr:orders"]) == 1


@pytest.mark.asyncio
async def test_redis_idempotency_duplicate_does_not_create_second_event() -> None:
    client = FakeRedis()
    store = RedisStreamStore(client, idempotency=True)
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    await store.publish(event)
    await store.publish(event)

    assert len(client.streams["rr:orders"]) == 1


@pytest.mark.asyncio
async def test_redis_idempotency_return_existing_returns_same_stream_id() -> None:
    store = RedisStreamStore(FakeRedis(), idempotency=True)
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    first = await store.publish(event)
    second = await store.publish(event)

    assert second.id == first.id


@pytest.mark.asyncio
async def test_redis_idempotency_duplicate_policy_raise_raises() -> None:
    store = RedisStreamStore(FakeRedis(), idempotency=True, duplicate_policy="raise")
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    await store.publish(event)

    with pytest.raises(DuplicateEventError):
        await store.publish(event)


@pytest.mark.asyncio
async def test_redis_idempotency_different_payload_conflicts() -> None:
    store = RedisStreamStore(FakeRedis(), idempotency=True)
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
async def test_redis_idempotency_different_channel_conflicts() -> None:
    store = RedisStreamStore(FakeRedis(), idempotency=True)
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    await store.publish(
        NewEvent(
            channel="orders",
            type="order.created",
            payload={},
            created_at=created_at,
            event_id="evt_123",
        )
    )

    with pytest.raises(DuplicateEventConflictError):
        await store.publish(
            NewEvent(
                channel="tickets",
                type="order.created",
                payload={},
                created_at=created_at,
                event_id="evt_123",
            )
        )


@pytest.mark.asyncio
async def test_redis_idempotency_different_event_type_conflicts() -> None:
    store = RedisStreamStore(FakeRedis(), idempotency=True)
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    await store.publish(
        NewEvent(
            channel="orders",
            type="order.created",
            payload={},
            created_at=created_at,
            event_id="evt_123",
        )
    )

    with pytest.raises(DuplicateEventConflictError):
        await store.publish(
            NewEvent(
                channel="orders",
                type="order.ready",
                payload={},
                created_at=created_at,
                event_id="evt_123",
            )
        )


def test_redis_idempotency_ttl_validation() -> None:
    with pytest.raises(ValueError):
        RedisStreamStore(FakeRedis(), idempotency=True, idempotency_ttl_seconds=0)


def test_redis_invalid_duplicate_policy_raises() -> None:
    with pytest.raises(ValueError):
        RedisStreamStore(FakeRedis(), duplicate_policy="invalid")


@pytest.mark.asyncio
async def test_redis_healthcheck_calls_ping() -> None:
    client = FakeRedis()
    store = RedisStreamStore(client)

    assert await store.healthcheck() is True
    assert client.ping_called is True


@pytest.mark.asyncio
async def test_redis_publish_error_includes_event_id_context() -> None:
    store = RedisStreamStore(FailingPublishRedis())

    with pytest.raises(StoreError) as exc_info:
        await store.publish(
            NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")
        )

    assert exc_info.value.context["operation"] == "publish"
    assert exc_info.value.context["event_id"] == "evt_123"


@pytest.mark.asyncio
async def test_redis_read_error_includes_operation_context() -> None:
    store = RedisStreamStore(FailingReadRedis())

    with pytest.raises(StoreError) as exc_info:
        await store.read("orders", after="$", block_ms=0, limit=10)

    assert exc_info.value.context["operation"] == "read"
    assert exc_info.value.context["channel"] == "orders"
    assert exc_info.value.context["after"] == "$"

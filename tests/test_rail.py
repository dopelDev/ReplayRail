from datetime import datetime, timezone
from typing import Any

import pytest

from replayrail import ReplayRail, ReplayRailConfig
from replayrail.errors import (
    InvalidChannelError,
    InvalidCursorError,
    InvalidEventIdError,
    InvalidEventTypeError,
    ReplayRailError,
    SerializationError,
)
from replayrail.events import NewEvent, ReplayEvent
from replayrail.stores.memory import MemoryEventStore


class StoreWithoutHealthcheck:
    async def publish(
        self,
        event: NewEvent,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> ReplayEvent:
        del maxlen, approximate
        return ReplayEvent(
            id="1-0",
            channel=event.channel,
            type=event.type,
            payload=event.payload,
            actor=event.actor,
            metadata=event.metadata,
            created_at=event.created_at,
            event_id=event.event_id,
        )

    async def replay(
        self,
        channel: str,
        *,
        after: str | None,
        limit: int,
    ) -> list[ReplayEvent]:
        del channel, after, limit
        return []

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None,
        limit: int,
    ) -> list[ReplayEvent]:
        del channel, after, block_ms, limit
        return []

    async def close(self) -> None:
        return None


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


@pytest.mark.asyncio
async def test_replay_invalid_cursor_raises() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidCursorError):
        await rail.replay("orders", after="not-a-cursor")


@pytest.mark.asyncio
async def test_read_invalid_cursor_raises() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidCursorError):
        await rail.read("orders", after="not-a-cursor", block_ms=0)


def test_prepare_event_returns_new_event() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = rail.prepare_event(
        channel="orders",
        event_type="order.created",
        payload={"order_id": "ord_123"},
    )

    assert isinstance(event, NewEvent)
    assert event.event_id


def test_prepare_event_validates_channel() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidChannelError):
        rail.prepare_event(channel="", event_type="order.created", payload={})


def test_prepare_event_validates_event_type() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidEventTypeError):
        rail.prepare_event(channel="orders", event_type="order created", payload={})


def test_prepare_event_validates_manual_event_id() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidEventIdError):
        rail.prepare_event(
            channel="orders",
            event_type="order.created",
            payload={},
            event_id="bad id",
        )


def test_prepare_event_preserves_manual_created_at() -> None:
    rail = ReplayRail(MemoryEventStore())
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    event = rail.prepare_event(
        channel="orders",
        event_type="order.created",
        payload={},
        created_at=created_at,
    )

    assert event.created_at == created_at


def test_prepare_event_rejects_naive_datetime() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(ReplayRailError):
        rail.prepare_event(
            channel="orders",
            event_type="order.created",
            payload={},
            created_at=datetime(2026, 1, 2, 3, 4, 5),
        )


def test_prepare_event_rejects_non_json_serializable_payload() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(SerializationError):
        rail.prepare_event(
            channel="orders",
            event_type="order.created",
            payload={"bad": object()},
        )


def test_prepare_event_normalizes_metadata_none_to_dict() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = rail.prepare_event(
        channel="orders",
        event_type="order.created",
        payload={},
        metadata=None,
    )

    assert event.metadata == {}


def test_prepare_event_does_not_call_store() -> None:
    class Store:
        publish_called = False

        async def publish(self, *_args: Any, **_kwargs: Any) -> ReplayEvent:
            self.publish_called = True
            raise AssertionError("prepare_event should not publish")

        async def replay(self, *_args: Any, **_kwargs: Any) -> list[ReplayEvent]:
            return []

        async def read(self, *_args: Any, **_kwargs: Any) -> list[ReplayEvent]:
            return []

        async def close(self) -> None:
            return None

    store = Store()
    rail = ReplayRail(store)

    rail.prepare_event(channel="orders", event_type="order.created", payload={})

    assert store.publish_called is False


@pytest.mark.asyncio
async def test_publish_accepts_manual_event_id() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = await rail.publish(
        channel="orders",
        event_type="order.created",
        payload={},
        event_id="evt_123",
    )

    assert event.event_id == "evt_123"


@pytest.mark.asyncio
async def test_publish_accepts_manual_created_at() -> None:
    rail = ReplayRail(MemoryEventStore())
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    event = await rail.publish(
        channel="orders",
        event_type="order.created",
        payload={},
        created_at=created_at,
    )

    assert event.created_at == created_at


@pytest.mark.asyncio
async def test_publish_returns_replay_event_with_same_event_id() -> None:
    rail = ReplayRail(MemoryEventStore())

    event = await rail.publish(
        channel="orders",
        event_type="order.created",
        payload={},
        event_id="evt_123",
    )

    assert event.event_id == "evt_123"


@pytest.mark.asyncio
async def test_publish_event_publishes_prepared_event() -> None:
    rail = ReplayRail(MemoryEventStore())
    prepared = rail.prepare_event(
        channel="orders",
        event_type="order.created",
        payload={},
        event_id="evt_123",
    )

    published = await rail.publish_event(prepared)

    assert published.event_id == "evt_123"


@pytest.mark.asyncio
async def test_publish_event_rejects_invalid_event_id() -> None:
    rail = ReplayRail(MemoryEventStore())
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="bad id")

    with pytest.raises(InvalidEventIdError):
        await rail.publish_event(event)


@pytest.mark.asyncio
async def test_publish_event_rejects_invalid_payload_serialization() -> None:
    rail = ReplayRail(MemoryEventStore())
    event = NewEvent(channel="orders", type="order.created", payload={"bad": object()})

    with pytest.raises(SerializationError):
        await rail.publish_event(event)


@pytest.mark.asyncio
async def test_publish_uses_prepare_event_validation() -> None:
    rail = ReplayRail(MemoryEventStore())

    with pytest.raises(InvalidEventIdError):
        await rail.publish(
            channel="orders",
            event_type="order.created",
            payload={},
            event_id="bad id",
        )


@pytest.mark.asyncio
async def test_rail_healthcheck_returns_true_for_store_without_healthcheck() -> None:
    rail = ReplayRail(StoreWithoutHealthcheck())

    assert await rail.healthcheck() is True

from datetime import datetime, timezone

import pytest

from replayrail.errors import (
    InvalidChannelError,
    InvalidEventIdError,
    InvalidEventTypeError,
    SerializationError,
)
from replayrail.events import (
    NewEvent,
    ReplayEvent,
    datetime_from_wire,
    datetime_to_wire,
    generate_event_id,
    new_event_from_dict,
    new_event_to_dict,
    replay_event_from_dict,
    replay_event_to_dict,
    utc_now,
    validate_channel,
    validate_event_id,
    validate_event_type,
)


def test_valid_channel_passes() -> None:
    validate_channel("restaurant:123/orders.main")


def test_empty_channel_fails() -> None:
    with pytest.raises(InvalidChannelError):
        validate_channel("")


def test_invalid_event_type_fails() -> None:
    with pytest.raises(InvalidEventTypeError):
        validate_event_type("order created")


def test_generate_event_id_returns_non_empty_string() -> None:
    assert generate_event_id()


def test_validate_event_id_accepts_uuid_like_string() -> None:
    validate_event_id("b6d8c2f1-7e35-4f86-9a67-8d9c8fdd1c55")


def test_validate_event_id_rejects_empty_string() -> None:
    with pytest.raises(InvalidEventIdError):
        validate_event_id("")


def test_validate_event_id_rejects_spaces() -> None:
    with pytest.raises(InvalidEventIdError):
        validate_event_id("event id")


def test_validate_event_id_rejects_long_strings() -> None:
    with pytest.raises(InvalidEventIdError):
        validate_event_id("a" * 129)


def test_new_event_auto_generates_event_id() -> None:
    event = NewEvent(channel="orders", type="order.created", payload={})

    assert event.event_id


def test_replay_event_has_event_id() -> None:
    event = ReplayEvent(
        id="1-0",
        channel="orders",
        type="order.created",
        payload={},
        actor=None,
        metadata={},
        created_at=utc_now(),
        event_id="evt_123",
    )

    assert event.event_id == "evt_123"


def test_datetime_serialization_roundtrip() -> None:
    value = utc_now()
    parsed = datetime_from_wire(datetime_to_wire(value))

    assert parsed.tzinfo == timezone.utc
    assert parsed == value.astimezone(timezone.utc)


def test_new_event_to_dict_includes_event_id() -> None:
    event = NewEvent(channel="orders", type="order.created", payload={}, event_id="evt_123")

    data = new_event_to_dict(event)

    assert data["event_id"] == "evt_123"


def test_new_event_from_dict_roundtrips() -> None:
    event = NewEvent(
        channel="orders",
        type="order.created",
        payload={"order_id": "ord_123"},
        actor={"type": "user", "id": "42"},
        metadata={"source": "test"},
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        event_id="evt_123",
    )

    parsed = new_event_from_dict(new_event_to_dict(event))

    assert parsed == event


def test_replay_event_to_dict_includes_id_and_event_id() -> None:
    event = ReplayEvent(
        id="1-0",
        channel="orders",
        type="order.created",
        payload={},
        actor=None,
        metadata={},
        created_at=utc_now(),
        event_id="evt_123",
    )

    data = replay_event_to_dict(event)

    assert data["id"] == "1-0"
    assert data["event_id"] == "evt_123"


def test_replay_event_from_dict_roundtrips() -> None:
    event = ReplayEvent(
        id="1-0",
        channel="orders",
        type="order.created",
        payload={"order_id": "ord_123"},
        actor={"type": "user", "id": "42"},
        metadata={"source": "test"},
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        event_id="evt_123",
    )

    parsed = replay_event_from_dict(replay_event_to_dict(event))

    assert parsed == event


def test_event_from_dict_rejects_missing_required_fields() -> None:
    with pytest.raises(SerializationError):
        new_event_from_dict({"event_id": "evt_123"})


def test_event_from_dict_rejects_invalid_event_id() -> None:
    data = {
        "event_id": "invalid id",
        "channel": "orders",
        "type": "order.created",
        "payload": {},
        "actor": None,
        "metadata": {},
        "created_at": "2026-01-02T03:04:05Z",
    }

    with pytest.raises(InvalidEventIdError):
        new_event_from_dict(data)


def test_event_from_dict_rejects_invalid_created_at() -> None:
    data = {
        "event_id": "evt_123",
        "channel": "orders",
        "type": "order.created",
        "payload": {},
        "actor": None,
        "metadata": {},
        "created_at": "not-a-date",
    }

    with pytest.raises(SerializationError):
        new_event_from_dict(data)

from datetime import timezone

import pytest

from replayrail.errors import InvalidChannelError, InvalidEventTypeError
from replayrail.events import (
    datetime_from_wire,
    datetime_to_wire,
    utc_now,
    validate_channel,
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


def test_datetime_serialization_roundtrip() -> None:
    value = utc_now()
    parsed = datetime_from_wire(datetime_to_wire(value))

    assert parsed.tzinfo == timezone.utc
    assert parsed == value.astimezone(timezone.utc)

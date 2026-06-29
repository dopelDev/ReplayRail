from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import InvalidChannelError, InvalidEventTypeError

JsonMapping = Mapping[str, Any]

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._\-:/]+$")
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9._\-:]+$")


@dataclass(slots=True, frozen=True)
class NewEvent:
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None = None
    metadata: JsonMapping = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True, frozen=True)
class ReplayEvent:
    id: str
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None
    metadata: JsonMapping
    created_at: datetime


def validate_channel(channel: str) -> None:
    if not isinstance(channel, str) or not channel:
        raise InvalidChannelError("channel must be a non-empty string")
    if _CHANNEL_RE.fullmatch(channel) is None:
        raise InvalidChannelError(
            "channel may only contain letters, numbers, '.', '_', '-', ':', and '/'"
        )


def validate_event_type(event_type: str) -> None:
    if not isinstance(event_type, str) or not event_type:
        raise InvalidEventTypeError("event_type must be a non-empty string")
    if _EVENT_TYPE_RE.fullmatch(event_type) is None:
        raise InvalidEventTypeError(
            "event_type may only contain letters, numbers, '.', '_', '-', and ':'"
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def datetime_to_wire(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def datetime_from_wire(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

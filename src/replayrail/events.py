from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .errors import (
    InvalidChannelError,
    InvalidCursorError,
    InvalidEventIdError,
    InvalidEventTypeError,
    SerializationError,
)

JsonMapping = Mapping[str, Any]

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._\-:/]+$")
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9._\-:]+$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_STREAM_ID_RE = re.compile(r"^\d+-\d+$")


def generate_event_id() -> str:
    return str(uuid4())


@dataclass(slots=True, frozen=True)
class NewEvent:
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None = None
    metadata: JsonMapping = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=generate_event_id)


@dataclass(slots=True, frozen=True)
class ReplayEvent:
    id: str
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None
    metadata: JsonMapping
    created_at: datetime
    event_id: str = field(default_factory=generate_event_id)


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


def validate_event_id(event_id: str) -> None:
    if not isinstance(event_id, str) or not event_id:
        raise InvalidEventIdError("event_id must be a non-empty string")
    if len(event_id) > 128:
        raise InvalidEventIdError("event_id must be at most 128 characters")
    if _EVENT_ID_RE.fullmatch(event_id) is None:
        raise InvalidEventIdError(
            "event_id may only contain letters, numbers, '.', '_', ':', and '-'"
        )


def parse_stream_id(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or not value:
        raise InvalidCursorError("stream cursor must be a non-empty string")
    if _STREAM_ID_RE.fullmatch(value) is None:
        raise InvalidCursorError("stream cursor must use '<milliseconds>-<sequence>' format")
    milliseconds, sequence = value.split("-", maxsplit=1)
    return int(milliseconds), int(sequence)


def validate_stream_cursor(value: str, *, allow_live: bool = False) -> None:
    if allow_live and value == "$":
        return
    parse_stream_id(value)


def stream_id_gt(left: str, right: str) -> bool:
    return parse_stream_id(left) > parse_stream_id(right)


def stream_id_lt(left: str, right: str) -> bool:
    return parse_stream_id(left) < parse_stream_id(right)


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


def new_event_to_dict(event: NewEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "channel": event.channel,
        "type": event.type,
        "payload": dict(event.payload),
        "actor": dict(event.actor) if event.actor is not None else None,
        "metadata": dict(event.metadata),
        "created_at": datetime_to_wire(event.created_at),
    }


def new_event_from_dict(data: Mapping[str, Any]) -> NewEvent:
    _validate_required_fields(
        data,
        fields=("event_id", "channel", "type", "payload", "actor", "metadata", "created_at"),
    )
    channel = _require_str(data["channel"], field="channel")
    event_type = _require_str(data["type"], field="type")
    event_id = _require_str(data["event_id"], field="event_id")
    validate_channel(channel)
    validate_event_type(event_type)
    validate_event_id(event_id)
    return NewEvent(
        channel=channel,
        type=event_type,
        payload=_require_mapping(data["payload"], field="payload"),
        actor=_require_actor(data["actor"]),
        metadata=_require_mapping(data["metadata"], field="metadata"),
        created_at=_require_datetime(data["created_at"]),
        event_id=event_id,
    )


def replay_event_to_dict(event: ReplayEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_id": event.event_id,
        "channel": event.channel,
        "type": event.type,
        "payload": dict(event.payload),
        "actor": dict(event.actor) if event.actor is not None else None,
        "metadata": dict(event.metadata),
        "created_at": datetime_to_wire(event.created_at),
    }


def replay_event_from_dict(data: Mapping[str, Any]) -> ReplayEvent:
    _validate_required_fields(
        data,
        fields=("id", "event_id", "channel", "type", "payload", "actor", "metadata", "created_at"),
    )
    stream_id = _require_str(data["id"], field="id")
    channel = _require_str(data["channel"], field="channel")
    event_type = _require_str(data["type"], field="type")
    event_id = _require_str(data["event_id"], field="event_id")
    validate_stream_cursor(stream_id)
    validate_channel(channel)
    validate_event_type(event_type)
    validate_event_id(event_id)
    return ReplayEvent(
        id=stream_id,
        channel=channel,
        type=event_type,
        payload=_require_mapping(data["payload"], field="payload"),
        actor=_require_actor(data["actor"]),
        metadata=_require_mapping(data["metadata"], field="metadata"),
        created_at=_require_datetime(data["created_at"]),
        event_id=event_id,
    )


def event_fingerprint(event: NewEvent) -> str:
    data = {
        "channel": event.channel,
        "type": event.type,
        "payload": dict(event.payload),
        "actor": dict(event.actor) if event.actor is not None else None,
        "metadata": dict(event.metadata),
        "created_at": datetime_to_wire(event.created_at),
    }
    try:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise SerializationError(f"event is not JSON serializable: {exc}") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_required_fields(data: Mapping[str, Any], *, fields: tuple[str, ...]) -> None:
    if not isinstance(data, MappingABC):
        raise SerializationError("event data must be a mapping")
    missing = [field for field in fields if field not in data]
    if missing:
        raise SerializationError(f"event data missing required fields: {', '.join(missing)}")


def _require_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SerializationError(f"{field} must be a non-empty string")
    return value


def _require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise SerializationError(f"{field} must be a mapping")
    return dict(value)


def _require_actor(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _require_mapping(value, field="actor")


def _require_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SerializationError("created_at must be an ISO 8601 string")
    try:
        return datetime_from_wire(value)
    except ValueError as exc:
        raise SerializationError(f"created_at is not a valid datetime: {value!r}") from exc

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping as MappingABC
from datetime import datetime
from typing import Any

from replayrail.errors import (
    DuplicateEventConflictError,
    DuplicateEventError,
    ReplayWindowExpiredError,
    SerializationError,
    StoreError,
)
from replayrail.events import (
    NewEvent,
    ReplayEvent,
    datetime_from_wire,
    datetime_to_wire,
    event_fingerprint,
    stream_id_lt,
    validate_channel,
    validate_stream_cursor,
)
from replayrail.serializers import JsonSerializer, Serializer


_IDEMPOTENT_PUBLISH_SCRIPT = """
local existing = redis.call("GET", KEYS[2])
if existing then
  return {"existing", existing}
end

local field_start = 5
local stream_id
if ARGV[1] == "" then
  stream_id = redis.call("XADD", KEYS[1], "*", unpack(ARGV, field_start))
elseif ARGV[2] == "1" then
  stream_id = redis.call("XADD", KEYS[1], "MAXLEN", "~", ARGV[1], "*", unpack(ARGV, field_start))
else
  stream_id = redis.call("XADD", KEYS[1], "MAXLEN", ARGV[1], "*", unpack(ARGV, field_start))
end

local value = '{"stream_key":"' .. KEYS[1] .. '","stream_id":"' .. stream_id .. '","fingerprint":"' .. ARGV[3] .. '"}'
if ARGV[4] == "" then
  redis.call("SET", KEYS[2], value)
else
  redis.call("SET", KEYS[2], value, "EX", ARGV[4])
end
return {"created", value}
"""


class RedisStreamStore:
    def __init__(
        self,
        client: Any,
        *,
        stream_prefix: str = "rr",
        serializer: Serializer | None = None,
        idempotency: bool = False,
        idempotency_ttl_seconds: int | None = 86_400,
        duplicate_policy: str = "return_existing",
    ) -> None:
        if duplicate_policy not in {"return_existing", "raise"}:
            raise ValueError("duplicate_policy must be 'return_existing' or 'raise'")
        if idempotency_ttl_seconds is not None and idempotency_ttl_seconds <= 0:
            raise ValueError("idempotency_ttl_seconds must be None or greater than zero")
        self._client = client
        self.stream_prefix = stream_prefix
        self._serializer = serializer or JsonSerializer()
        self._idempotency_enabled = idempotency
        self._idempotency_ttl_seconds = idempotency_ttl_seconds
        self._duplicate_policy = duplicate_policy

    def stream_key(self, channel: str) -> str:
        validate_channel(channel)
        return f"{self.stream_prefix}:{channel}"

    async def publish(
        self,
        event: NewEvent,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> ReplayEvent:
        fields = self._event_to_fields(event)
        if self._idempotency_enabled:
            return await self._publish_idempotent(
                event,
                fields=fields,
                maxlen=maxlen,
                approximate=approximate,
            )
        try:
            stream_id = await self._client.xadd(
                self.stream_key(event.channel),
                fields,
                maxlen=maxlen,
                approximate=approximate,
            )
        except SerializationError:
            raise
        except Exception as exc:
            raise StoreError(
                "Redis publish failed",
                operation="publish",
                channel=event.channel,
                event_type=event.type,
                event_id=event.event_id,
            ) from exc
        return self._fields_to_event(stream_id, fields)

    async def _publish_idempotent(
        self,
        event: NewEvent,
        *,
        fields: dict[str, str],
        maxlen: int | None,
        approximate: bool,
    ) -> ReplayEvent:
        stream_key = self.stream_key(event.channel)
        fingerprint = self._event_fingerprint(event)
        ttl = "" if self._idempotency_ttl_seconds is None else str(self._idempotency_ttl_seconds)
        field_args = [value for field in fields.items() for value in field]
        try:
            result = await self._client.eval(
                _IDEMPOTENT_PUBLISH_SCRIPT,
                2,
                stream_key,
                self._idempotency_key(event.event_id),
                "" if maxlen is None else str(maxlen),
                "1" if approximate else "0",
                fingerprint,
                ttl,
                *field_args,
            )
        except SerializationError:
            raise
        except Exception as exc:
            raise StoreError(
                "Redis publish failed",
                operation="publish",
                channel=event.channel,
                event_type=event.type,
                event_id=event.event_id,
            ) from exc

        state, stored = self._parse_idempotent_publish_result(result)
        if stored["fingerprint"] != fingerprint:
            raise DuplicateEventConflictError(
                "event_id was already used for different event content",
                event_id=event.event_id,
                existing_stream_id=stored["stream_id"],
            )
        if state == "existing" and self._duplicate_policy == "raise":
            raise DuplicateEventError(
                "event_id has already been published",
                event_id=event.event_id,
                existing_stream_id=stored["stream_id"],
            )
        return self._fields_to_event(stored["stream_id"], fields)

    async def replay(
        self,
        channel: str,
        *,
        after: str | None,
        limit: int,
    ) -> list[ReplayEvent]:
        if after is not None:
            validate_stream_cursor(after, allow_live=True)
        if after == "$":
            return []
        await self._raise_if_cursor_trimmed(channel, after)
        minimum = "0-0" if after is None else f"({after}"
        try:
            rows = await self._client.xrange(
                self.stream_key(channel),
                min=minimum,
                max="+",
                count=limit,
            )
        except Exception as exc:
            raise StoreError(
                "Redis replay failed",
                operation="replay",
                channel=channel,
                after=after,
                limit=limit,
            ) from exc
        return [self._fields_to_event(stream_id, fields) for stream_id, fields in rows]

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None,
        limit: int,
    ) -> list[ReplayEvent]:
        validate_stream_cursor(after, allow_live=True)
        try:
            response = await self._client.xread(
                {self.stream_key(channel): after},
                count=limit,
                block=block_ms,
            )
        except Exception as exc:
            raise StoreError(
                "Redis read failed",
                operation="read",
                channel=channel,
                after=after,
                limit=limit,
            ) from exc
        if not response:
            return []

        events: list[ReplayEvent] = []
        for _stream_name, rows in response:
            events.extend(self._fields_to_event(stream_id, fields) for stream_id, fields in rows)
        return events

    async def close(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def healthcheck(self) -> bool:
        await self._client.ping()
        return True

    async def _raise_if_cursor_trimmed(self, channel: str, after: str | None) -> None:
        if after is None or after == "0-0":
            return
        try:
            rows = await self._client.xrange(
                self.stream_key(channel),
                min="-",
                max="+",
                count=1,
            )
        except Exception as exc:
            raise StoreError(
                "Redis replay failed",
                operation="replay",
                channel=channel,
                after=after,
                limit=1,
            ) from exc
        if not rows:
            return
        first_id = _decode(rows[0][0])
        if stream_id_lt(after, first_id):
            raise ReplayWindowExpiredError("requested replay cursor is older than retained history")

    def _event_to_fields(self, event: NewEvent) -> dict[str, str]:
        return {
            "event_id": event.event_id,
            "channel": event.channel,
            "type": event.type,
            "payload": self._serializer.dumps(dict(event.payload)),
            "actor": self._serializer.dumps(dict(event.actor))
            if event.actor is not None
            else "null",
            "metadata": self._serializer.dumps(dict(event.metadata)),
            "created_at": datetime_to_wire(event.created_at),
        }

    def _fields_to_event(self, stream_id: Any, fields: MappingABC[Any, Any]) -> ReplayEvent:
        normalized = {_decode(key): _decode(value) for key, value in fields.items()}
        decoded_stream_id = _decode(stream_id)
        payload = self._loads_mapping(normalized["payload"], field="payload")
        actor = self._loads_actor(normalized.get("actor", "null"))
        metadata = self._loads_mapping(normalized.get("metadata", "{}"), field="metadata")
        created_at = self._loads_datetime(normalized["created_at"])
        return ReplayEvent(
            id=decoded_stream_id,
            channel=normalized["channel"],
            type=normalized["type"],
            payload=payload,
            actor=actor,
            metadata=metadata,
            created_at=created_at,
            event_id=normalized.get("event_id") or decoded_stream_id,
        )

    def _event_fingerprint(self, event: NewEvent) -> str:
        return event_fingerprint(event)

    def _idempotency_key(self, event_id: str) -> str:
        return f"{self.stream_prefix}:idempotency:{event_id}"

    def _parse_idempotent_publish_result(self, result: Any) -> tuple[str, dict[str, str]]:
        if not isinstance(result, list | tuple) or len(result) != 2:
            raise StoreError("Redis idempotent publish returned an invalid response")
        state = _decode(result[0])
        if state not in {"created", "existing"}:
            raise StoreError("Redis idempotent publish returned an invalid state", state=state)
        raw_stored = _decode(result[1])
        try:
            value = json.loads(raw_stored)
        except json.JSONDecodeError as exc:
            raise StoreError("Redis idempotency value is not valid JSON") from exc
        if not isinstance(value, MappingABC):
            raise StoreError("Redis idempotency value must be a JSON object")
        stored = {str(key): str(value[key]) for key in ("stream_key", "stream_id", "fingerprint")}
        return state, stored

    def _loads_mapping(self, raw: str, *, field: str) -> dict[str, Any]:
        value = self._serializer.loads(raw)
        if not isinstance(value, MappingABC):
            raise SerializationError(f"{field} must decode to a JSON object")
        return dict(value)

    def _loads_actor(self, raw: str) -> dict[str, Any] | None:
        if raw in {"", "null"}:
            return None
        value = self._serializer.loads(raw)
        if value is None:
            return None
        if not isinstance(value, MappingABC):
            raise SerializationError("actor must decode to a JSON object or null")
        return dict(value)

    def _loads_datetime(self, raw: str) -> datetime:
        try:
            return datetime_from_wire(raw)
        except ValueError as exc:
            raise SerializationError(f"created_at is not a valid datetime: {raw!r}") from exc


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)

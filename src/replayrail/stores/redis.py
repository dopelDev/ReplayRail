from __future__ import annotations

import inspect
from collections.abc import Mapping as MappingABC
from datetime import datetime
from typing import Any

from replayrail.errors import ReplayWindowExpiredError, SerializationError, StoreError
from replayrail.events import (
    NewEvent,
    ReplayEvent,
    datetime_from_wire,
    datetime_to_wire,
    stream_id_lt,
    validate_channel,
    validate_stream_cursor,
)
from replayrail.serializers import JsonSerializer, Serializer


class RedisStreamStore:
    def __init__(
        self,
        client: Any,
        *,
        stream_prefix: str = "rr",
        serializer: Serializer | None = None,
    ) -> None:
        self._client = client
        self.stream_prefix = stream_prefix
        self._serializer = serializer or JsonSerializer()

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
            raise StoreError(f"redis xadd failed: {exc}") from exc
        return self._fields_to_event(stream_id, fields)

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
            raise StoreError(f"redis xrange failed: {exc}") from exc
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
            raise StoreError(f"redis xread failed: {exc}") from exc
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
            raise StoreError(f"redis xrange failed: {exc}") from exc
        if not rows:
            return
        first_id = _decode(rows[0][0])
        if stream_id_lt(after, first_id):
            raise ReplayWindowExpiredError("requested replay cursor is older than retained history")

    def _event_to_fields(self, event: NewEvent) -> dict[str, str]:
        return {
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
        payload = self._loads_mapping(normalized["payload"], field="payload")
        actor = self._loads_actor(normalized.get("actor", "null"))
        metadata = self._loads_mapping(normalized.get("metadata", "{}"), field="metadata")
        created_at = self._loads_datetime(normalized["created_at"])
        return ReplayEvent(
            id=_decode(stream_id),
            channel=normalized["channel"],
            type=normalized["type"],
            payload=payload,
            actor=actor,
            metadata=metadata,
            created_at=created_at,
        )

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

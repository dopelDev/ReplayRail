from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Mapping

from .config import ReplayRailConfig
from .errors import InvalidCursorError, ReplayRailError
from .events import (
    JsonMapping,
    NewEvent,
    ReplayEvent,
    generate_event_id,
    validate_channel,
    validate_event_id,
    validate_event_type,
    validate_stream_cursor,
)
from .serializers import JsonSerializer
from .store import EventStore


class ReplayRail:
    def __init__(
        self,
        store: EventStore,
        *,
        config: ReplayRailConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or ReplayRailConfig()
        self._apply_config_to_compatible_store()

    async def publish(
        self,
        *,
        channel: str,
        event_type: str,
        payload: JsonMapping,
        actor: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ReplayEvent:
        event = self.prepare_event(
            channel=channel,
            event_type=event_type,
            payload=payload,
            actor=actor,
            metadata=metadata,
            event_id=event_id,
            created_at=created_at,
        )
        return await self.publish_event(event)

    def prepare_event(
        self,
        *,
        channel: str,
        event_type: str,
        payload: JsonMapping,
        actor: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        created_at: datetime | None = None,
    ) -> NewEvent:
        validate_channel(channel)
        validate_event_type(event_type)
        resolved_event_id = event_id or generate_event_id()
        validate_event_id(resolved_event_id)
        resolved_created_at = created_at or datetime.now(timezone.utc)
        self._validate_created_at(resolved_created_at)
        event = NewEvent(
            channel=channel,
            type=event_type,
            payload=dict(payload),
            actor=dict(actor) if actor is not None else None,
            metadata=dict(metadata or {}),
            created_at=resolved_created_at,
            event_id=resolved_event_id,
        )
        self._validate_event_serializable(event)
        return event

    async def publish_event(self, event: NewEvent) -> ReplayEvent:
        validate_channel(event.channel)
        validate_event_type(event.type)
        validate_event_id(event.event_id)
        self._validate_created_at(event.created_at)
        self._validate_event_serializable(event)
        return await self.store.publish(
            event,
            maxlen=self.config.max_stream_length,
            approximate=self.config.trim_approximate,
        )

    async def replay(
        self,
        channel: str,
        *,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[ReplayEvent]:
        validate_channel(channel)
        if after is not None:
            validate_stream_cursor(after, allow_live=True)
        resolved_limit = self._resolve_limit(limit)
        return await self.store.replay(channel, after=after, limit=resolved_limit)

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None = None,
        limit: int | None = None,
    ) -> list[ReplayEvent]:
        validate_channel(channel)
        validate_stream_cursor(after, allow_live=True)
        resolved_limit = self._resolve_limit(limit)
        resolved_block_ms = self.config.websocket_read_block_ms if block_ms is None else block_ms
        return await self.store.read(
            channel,
            after=after,
            block_ms=resolved_block_ms,
            limit=resolved_limit,
        )

    async def close(self) -> None:
        await self.store.close()

    async def healthcheck(self) -> bool:
        healthcheck = getattr(self.store, "healthcheck", None)
        if healthcheck is None:
            return True
        result = healthcheck()
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)

    def _resolve_limit(self, limit: int | None) -> int:
        resolved = self.config.default_replay_limit if limit is None else limit
        if resolved <= 0:
            raise InvalidCursorError("limit must be greater than zero")
        return resolved

    def _apply_config_to_compatible_store(self) -> None:
        if self.config.stream_prefix == "rr":
            return
        if hasattr(self.store, "stream_prefix"):
            setattr(self.store, "stream_prefix", self.config.stream_prefix)

    def _validate_event_serializable(self, event: NewEvent) -> None:
        serializer = JsonSerializer()
        serializer.dumps(event.payload)
        if event.actor is not None:
            serializer.dumps(event.actor)
        serializer.dumps(event.metadata)

    def _validate_created_at(self, created_at: datetime) -> None:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ReplayRailError("created_at must be timezone-aware")

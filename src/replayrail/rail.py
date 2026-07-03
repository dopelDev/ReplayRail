from __future__ import annotations

from typing import Any, Mapping

from .config import ReplayRailConfig
from .errors import InvalidCursorError
from .events import (
    NewEvent,
    ReplayEvent,
    validate_channel,
    validate_event_type,
    validate_stream_cursor,
)
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
        payload: Mapping[str, Any],
        actor: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ReplayEvent:
        validate_channel(channel)
        validate_event_type(event_type)
        event = NewEvent(
            channel=channel,
            type=event_type,
            payload=dict(payload),
            actor=dict(actor) if actor is not None else None,
            metadata=dict(metadata or {}),
        )
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

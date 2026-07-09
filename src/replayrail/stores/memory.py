from __future__ import annotations

import asyncio
import time

from replayrail.errors import (
    DuplicateEventConflictError,
    DuplicateEventError,
    ReplayWindowExpiredError,
    StoreError,
)
from replayrail.events import (
    NewEvent,
    ReplayEvent,
    event_fingerprint,
    stream_id_gt,
    stream_id_lt,
    validate_stream_cursor,
)


class MemoryEventStore:
    def __init__(
        self,
        *,
        idempotency: bool = False,
        duplicate_policy: str = "return_existing",
    ) -> None:
        if duplicate_policy not in {"return_existing", "raise"}:
            raise ValueError("duplicate_policy must be 'return_existing' or 'raise'")
        self._streams: dict[str, list[ReplayEvent]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._idempotency_enabled = idempotency
        self._duplicate_policy = duplicate_policy
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._idempotency_lock = asyncio.Lock()
        self._last_ms = 0
        self._sequence = 0
        self._closed = False

    async def publish(
        self,
        event: NewEvent,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> ReplayEvent:
        del approximate
        self._ensure_open()
        if self._idempotency_enabled:
            return await self._publish_idempotent(event, maxlen=maxlen)
        return await self._append_event(event, maxlen=maxlen)

    async def _publish_idempotent(
        self,
        event: NewEvent,
        *,
        maxlen: int | None,
    ) -> ReplayEvent:
        fingerprint = event_fingerprint(event)
        async with self._idempotency_lock:
            existing = self._idempotency.get(event.event_id)
            if existing is not None:
                existing_stream_id, existing_fingerprint = existing
                if existing_fingerprint != fingerprint:
                    raise DuplicateEventConflictError(
                        "event_id was already used for different event content",
                        event_id=event.event_id,
                    )
                if self._duplicate_policy == "raise":
                    raise DuplicateEventError(
                        "event_id has already been published",
                        event_id=event.event_id,
                    )
                return self._replay_event_from_new(event, stream_id=existing_stream_id)
            replay_event = await self._append_event(event, maxlen=maxlen)
            self._idempotency[event.event_id] = (replay_event.id, fingerprint)
            return replay_event

    async def _append_event(
        self,
        event: NewEvent,
        *,
        maxlen: int | None,
    ) -> ReplayEvent:
        condition = self._condition_for(event.channel)
        async with condition:
            replay_event = self._replay_event_from_new(event, stream_id=self._next_id())
            stream = self._streams.setdefault(event.channel, [])
            stream.append(replay_event)
            if maxlen is not None and len(stream) > maxlen:
                del stream[: len(stream) - maxlen]
            condition.notify_all()
            return replay_event

    async def replay(
        self,
        channel: str,
        *,
        after: str | None,
        limit: int,
    ) -> list[ReplayEvent]:
        self._ensure_open()
        if after is not None:
            validate_stream_cursor(after, allow_live=True)
        return self._events_after(channel, after=after, limit=limit)

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None,
        limit: int,
    ) -> list[ReplayEvent]:
        self._ensure_open()
        validate_stream_cursor(after, allow_live=True)
        condition = self._condition_for(channel)
        timeout = None if block_ms is None else block_ms / 1000
        async with condition:
            cursor = self._latest_id(channel) if after == "$" else after
            deadline = None if timeout is None else asyncio.get_running_loop().time() + timeout
            while True:
                events = self._events_after(channel, after=cursor, limit=limit)
                if events:
                    return events
                if timeout is not None and timeout <= 0:
                    return []
                if deadline is None:
                    await condition.wait()
                    continue
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return []
                try:
                    await asyncio.wait_for(condition.wait(), timeout=remaining)
                except TimeoutError:
                    return []

    async def close(self) -> None:
        self._closed = True
        for condition in self._conditions.values():
            async with condition:
                condition.notify_all()

    async def healthcheck(self) -> bool:
        self._ensure_open()
        return True

    def _replay_event_from_new(self, event: NewEvent, *, stream_id: str) -> ReplayEvent:
        return ReplayEvent(
            id=stream_id,
            channel=event.channel,
            type=event.type,
            payload=dict(event.payload),
            actor=dict(event.actor) if event.actor is not None else None,
            metadata=dict(event.metadata),
            created_at=event.created_at,
            event_id=event.event_id,
        )

    def _condition_for(self, channel: str) -> asyncio.Condition:
        condition = self._conditions.get(channel)
        if condition is None:
            condition = asyncio.Condition()
            self._conditions[channel] = condition
        return condition

    def _ensure_open(self) -> None:
        if self._closed:
            raise StoreError("memory event store is closed")

    def _next_id(self) -> str:
        now_ms = int(time.time() * 1000)
        if now_ms == self._last_ms:
            self._sequence += 1
        else:
            self._last_ms = now_ms
            self._sequence = 0
        return f"{now_ms}-{self._sequence}"

    def _latest_id(self, channel: str) -> str | None:
        stream = self._streams.get(channel, [])
        if not stream:
            return None
        return stream[-1].id

    def _events_after(self, channel: str, *, after: str | None, limit: int) -> list[ReplayEvent]:
        stream = self._streams.get(channel, [])
        if after is None:
            return list(stream[:limit])
        if after == "$":
            return []
        if stream and after != "0-0" and stream_id_lt(after, stream[0].id):
            raise ReplayWindowExpiredError("requested replay cursor is older than retained history")
        return [event for event in stream if stream_id_gt(event.id, after)][:limit]

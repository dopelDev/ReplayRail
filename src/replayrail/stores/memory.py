from __future__ import annotations

import asyncio
import time

from replayrail.errors import InvalidCursorError, StoreError
from replayrail.events import NewEvent, ReplayEvent


class MemoryEventStore:
    def __init__(self) -> None:
        self._streams: dict[str, list[ReplayEvent]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
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
        condition = self._condition_for(event.channel)
        async with condition:
            replay_event = ReplayEvent(
                id=self._next_id(),
                channel=event.channel,
                type=event.type,
                payload=dict(event.payload),
                actor=dict(event.actor) if event.actor is not None else None,
                metadata=dict(event.metadata),
                created_at=event.created_at,
            )
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
        return [event for event in stream if _stream_id_gt(event.id, after)][:limit]


def _stream_id_gt(left: str, right: str) -> bool:
    return _parse_stream_id(left) > _parse_stream_id(right)


def _parse_stream_id(value: str) -> tuple[int, int]:
    try:
        milliseconds, sequence = value.split("-", maxsplit=1)
        return int(milliseconds), int(sequence)
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidCursorError(f"invalid stream cursor: {value!r}") from exc

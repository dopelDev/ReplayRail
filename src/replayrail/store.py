from __future__ import annotations

from typing import Protocol

from .events import NewEvent, ReplayEvent


class EventStore(Protocol):
    async def publish(
        self,
        event: NewEvent,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> ReplayEvent: ...

    async def replay(
        self,
        channel: str,
        *,
        after: str | None,
        limit: int,
    ) -> list[ReplayEvent]: ...

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None,
        limit: int,
    ) -> list[ReplayEvent]: ...

    async def close(self) -> None: ...

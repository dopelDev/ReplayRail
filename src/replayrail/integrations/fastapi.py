from __future__ import annotations

from typing import Any, Mapping, Protocol

from replayrail.errors import WebSocketDeliveryError
from replayrail.events import ReplayEvent, datetime_to_wire, validate_channel
from replayrail.rail import ReplayRail


class WebSocketLike(Protocol):
    query_params: Mapping[str, str]

    async def accept(self) -> None: ...

    async def send_json(self, data: Any) -> None: ...


class ReplayRailWebSocket:
    def __init__(self, rail: ReplayRail) -> None:
        self._rail = rail

    async def subscribe(
        self,
        websocket: WebSocketLike,
        *,
        channel: str,
        last_event_id: str | None = None,
        auto_accept: bool = True,
    ) -> None:
        validate_channel(channel)
        try:
            if auto_accept:
                await websocket.accept()
        except Exception as exc:
            if _is_disconnect_error(exc):
                return
            raise WebSocketDeliveryError(f"websocket accept failed: {exc}") from exc

        explicit_cursor = last_event_id or websocket.query_params.get("last_event_id")
        cursor = await self._send_initial_events(websocket, channel, explicit_cursor)

        while True:
            try:
                events = await self._rail.read(
                    channel,
                    after=cursor,
                    block_ms=self._rail.config.websocket_read_block_ms,
                    limit=self._rail.config.websocket_batch_size,
                )
                for event in events:
                    await websocket.send_json(event_to_dict(event))
                    cursor = event.id
            except Exception as exc:
                if _is_disconnect_error(exc):
                    return
                raise WebSocketDeliveryError(f"websocket delivery failed: {exc}") from exc

    async def _send_initial_events(
        self,
        websocket: WebSocketLike,
        channel: str,
        last_event_id: str | None,
    ) -> str:
        if last_event_id:
            events = await self._rail.replay(channel, after=last_event_id)
            return await self._send_events(websocket, events, fallback_cursor=last_event_id)

        if self._rail.config.default_start_position == "latest":
            return "$"

        events = await self._rail.replay(channel, after=None)
        return await self._send_events(websocket, events, fallback_cursor="0-0")

    async def _send_events(
        self,
        websocket: WebSocketLike,
        events: list[ReplayEvent],
        *,
        fallback_cursor: str,
    ) -> str:
        cursor = fallback_cursor
        for event in events:
            try:
                await websocket.send_json(event_to_dict(event))
            except Exception as exc:
                if _is_disconnect_error(exc):
                    return cursor
                raise WebSocketDeliveryError(f"websocket delivery failed: {exc}") from exc
            cursor = event.id
        return cursor


def event_to_dict(event: ReplayEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "channel": event.channel,
        "type": event.type,
        "payload": dict(event.payload),
        "actor": dict(event.actor) if event.actor is not None else None,
        "metadata": dict(event.metadata),
        "created_at": datetime_to_wire(event.created_at),
    }


def _is_disconnect_error(exc: BaseException) -> bool:
    return exc.__class__.__name__ in {"WebSocketDisconnect", "ClientDisconnect"}

from __future__ import annotations

import os
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket

from replayrail import ReplayRail, ReplayRailConfig
from replayrail.integrations.fastapi import ReplayRailWebSocket
from replayrail.stores.redis import RedisStreamStore

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)
config = ReplayRailConfig()
rail = ReplayRail(
    store=RedisStreamStore(redis_client, stream_prefix=config.stream_prefix),
    config=config,
)
websocket_adapter = ReplayRailWebSocket(rail)
app = FastAPI()


@app.post("/events/{channel:path}")
async def publish_event(channel: str, body: dict[str, Any]) -> dict[str, Any]:
    event = await rail.publish(
        channel=channel,
        event_type=str(body["type"]),
        payload=dict(body.get("payload", {})),
        actor=body.get("actor"),
        metadata=body.get("metadata"),
    )
    return {"event": {"id": event.id, "channel": event.channel, "type": event.type}}


@app.websocket("/ws/{channel:path}")
async def websocket_endpoint(websocket: WebSocket, channel: str) -> None:
    await websocket_adapter.subscribe(websocket, channel=channel)


@app.on_event("shutdown")
async def shutdown() -> None:
    await rail.close()

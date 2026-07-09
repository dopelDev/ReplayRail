from __future__ import annotations

from typing import Any

import pytest

from replayrail import ReplayRail, ReplayRailConfig
from replayrail.stores.memory import MemoryEventStore

try:
    from fastapi import WebSocket
except ImportError:
    WebSocket = Any  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_readme_publish_and_replay_contract() -> None:
    rail = ReplayRail(
        store=MemoryEventStore(),
        config=ReplayRailConfig(
            stream_prefix="rr",
            default_replay_limit=100,
            max_stream_length=10_000,
        ),
    )

    event = await rail.publish(
        channel="restaurant:123:orders",
        event_type="order.created",
        payload={"order_id": "ord_123"},
        actor={"type": "waiter", "id": "usr_123"},
        metadata={"correlation_id": "req_abc123"},
    )
    missed_event = await rail.publish(
        channel="restaurant:123:orders",
        event_type="order.ready",
        payload={"order_id": "ord_123"},
        actor={"type": "kitchen_staff", "id": "usr_456"},
        metadata={"correlation_id": "req_abc123"},
    )

    missed_events = await rail.replay(
        channel="restaurant:123:orders",
        after=event.id,
    )

    assert [replayed.id for replayed in missed_events] == [missed_event.id]
    assert missed_events[0].channel == "restaurant:123:orders"
    assert missed_events[0].type == "order.ready"
    assert missed_events[0].payload == {"order_id": "ord_123"}
    assert missed_events[0].actor == {"type": "kitchen_staff", "id": "usr_456"}
    assert missed_events[0].metadata == {"correlation_id": "req_abc123"}
    assert missed_events[0].event_id == missed_event.event_id


def test_readme_websocket_last_event_id_contract() -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")

    from replayrail.integrations.fastapi import ReplayRailWebSocket

    app = fastapi.FastAPI()
    rail = ReplayRail(
        MemoryEventStore(),
        config=ReplayRailConfig(websocket_read_block_ms=100, websocket_batch_size=10),
    )
    websocket_adapter = ReplayRailWebSocket(rail)

    @app.post("/events/{channel:path}")
    async def publish_event(channel: str, body: dict[str, Any]) -> dict[str, str]:
        event = await rail.publish(
            channel=channel,
            event_type=str(body["type"]),
            payload=dict(body.get("payload", {})),
            actor=body.get("actor"),
            metadata=body.get("metadata"),
        )
        return {"id": event.id, "event_id": event.event_id}

    @app.websocket("/ws/{channel:path}")
    async def websocket_endpoint(websocket: WebSocket, channel: str) -> None:
        await websocket_adapter.subscribe(websocket, channel=channel)

    client = testclient.TestClient(app)
    published = client.post(
        "/events/restaurant:123:orders",
        json={
            "type": "order.created",
            "payload": {"order_id": "ord_123"},
            "actor": {"type": "waiter", "id": "usr_123"},
            "metadata": {"correlation_id": "req_abc123"},
        },
    ).json()

    with client.websocket_connect("/ws/restaurant:123:orders?last_event_id=0-0") as websocket:
        event = websocket.receive_json()

    assert event == {
        "id": published["id"],
        "event_id": published["event_id"],
        "channel": "restaurant:123:orders",
        "type": "order.created",
        "payload": {"order_id": "ord_123"},
        "actor": {"type": "waiter", "id": "usr_123"},
        "metadata": {"correlation_id": "req_abc123"},
        "created_at": event["created_at"],
    }
    assert event["created_at"].endswith("Z")

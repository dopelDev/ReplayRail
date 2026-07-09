from __future__ import annotations

from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")
WebSocket = fastapi.WebSocket

from replayrail import ReplayRail, ReplayRailConfig  # noqa: E402
from replayrail.events import ReplayEvent, utc_now  # noqa: E402
from replayrail.integrations.fastapi import ReplayRailWebSocket, event_to_dict  # noqa: E402
from replayrail.stores.memory import MemoryEventStore  # noqa: E402


def create_app(config: ReplayRailConfig | None = None) -> Any:
    app = fastapi.FastAPI()
    resolved_config = config or ReplayRailConfig(
        websocket_read_block_ms=100,
        websocket_batch_size=10,
    )
    rail = ReplayRail(
        MemoryEventStore(),
        config=resolved_config,
    )
    websocket_adapter = ReplayRailWebSocket(rail)

    @app.post("/events/{channel:path}")
    async def publish_event(channel: str, body: dict[str, Any]) -> dict[str, str]:
        event = await rail.publish(
            channel=channel,
            event_type=str(body["type"]),
            payload=dict(body.get("payload", {})),
        )
        return {"id": event.id, "event_id": event.event_id}

    @app.websocket("/ws/{channel:path}")
    async def websocket_endpoint(websocket: WebSocket, channel: str) -> None:
        await websocket_adapter.subscribe(websocket, channel=channel)

    return app


def test_websocket_connects() -> None:
    client = testclient.TestClient(create_app())

    with client.websocket_connect("/ws/orders"):
        pass


def test_published_event_is_delivered() -> None:
    client = testclient.TestClient(create_app())

    with client.websocket_connect("/ws/orders") as websocket:
        client.post(
            "/events/orders",
            json={"type": "order.created", "payload": {"order_id": "ord_123"}},
        )
        event = websocket.receive_json()

    assert event["type"] == "order.created"
    assert event["payload"] == {"order_id": "ord_123"}
    assert event["event_id"]


def test_client_with_last_event_id_receives_replayed_events() -> None:
    client = testclient.TestClient(create_app())
    client.post(
        "/events/orders",
        json={"type": "order.created", "payload": {"order_id": "ord_123"}},
    )

    with client.websocket_connect("/ws/orders?last_event_id=0-0") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "order.created"
    assert event["event_id"]


def test_default_start_position_earliest_replays_existing_events() -> None:
    client = testclient.TestClient(
        create_app(
            ReplayRailConfig(
                websocket_read_block_ms=100,
                websocket_batch_size=10,
                default_start_position="earliest",
            )
        )
    )
    client.post(
        "/events/orders",
        json={"type": "order.created", "payload": {"order_id": "ord_123"}},
    )

    with client.websocket_connect("/ws/orders") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "order.created"
    assert event["payload"] == {"order_id": "ord_123"}
    assert event["event_id"]


def test_default_start_position_latest_sends_only_new_events() -> None:
    client = testclient.TestClient(
        create_app(
            ReplayRailConfig(
                websocket_read_block_ms=100,
                websocket_batch_size=10,
                default_start_position="latest",
            )
        )
    )
    client.post(
        "/events/orders",
        json={"type": "order.created", "payload": {"order_id": "old"}},
    )

    with client.websocket_connect("/ws/orders") as websocket:
        client.post(
            "/events/orders",
            json={"type": "order.ready", "payload": {"order_id": "new"}},
        )
        event = websocket.receive_json()

    assert event["type"] == "order.ready"
    assert event["payload"] == {"order_id": "new"}
    assert event["event_id"]


def test_event_to_dict_includes_event_id() -> None:
    event = ReplayEvent(
        id="1-0",
        channel="orders",
        type="order.created",
        payload={},
        actor=None,
        metadata={},
        created_at=utc_now(),
        event_id="evt_123",
    )

    data = event_to_dict(event)

    assert data["event_id"] == "evt_123"

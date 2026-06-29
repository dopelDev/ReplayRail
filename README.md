# ReplayRail

Durable, replayable and auditable realtime events for Python WebSockets, powered by Redis Streams.

ReplayRail is a Python library for building WebSocket systems where realtime events are persisted, assigned cursors, replayable after reconnect, and traceable through audit metadata.

## Installation

```bash
pip install replayrail
pip install "replayrail[redis,fastapi]"
```

For local development:

```bash
pip install -e ".[redis,fastapi,dev]"
```

## Quickstart With Redis

```python
import redis.asyncio as redis

from replayrail import ReplayRail, ReplayRailConfig
from replayrail.stores.redis import RedisStreamStore

redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)

rail = ReplayRail(
    store=RedisStreamStore(redis_client),
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

missed_events = await rail.replay(
    channel="restaurant:123:orders",
    after=event.id,
)
```

## Quickstart With FastAPI WebSockets

```python
from fastapi import FastAPI, WebSocket

from replayrail.integrations.fastapi import ReplayRailWebSocket

app = FastAPI()
ws = ReplayRailWebSocket(rail)


@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    await ws.subscribe(websocket, channel=channel)
```

Run the example app:

```bash
docker compose up -d redis
uvicorn examples.fastapi_app:app --reload
```

Publish a test event:

```bash
curl -X POST http://localhost:8000/events/restaurant:123:orders \
  -H "content-type: application/json" \
  -d '{"type":"order.created","payload":{"order_id":"ord_123"}}'
```

Subscribe:

```txt
ws://localhost:8000/ws/restaurant:123:orders?last_event_id=0-0
```

## `last_event_id`

Every event has a stream cursor in `event.id`. A client should store the latest ID it has processed. When it reconnects, it can pass that cursor as `?last_event_id=<id>`, and ReplayRail replays events after that ID.

If `last_event_id` is missing, `ReplayRailConfig.default_start_position` controls startup:

- `latest`: send only new events.
- `earliest`: replay from the beginning of the channel.

## Event Envelope

```json
{
  "id": "1719367320123-0",
  "channel": "restaurant:123:orders",
  "type": "order.created",
  "payload": {"order_id": "ord_123"},
  "actor": {"type": "waiter", "id": "usr_123"},
  "metadata": {"correlation_id": "req_abc123"},
  "created_at": "2026-06-29T12:00:00Z"
}
```

## RestaurantHUB Example

ReplayRail core stays generic. RestaurantHUB can model application-specific behavior with channels and event types:

```python
await rail.publish(
    channel=f"restaurant:{restaurant_id}:kitchen",
    event_type="order.ready",
    payload={
        "order_id": order_id,
        "table_id": table_id,
    },
    actor={
        "type": "kitchen_staff",
        "id": staff_id,
    },
    metadata={
        "source": "restauranthub-api",
        "correlation_id": request_id,
    },
)
```

Suggested channels:

- `restaurant:{restaurant_id}:orders`
- `restaurant:{restaurant_id}:kitchen`
- `restaurant:{restaurant_id}:tables`
- `restaurant:{restaurant_id}:reservations`
- `restaurant:{restaurant_id}:admin`
- `order:{order_id}`
- `user:{user_id}:notifications`

Suggested events:

- `order.created`
- `order.confirmed`
- `order.preparing`
- `order.ready`
- `order.delivered`
- `order.cancelled`
- `kitchen.ticket.created`
- `kitchen.ticket.updated`
- `table.occupied`
- `table.released`
- `reservation.created`
- `reservation.cancelled`
- `payment.failed`
- `inventory.low`

## Why Not Just `redis.asyncio`?

You can use `redis.asyncio` directly. ReplayRail adds reusable application semantics on top of Redis Streams:

- event envelopes;
- channel validation;
- JSON serialization boundaries;
- cursor-based replay;
- reconnect recovery through `last_event_id`;
- retention configuration;
- WebSocket delivery;
- pluggable stores for tests and future backends.

`redis.asyncio` gives you Redis commands. ReplayRail gives your WebSocket application a durable realtime event contract.

## Included In v0.1

- Python package named `replayrail`.
- Core event models and validation.
- Config object.
- Event store protocol.
- Redis Streams backend using `redis.asyncio`.
- In-memory backend for tests and local development.
- `ReplayRail.publish(...)`, `ReplayRail.replay(...)`, and `ReplayRail.read(...)`.
- FastAPI / Starlette WebSocket integration.
- Cursor-based recovery with `last_event_id`.
- Basic stream retention through `maxlen`.
- JSON serialization.
- Minimal FastAPI example.

## Intentionally Not Included In v0.1

- advanced client ACK protocol;
- Redis consumer groups;
- distributed fanout optimization;
- dashboards;
- metrics/exporters;
- Kafka/NATS/PostgreSQL backends;
- long-term compliance archive;
- complex auth framework;
- frontend SDK;
- admin UI;
- CLI.

## Known Limitation

v0.1 prioritizes correctness and simplicity. The WebSocket integration uses one blocking read loop per WebSocket subscription. Future versions may add a local per-channel fanout manager so multiple WebSocket clients subscribed to the same channel share one Redis read loop per process.

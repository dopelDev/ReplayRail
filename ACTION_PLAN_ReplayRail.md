# ReplayRail Development Action Plan

> **Project name:** ReplayRail  
> **Python package:** `replayrail`  
> **Description:** Durable, replayable and auditable realtime events for Python WebSockets, powered by Redis Streams.

This document is written as an implementation plan for a coding agent working inside the repository.

---

## 0. Goal

Build the first usable version of **ReplayRail**, a Python library that adds a durable realtime event layer on top of **Redis Streams** and **WebSockets**.

The library should not be a thin wrapper around `redis.asyncio`. It should provide reusable application-level semantics:

- structured event envelopes;
- channel-based publishing;
- cursor-based replay;
- WebSocket delivery;
- reconnection recovery;
- audit metadata;
- retention configuration;
- pluggable event store interface;
- testable in-memory backend.

The first version should be small, stable and useful for projects such as **RestaurantHUB**, while keeping the core generic enough for other apps.

---

## 1. Product scope for v0.1.0

### Include in v0.1.0

Implement these features:

1. Python package named `replayrail`.
2. Core event models.
3. Config object.
4. Event store protocol/interface.
5. Redis Streams backend using `redis.asyncio`.
6. In-memory backend for tests and local development.
7. `ReplayRail.publish(...)` API.
8. `ReplayRail.replay(...)` API.
9. Basic WebSocket integration for FastAPI/Starlette.
10. Cursor-based recovery using `last_event_id`.
11. Basic stream retention through `maxlen`.
12. JSON serialization.
13. Unit tests.
14. Minimal FastAPI example.
15. README updated with the current public API.

### Do not include in v0.1.0

Do **not** implement these yet:

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

These can be added later after the core API is validated.

---

## 2. Design principle

ReplayRail should be:

```txt
Strict where correctness matters.
Flexible where applications differ.
```

### Strict in the core

Be strict about:

- event envelope fields;
- event IDs;
- channel validation;
- event type validation;
- cursor behavior;
- serialization;
- replay ordering;
- error types;
- Redis stream key generation.

### Flexible at the edges

Be configurable for:

- stream prefix;
- replay limit;
- retention/maxlen;
- serializer;
- backend store;
- WebSocket route shape;
- authorization hook;
- channel naming conventions;
- app-specific metadata.

The core must not contain RestaurantHUB-specific concepts such as orders, kitchens, tables or reservations.

---

## 3. Recommended repository structure

Use a `src/` layout.

```txt
.
├── pyproject.toml
├── README.md
├── LICENSE
├── docker-compose.yml
├── examples/
│   └── fastapi_app.py
├── src/
│   └── replayrail/
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── events.py
│       ├── rail.py
│       ├── serializers.py
│       ├── store.py
│       ├── stores/
│       │   ├── __init__.py
│       │   ├── memory.py
│       │   └── redis.py
│       └── integrations/
│           ├── __init__.py
│           └── fastapi.py
└── tests/
    ├── test_events.py
    ├── test_memory_store.py
    ├── test_rail.py
    ├── test_serializers.py
    ├── test_redis_store.py
    └── test_fastapi_integration.py
```

---

## 4. Packaging requirements

Create or update `pyproject.toml`.

Recommended metadata:

```toml
[project]
name = "replayrail"
version = "0.1.0"
description = "Durable, replayable and auditable realtime events for Python WebSockets, powered by Redis Streams."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [
  { name = "ReplayRail contributors" }
]
keywords = [
  "redis",
  "redis-streams",
  "websockets",
  "fastapi",
  "realtime",
  "events",
  "replay",
  "audit-log"
]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Framework :: FastAPI",
  "Topic :: Software Development :: Libraries :: Python Modules"
]

dependencies = []

[project.optional-dependencies]
redis = ["redis>=5"]
fastapi = ["fastapi>=0.100", "starlette>=0.27"]
dev = [
  "pytest",
  "pytest-asyncio",
  "ruff",
  "mypy",
  "httpx",
  "uvicorn"
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

Notes:

- The package name should be `replayrail`.
- The import should be `import replayrail`.
- Do not name the package `ReplayRail`, `replay-rail` or `replay_rail`.
- Do not use `aioredis`; use `redis.asyncio` for the Redis backend.
- Keep core dependencies empty if possible. Put Redis and FastAPI under extras.

---

## 5. Core public API target

The public API should support this minimal usage:

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

FastAPI usage target:

```python
from fastapi import FastAPI, WebSocket
from replayrail.integrations.fastapi import ReplayRailWebSocket

app = FastAPI()
ws = ReplayRailWebSocket(rail)

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    await ws.subscribe(websocket, channel=channel)
```

RestaurantHUB usage target:

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

---

## 6. Core models

Implement `src/replayrail/events.py`.

Recommended models:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

JsonMapping = Mapping[str, Any]

@dataclass(slots=True, frozen=True)
class NewEvent:
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None = None
    metadata: JsonMapping = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(slots=True, frozen=True)
class ReplayEvent:
    id: str
    channel: str
    type: str
    payload: JsonMapping
    actor: JsonMapping | None
    metadata: JsonMapping
    created_at: datetime
```

Also implement helpers:

```python
def validate_channel(channel: str) -> None: ...
def validate_event_type(event_type: str) -> None: ...
def utc_now() -> datetime: ...
def datetime_to_wire(value: datetime) -> str: ...
def datetime_from_wire(value: str) -> datetime: ...
```

Validation rules:

- `channel` must be a non-empty string.
- `event_type` must be a non-empty string.
- Allow common characters in channels: letters, numbers, `.`, `_`, `-`, `:`, `/`.
- Allow common event types: letters, numbers, `.`, `_`, `-`, `:`.
- Raise library-specific errors, not generic `ValueError`, at the public API boundary.

---

## 7. Error types

Implement `src/replayrail/errors.py`.

Recommended errors:

```python
class ReplayRailError(Exception): ...
class InvalidChannelError(ReplayRailError): ...
class InvalidEventTypeError(ReplayRailError): ...
class InvalidCursorError(ReplayRailError): ...
class SerializationError(ReplayRailError): ...
class StoreError(ReplayRailError): ...
class ReplayWindowExpiredError(ReplayRailError): ...
class WebSocketDeliveryError(ReplayRailError): ...
```

Use these errors consistently.

---

## 8. Configuration

Implement `src/replayrail/config.py`.

Recommended config:

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class ReplayRailConfig:
    stream_prefix: str = "rr"
    default_replay_limit: int = 100
    max_stream_length: int | None = 10_000
    trim_approximate: bool = True
    websocket_read_block_ms: int = 5_000
    websocket_batch_size: int = 100
    default_start_position: str = "latest"  # "latest" or "earliest"
```

Behavior:

- If `last_event_id` is provided by the WebSocket client, replay after that ID.
- If `last_event_id` is missing and `default_start_position == "latest"`, only send new events.
- If `last_event_id` is missing and `default_start_position == "earliest"`, replay from `0-0`.

---

## 9. Serialization

Implement `src/replayrail/serializers.py`.

Default serializer: JSON.

Required behavior:

- Convert `payload`, `actor` and `metadata` to JSON strings before storing in Redis.
- Convert JSON strings back to dicts when reading.
- Raise `SerializationError` on invalid/non-serializable data.
- Keep serializer interface pluggable.

Suggested interface:

```python
from typing import Protocol, Any

class Serializer(Protocol):
    def dumps(self, value: Any) -> str: ...
    def loads(self, value: str) -> Any: ...

class JsonSerializer:
    def dumps(self, value: Any) -> str: ...
    def loads(self, value: str) -> Any: ...
```

---

## 10. Event store interface

Implement `src/replayrail/store.py`.

Suggested protocol:

```python
from typing import Protocol
from .events import NewEvent, ReplayEvent

class EventStore(Protocol):
    async def publish(
        self,
        event: NewEvent,
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> ReplayEvent:
        ...

    async def replay(
        self,
        channel: str,
        *,
        after: str | None,
        limit: int,
    ) -> list[ReplayEvent]:
        ...

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None,
        limit: int,
    ) -> list[ReplayEvent]:
        ...

    async def close(self) -> None:
        ...
```

Meaning:

- `publish` stores one event and returns it with its assigned stream ID.
- `replay` returns historical events after a cursor.
- `read` blocks/waits for new events after a cursor when supported.
- `close` releases resources where necessary.

---

## 11. Redis Streams backend

Implement `src/replayrail/stores/redis.py`.

Class:

```python
class RedisStreamStore:
    def __init__(
        self,
        client: Any,
        *,
        stream_prefix: str = "rr",
        serializer: Serializer | None = None,
    ) -> None:
        ...
```

### Stream key format

Use this default:

```txt
{stream_prefix}:{channel}
```

Examples:

```txt
rr:restaurant:123:orders
rr:user:usr_123:notifications
rr:system:alerts
```

Implement method:

```python
def stream_key(self, channel: str) -> str:
    ...
```

### Redis fields

Store fields like this:

```txt
channel      -> string
 type        -> string
 payload     -> JSON string
 actor       -> JSON string or empty/null
 metadata    -> JSON string
 created_at  -> ISO-8601 UTC string
```

Use consistent names without spaces.

### Publish implementation

Use Redis Streams `XADD`.

Expected behavior:

- Validate/serialize event.
- Call `xadd` with optional `maxlen` and `approximate`.
- Return `ReplayEvent` with Redis stream ID.

Pseudo-code:

```python
fields = self._event_to_fields(event)
stream_id = await self._client.xadd(
    self.stream_key(event.channel),
    fields,
    maxlen=maxlen,
    approximate=approximate,
)
return self._fields_to_event(stream_id, fields)
```

Handle both `bytes` and `str` responses, because users may or may not configure `decode_responses=True`.

### Replay implementation

Use Redis `XRANGE`.

Behavior:

- If `after is None`, read from `0-0`.
- If `after` is provided, replay must be exclusive: do not return the event with the same ID.
- Limit results using `count=limit`.

Implementation note:

- Redis supports exclusive lower bound with a `(` prefix in stream range queries.
- If the Redis client/API makes this awkward, read from `after` and filter out the first matching ID in Python.

### Blocking read implementation

Use Redis `XREAD`.

Behavior:

- `after="$"` means only new events.
- `after="0-0"` means read available events from the beginning.
- Return a list of `ReplayEvent`.
- If timeout returns nothing, return an empty list.

Pseudo-code:

```python
response = await self._client.xread(
    {self.stream_key(channel): after},
    count=limit,
    block=block_ms,
)
```

Then decode the Redis response into `ReplayEvent` instances.

---

## 12. In-memory backend

Implement `src/replayrail/stores/memory.py`.

Purpose:

- Fast unit tests.
- Local examples without Redis.
- Demonstrate backend abstraction.

Behavior:

- Preserve event order per channel.
- Generate Redis-like IDs such as `milliseconds-sequence`.
- Support `publish`, `replay`, `read`, `close`.
- `read` should wait for new events using `asyncio.Condition`.
- Support basic maxlen trimming.

This backend does not need to be distributed or persistent.

---

## 13. ReplayRail service

Implement `src/replayrail/rail.py`.

Class:

```python
class ReplayRail:
    def __init__(
        self,
        store: EventStore,
        *,
        config: ReplayRailConfig | None = None,
    ) -> None:
        ...

    async def publish(
        self,
        *,
        channel: str,
        event_type: str,
        payload: Mapping[str, Any],
        actor: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ReplayEvent:
        ...

    async def replay(
        self,
        channel: str,
        *,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[ReplayEvent]:
        ...

    async def read(
        self,
        channel: str,
        *,
        after: str,
        block_ms: int | None = None,
        limit: int | None = None,
    ) -> list[ReplayEvent]:
        ...

    async def close(self) -> None:
        ...
```

Responsibilities:

- Validate channel and event type.
- Construct `NewEvent`.
- Apply config defaults.
- Delegate to store.
- Keep the public API stable and backend-agnostic.

---

## 14. FastAPI / Starlette WebSocket integration

Implement `src/replayrail/integrations/fastapi.py`.

Class:

```python
class ReplayRailWebSocket:
    def __init__(self, rail: ReplayRail) -> None:
        ...

    async def subscribe(
        self,
        websocket: WebSocket,
        *,
        channel: str,
        last_event_id: str | None = None,
        auto_accept: bool = True,
    ) -> None:
        ...
```

### Query parameter behavior

If `last_event_id` is not passed explicitly, read it from:

```txt
?last_event_id=<id>
```

### Delivery behavior

For v0.1.0, use a simple and correct implementation:

1. Accept the WebSocket if `auto_accept=True`.
2. Determine initial cursor:
   - If `last_event_id` exists, replay missed events after it.
   - If no `last_event_id` and config says `latest`, start live mode from `$`.
   - If no `last_event_id` and config says `earliest`, replay from `0-0`.
3. Send replayed events to the client.
4. Continue reading new events from the store with blocking reads.
5. Send each event as JSON.
6. Update local cursor after each sent event.
7. Exit cleanly on disconnect.

### Important v0.1 simplification

It is acceptable for v0.1 to use one Redis read loop per WebSocket connection.

Document this limitation in comments or README:

```txt
v0.1 prioritizes correctness and simplicity. Future versions may add per-channel fanout workers to reduce Redis reads when many clients subscribe to the same channel.
```

### Event JSON sent over WebSocket

Send the event envelope directly:

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

Implement `event_to_dict(event: ReplayEvent) -> dict` helper.

---

## 15. Example FastAPI app

Implement `examples/fastapi_app.py`.

It should include:

- Redis client setup.
- ReplayRail setup.
- WebSocket endpoint.
- HTTP endpoint to publish test events.

Example endpoints:

```txt
POST /events/{channel}
WS   /ws/{channel}?last_event_id=<id>
```

Example publish body:

```json
{
  "type": "order.created",
  "payload": {
    "order_id": "ord_123"
  }
}
```

Run command in README:

```bash
uvicorn examples.fastapi_app:app --reload
```

---

## 16. RestaurantHUB example guidance

Do not add RestaurantHUB-specific classes to the library core.

But include an example in README showing how RestaurantHUB would use ReplayRail.

Suggested channels:

```txt
restaurant:{restaurant_id}:orders
restaurant:{restaurant_id}:kitchen
restaurant:{restaurant_id}:tables
restaurant:{restaurant_id}:reservations
restaurant:{restaurant_id}:admin
order:{order_id}
user:{user_id}:notifications
```

Suggested events:

```txt
order.created
order.confirmed
order.preparing
order.ready
order.delivered
order.cancelled
kitchen.ticket.created
kitchen.ticket.updated
table.occupied
table.released
reservation.created
reservation.cancelled
payment.failed
inventory.low
```

---

## 17. Tests

Implement tests before considering v0.1 complete.

### Unit tests

`tests/test_events.py`

- valid channel passes;
- empty channel fails;
- invalid event type fails;
- datetime serialization roundtrip works.

`tests/test_serializers.py`

- JSON serializer dumps/loads dict;
- non-serializable payload raises `SerializationError`.

`tests/test_memory_store.py`

- publish returns ID;
- replay returns events in order;
- replay after an ID is exclusive;
- maxlen trimming works;
- blocking read returns new event.

`tests/test_rail.py`

- `ReplayRail.publish` validates input;
- `ReplayRail.replay` uses default limit;
- metadata defaults to `{}`;
- actor can be `None`.

### Redis integration tests

`tests/test_redis_store.py`

These should be skipped unless `REDIS_URL` is set.

Test cases:

- publish event to Redis;
- replay event after `0-0`;
- replay after event ID excludes that event;
- blocking read gets a newly published event;
- maxlen is passed to Redis.

Pseudo-skip:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="REDIS_URL not set",
)
```

### FastAPI tests

`tests/test_fastapi_integration.py`

Minimum:

- WebSocket connects;
- published event is delivered;
- client with `last_event_id=0-0` receives replayed events.

Use memory store for these tests to avoid requiring Redis.

---

## 18. README update requirements

Update `README.md` to match the actual implemented API.

The README must include:

1. Project title: `ReplayRail`.
2. Description exactly:

```txt
Durable, replayable and auditable realtime events for Python WebSockets, powered by Redis Streams.
```

3. Installation:

```bash
pip install replayrail
pip install "replayrail[redis,fastapi]"
```

4. Quickstart with Redis.
5. Quickstart with FastAPI WebSocket.
6. Explanation of `last_event_id`.
7. Event envelope example.
8. RestaurantHUB example.
9. Why not just `redis.asyncio`?
10. What is intentionally not included in v0.1.

---

## 19. Acceptance criteria

The implementation is acceptable when all of these are true:

1. `pip install -e ".[redis,fastapi,dev]"` works.
2. `import replayrail` works.
3. `from replayrail import ReplayRail, ReplayRailConfig` works.
4. Memory store tests pass.
5. Redis store tests pass when `REDIS_URL` is available.
6. FastAPI example starts with Uvicorn.
7. A WebSocket client can receive a newly published event.
8. A WebSocket client can reconnect with `last_event_id` and receive missed events.
9. Events include `id`, `channel`, `type`, `payload`, `actor`, `metadata`, `created_at`.
10. The core package does not depend directly on FastAPI.
11. The core package does not depend directly on RestaurantHUB concepts.
12. README examples match the implemented API.
13. Ruff passes.
14. Mypy passes or has documented minimal exclusions.
15. Pytest passes.

---

## 20. Suggested implementation order

Follow this exact order:

### Step 1: Inspect repo

- Check existing files.
- Do not delete existing work unless clearly obsolete.
- Preserve README content that is still useful.

### Step 2: Packaging

- Add/update `pyproject.toml`.
- Use package name `replayrail`.
- Add optional extras: `redis`, `fastapi`, `dev`.

### Step 3: Core models and errors

- Implement `events.py`.
- Implement `errors.py`.
- Add tests.

### Step 4: Serializer

- Implement `serializers.py`.
- Add tests.

### Step 5: Store protocol

- Implement `store.py`.
- Keep it backend-agnostic.

### Step 6: Memory store

- Implement `stores/memory.py`.
- Add tests.

### Step 7: ReplayRail service

- Implement `rail.py`.
- Add tests using memory store.

### Step 8: Redis store

- Implement `stores/redis.py` using `redis.asyncio`-compatible client.
- Add integration tests gated by `REDIS_URL`.

### Step 9: FastAPI integration

- Implement `integrations/fastapi.py`.
- Add tests with memory store.

### Step 10: Example app

- Implement `examples/fastapi_app.py`.
- Add `docker-compose.yml` for Redis.

### Step 11: README

- Update README to reflect actual API.
- Include RestaurantHUB example without adding domain-specific code to the library.

### Step 12: Quality pass

Run:

```bash
ruff check .
ruff format .
mypy src/replayrail
pytest
```

Fix issues.

---

## 21. Coding guidelines for the agent

- Prefer small, typed modules.
- Use `dataclasses` for core models unless there is a strong reason to add Pydantic.
- Do not add unnecessary dependencies to core.
- Do not use `aioredis`.
- Keep Redis support optional through extras.
- Avoid global state.
- Avoid RestaurantHUB-specific code in `src/replayrail`.
- Use explicit error types.
- Keep public API simple.
- Write tests for behavior, not implementation details.
- Document any known limitation.

---

## 22. Known limitation to document

For v0.1, the WebSocket integration can use one blocking read loop per WebSocket subscription.

This is acceptable for the first version because it is simple and correct.

Document future improvement:

```txt
Future versions may add a local per-channel fanout manager so multiple WebSocket clients subscribed to the same channel share one Redis read loop per process.
```

---

## 23. Future roadmap after v0.1

### v0.2

- Per-channel fanout worker.
- Authorization hook.
- Better WebSocket lifecycle handling.
- Control messages such as `replay_complete`.
- More robust reconnect behavior.

### v0.3

- Client ACK mode.
- Delivery tracking.
- Retry policy.
- Dead-letter stream.

### v0.4

- Consumer group helpers.
- Worker processing helpers.
- Metrics hooks.

### Later

- NATS JetStream backend.
- PostgreSQL event table backend.
- Kafka/Redpanda backend.
- Frontend helper package.

---

## 24. Final instruction to the coding agent

Implement ReplayRail v0.1.0 according to this action plan.

Prioritize:

1. correctness;
2. simple public API;
3. tests;
4. clear README;
5. generic design reusable beyond RestaurantHUB.

Do not overbuild. The first version should prove this core loop:

```txt
publish event -> persist to Redis Stream -> deliver over WebSocket -> reconnect with cursor -> replay missed events
```


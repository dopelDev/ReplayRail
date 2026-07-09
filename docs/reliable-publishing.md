# Reliable publishing

## What ReplayRail guarantees

ReplayRail validates event envelopes, assigns a stable logical `event_id`, publishes to the configured event store, and returns a storage cursor in `ReplayEvent.id`.

The cursor is for replay. The logical `event_id` is for tracing, deduplication, retry safety, idempotency, and client-side duplicate handling.

## What ReplayRail does not guarantee

ReplayRail publish is not atomic with your application database.

ReplayRail does not implement outbox storage, database transactions, SQLAlchemy models, migrations, or background workers.

## The database dual-write problem

If your application writes to a database and then publishes to ReplayRail, the database write may succeed while Redis publishing fails.

The opposite ordering has a similar risk: publishing to ReplayRail may succeed while the database write fails or rolls back.

For critical workflows, your application should use a transactional outbox owned by the application database.

## Recommended pattern: application-owned transactional outbox

Use your application database transaction to persist both the business change and an outbox row. A separate application-owned publisher can later read pending outbox rows and call ReplayRail.

ReplayRail does not own this transaction. Your application owns the transaction, table, claiming behavior, retry policy, and worker lifecycle.

## How ReplayRail helps without owning your database

ReplayRail provides stable `event_id`, `prepare_event()`, `publish_event()`, serialization helpers, and optional Redis idempotency to make external outbox implementations safer.

Use `prepare_event()` before the database transaction commits. Store the prepared event data in your own outbox using `new_event_to_dict()`. Later, reconstruct the event with `new_event_from_dict()` and publish with `publish_event()`.

## Example flow

This is conceptual pseudocode only. It intentionally does not define a database model, migration, ORM, or worker framework.

```python
event = rail.prepare_event(
    channel=f"ticket:{ticket_id}",
    event_type="ticket.item.added",
    payload={"item_id": item_id},
    actor={"type": "user", "id": str(user_id)},
)

with app_owned_transaction():
    save_ticket_item(...)
    save_outbox_event(
        event_id=event.event_id,
        channel=event.channel,
        event_type=event.type,
        payload=event.payload,
        actor=event.actor,
        metadata=event.metadata,
        created_at=event.created_at,
    )
```

Publisher pseudocode:

```python
for row in claim_pending_outbox_events():
    event = NewEvent(
        event_id=row.event_id,
        channel=row.channel,
        type=row.event_type,
        payload=row.payload,
        actor=row.actor,
        metadata=row.metadata,
        created_at=row.created_at,
    )

    published = await rail.publish_event(event)

    mark_outbox_event_published(
        row.id,
        stream_id=published.id,
    )
```

The dict helpers are usually easier to store:

```python
data = new_event_to_dict(event)
event = new_event_from_dict(data)
published = await rail.publish_event(event)
```

## Client deduplication with event_id

Clients can keep a short-lived set of processed `event_id` values. If a client receives the same logical event more than once, it can ignore the duplicate while still using `id` as the replay cursor.

Do not use `event_id` as the replay cursor. Use `ReplayEvent.id` and WebSocket `last_event_id` for replay.

## Handling replay window expiration

ReplayRail replay is bounded by stream retention. If a client reconnects with a cursor older than retained history, a store may raise `ReplayWindowExpiredError`.

Applications should decide how to recover: reload current state from their own system of record, ask the client to resync, or increase stream retention for channels that need a longer replay window.

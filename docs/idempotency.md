# Redis idempotency

## Why duplicates can happen

Applications that use an app-owned outbox usually retry publishing until an event is marked published. A crash, timeout, or network failure can leave the application unsure whether Redis received the event.

Optional Redis idempotency lets ReplayRail deduplicate publishes by logical `event_id`.

## event_id vs stream id

`event_id` is the stable logical event identifier chosen before publishing.

`ReplayEvent.id` is the storage cursor returned by Redis Streams. Clients use it for replay with `last_event_id`.

## duplicate_policy="return_existing"

With `duplicate_policy="return_existing"`, publishing the same `event_id` with the same event content returns a `ReplayEvent` with the existing Redis stream id.

No second stream entry is created.

```python
store = RedisStreamStore(redis_client, idempotency=True)
```

## duplicate_policy="raise"

With `duplicate_policy="raise"`, publishing the same `event_id` with the same event content raises `DuplicateEventError`.

```python
store = RedisStreamStore(
    redis_client,
    idempotency=True,
    duplicate_policy="raise",
)
```

## DuplicateEventConflictError

If the same `event_id` is reused for different event content, ReplayRail raises `DuplicateEventConflictError` for both duplicate policies.

The event fingerprint includes channel, type, payload, actor, metadata, and created_at. It does not include `event_id`, because `event_id` is the lookup key.

## TTL and stream trimming caveats

By default, Redis idempotency keys expire after 86,400 seconds.

If `max_stream_length` trims old stream entries but idempotency keys live longer, ReplayRail may return an old stream id for a duplicate event that is no longer replayable.

Set `idempotency_ttl_seconds` according to your stream retention policy. Use `idempotency_ttl_seconds=None` only when you intentionally want idempotency keys without expiration.

## Recommended use with app-owned outbox

For critical database workflows, prepare the event before committing your application transaction, store it in your app-owned outbox, and publish it later with `publish_event()`.

Redis idempotency is a retry aid for the publish step. It is not a database transaction manager and does not replace an application-owned transactional outbox.

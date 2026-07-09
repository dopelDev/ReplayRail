# Changelog

All notable changes to ReplayRail are documented in this file.

## 0.2.0 - Unreleased

### Added

- Added logical `event_id` to `NewEvent` and `ReplayEvent`.
- Added `ReplayRail.prepare_event()`.
- Added `ReplayRail.publish_event()`.
- Added stable event dict serialization helpers.
- Added optional Redis publish idempotency by `event_id`.
- Added optional MemoryEventStore idempotency by `event_id`.
- Added duplicate event errors.
- Added optional healthcheck support.
- Added docs for reliable publishing and app-owned outbox patterns.

### Changed

- WebSocket event payloads now include `event_id`.
- Redis events now persist `event_id`.
- Redis decoding falls back to stream id for old events without `event_id`.

### Notes

ReplayRail does not implement database transactions, SQLAlchemy integration,
outbox tables, migrations, or outbox workers. Applications that need reliable
database-to-ReplayRail publishing should implement an app-owned transactional
outbox.

## 0.1.0 - 2026-06-29

- Implement initial ReplayRail package with core event models, configuration, errors, JSON serialization, memory and Redis stores, FastAPI WebSocket integration, example app, README, and tests.

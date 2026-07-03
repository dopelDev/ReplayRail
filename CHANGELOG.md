# Changelog

All notable changes to ReplayRail are documented in this file.

## 0.1.2 - Unreleased

- Add a reproducible Docker test gate with Redis-backed verification.
- Add README contract tests for publish/replay and WebSocket recovery with `last_event_id`.
- Add FastAPI tests for `default_start_position="latest"` and `"earliest"`.
- Add shared stream cursor validation and consistent `InvalidCursorError` behavior.
- Add retained-history detection through `ReplayWindowExpiredError` where stores can determine that a cursor is older than retained events.
- Preserve and test audit context fields including `actor`, `metadata`, correlation IDs, and timestamps across memory and Redis stores.
- Add PyPI readiness checks with `twine check`.
- Add GitHub Actions CI and a manual/release PyPI publish workflow.

## 0.1.0 - 2026-06-29

- Implement initial ReplayRail package with core event models, configuration, errors, JSON serialization, memory and Redis stores, FastAPI WebSocket integration, example app, README, and tests.

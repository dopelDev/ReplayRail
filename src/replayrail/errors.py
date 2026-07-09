from __future__ import annotations

from typing import Any


class ReplayRailError(Exception):
    """Base error for ReplayRail."""

    def __init__(self, message: str = "", **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context


class InvalidChannelError(ReplayRailError):
    """Raised when a channel name is empty or contains unsupported characters."""


class InvalidEventTypeError(ReplayRailError):
    """Raised when an event type is empty or contains unsupported characters."""


class InvalidEventIdError(ReplayRailError):
    """Raised when an event_id is invalid."""


class InvalidCursorError(ReplayRailError):
    """Raised when a replay/read cursor is malformed."""


class SerializationError(ReplayRailError):
    """Raised when event data cannot be serialized or deserialized."""


class StoreError(ReplayRailError):
    """Raised when an event store operation fails."""


class DuplicateEventError(ReplayRailError):
    """Raised when an event_id has already been published."""


class DuplicateEventConflictError(DuplicateEventError):
    """Raised when the same event_id is reused for different event content."""


class ReplayWindowExpiredError(ReplayRailError):
    """Raised when requested replay data is no longer available."""


class WebSocketDeliveryError(ReplayRailError):
    """Raised when WebSocket event delivery fails."""

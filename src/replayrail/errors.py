class ReplayRailError(Exception):
    """Base error for ReplayRail."""


class InvalidChannelError(ReplayRailError):
    """Raised when a channel name is empty or contains unsupported characters."""


class InvalidEventTypeError(ReplayRailError):
    """Raised when an event type is empty or contains unsupported characters."""


class InvalidCursorError(ReplayRailError):
    """Raised when a replay/read cursor is malformed."""


class SerializationError(ReplayRailError):
    """Raised when event data cannot be serialized or deserialized."""


class StoreError(ReplayRailError):
    """Raised when an event store operation fails."""


class ReplayWindowExpiredError(ReplayRailError):
    """Raised when requested replay data is no longer available."""


class WebSocketDeliveryError(ReplayRailError):
    """Raised when WebSocket event delivery fails."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ReplayRailError


@dataclass(slots=True, frozen=True)
class ReplayRailConfig:
    stream_prefix: str = "rr"
    default_replay_limit: int = 100
    max_stream_length: int | None = 10_000
    trim_approximate: bool = True
    websocket_read_block_ms: int = 5_000
    websocket_batch_size: int = 100
    default_start_position: str = "latest"

    def __post_init__(self) -> None:
        if not self.stream_prefix:
            raise ReplayRailError("stream_prefix must be a non-empty string")
        if self.default_replay_limit <= 0:
            raise ReplayRailError("default_replay_limit must be greater than zero")
        if self.max_stream_length is not None and self.max_stream_length <= 0:
            raise ReplayRailError("max_stream_length must be greater than zero when set")
        if self.websocket_read_block_ms < 0:
            raise ReplayRailError("websocket_read_block_ms must be greater than or equal to zero")
        if self.websocket_batch_size <= 0:
            raise ReplayRailError("websocket_batch_size must be greater than zero")
        if self.default_start_position not in {"latest", "earliest"}:
            raise ReplayRailError("default_start_position must be 'latest' or 'earliest'")

from __future__ import annotations

import json
from typing import Any, Protocol

from .errors import SerializationError


class Serializer(Protocol):
    def dumps(self, value: Any) -> str: ...

    def loads(self, value: str) -> Any: ...


class JsonSerializer:
    def dumps(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"value is not JSON serializable: {exc}") from exc

    def loads(self, value: str) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SerializationError(f"value is not valid JSON: {exc}") from exc

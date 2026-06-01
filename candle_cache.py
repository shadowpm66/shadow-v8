from __future__ import annotations

from time import time
from typing import Any


class CandleCache:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._cache.get(key)
        if not item:
            return None
        ts, value = item
        if time() - ts > self.ttl_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (time(), value)


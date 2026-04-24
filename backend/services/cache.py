from __future__ import annotations

import time
from typing import Optional

from backend.config.settings import CACHE_MAX_SIZE, CACHE_TTL_SECONDS
from backend.models import AnalysisResponse


class AnalysisCache:
    def __init__(
        self, ttl: int | None = None, max_size: int | None = None
    ) -> None:
        self._ttl = ttl if ttl is not None else CACHE_TTL_SECONDS
        self._max_size = max_size if max_size is not None else CACHE_MAX_SIZE
        self._store: dict[str, tuple[float, AnalysisResponse]] = {}

    def get(self, conversation_id: str) -> Optional[AnalysisResponse]:
        entry = self._store.get(conversation_id)
        if entry is None:
            return None
        expiry, response = entry
        if time.time() < expiry:
            return response
        del self._store[conversation_id]
        return None

    def put(self, conversation_id: str, response: AnalysisResponse) -> None:
        if conversation_id not in self._store and len(self._store) >= self._max_size:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
        self._store[conversation_id] = (time.time() + self._ttl, response)

    def invalidate(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        now = time.time()
        return sum(1 for expiry, _ in self._store.values() if now < expiry)

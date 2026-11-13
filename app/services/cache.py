import hashlib
import threading
import time
from collections import OrderedDict


class QueryCache:
    """Thread-safe LRU cache for QA results, keyed by normalised query + access level (+ conversation_id).

    Entries expire after ``ttl_seconds`` and the cache is bounded to ``max_size``
    entries. When full the oldest entry is evicted first.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 256,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: OrderedDict[str, tuple[float, object]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(query: str) -> str:
        return query.strip().lower()

    @staticmethod
    def _hash_key(
        normalized_query: str,
        access_level: str,
        conversation_id: str | None = None,
    ) -> str:
        raw = f"{normalized_query}||{access_level}||{conversation_id or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        query: str,
        access_level: str,
        conversation_id: str | None = None,
    ):
        """Return cached result or ``None`` for expired / missing entries."""
        key = self._hash_key(
            self._normalize(query), access_level, conversation_id
        )
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            timestamp, result = entry
            if time.time() - timestamp > self.ttl_seconds:
                # Expired – remove silently
                del self._cache[key]
                return None
            # Move to end so it stays "most recently used"
            self._cache.move_to_end(key)
            return result

    def set(
        self,
        query: str,
        access_level: str,
        result,
        conversation_id: str | None = None,
    ):
        """Store a result, evicting the oldest entry when the cache is full."""
        key = self._hash_key(
            self._normalize(query), access_level, conversation_id
        )
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (time.time(), result)
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    def invalidate(self):
        """Clear the entire cache (e.g. after a document upload)."""
        with self._lock:
            self._cache.clear()

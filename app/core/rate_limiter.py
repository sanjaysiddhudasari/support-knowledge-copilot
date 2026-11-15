"""In-memory sliding window rate limiter for FastAPI endpoints.

Guards endpoints (such as /api/query and /api/auth) against abuse and excessive
costs while requiring zero external infrastructure (Redis/Memcached).
"""

import threading
import time
from collections import defaultdict
from fastapi import HTTPException, Request, status


class RateLimiter:
    """Sliding-window in-memory rate limiter.

    Parameters
    ----------
    requests_per_minute : int
        Maximum number of requests permitted within any rolling 60-second window.
    key_func : callable, optional
        Function that extracts the client identity key from a ``Request``.
        Defaults to using the client's host IP.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        key_func=None,
    ):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self.key_func = key_func or self._default_key
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    @staticmethod
    def _default_key(request: Request) -> str:
        # Check forward headers first in case of reverse proxy (Render / Cloudflare)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = getattr(request, "client", None)
        return client.host if client else "anonymous"

    def __call__(self, request: Request) -> None:
        key = self.key_func(request)
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Purge entries older than the window
            timestamps = [t for t in self._history[key] if t > cutoff]
            if len(timestamps) >= self.requests_per_minute:
                oldest_in_window = timestamps[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: maximum {self.requests_per_minute} requests per minute. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)
            self._history[key] = timestamps

    def reset(self) -> None:
        """Reset all rate limiter records (useful for testing)."""
        with self._lock:
            self._history.clear()

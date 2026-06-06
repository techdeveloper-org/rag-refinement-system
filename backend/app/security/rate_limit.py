"""Per-credential rate limiting (ADV-003, NFR-015).

A fixed-window counter keyed by the principal's ``rate_limit_key`` enforces a
per-minute budget on every authenticated operation. Exceeding the budget
raises a 429 RATE_LIMITED problem with a ``Retry-After`` header. The default
policy covers reads; sensitive operations (erasure, data export) use a
tighter limit per ADV-003.

The in-memory window is process-local and deterministic for tests via an
injectable clock; a production deployment swaps the backing store for Redis
behind the same interface.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import Depends, Request

from backend.app.errors import rate_limited
from backend.app.security.auth import Principal, require_principal
from backend.app.settings import get_settings

_WINDOW_SECONDS = 60


class RateLimiter:
    """Fixed-window per-key rate limiter.

    Attributes are guarded by a lock so concurrent requests on the same key
    increment the counter atomically.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        """Initialize an empty limiter.

        Args:
            clock: Monotonic time source in seconds; defaults to
                :func:`time.monotonic`. Injectable for deterministic tests.
        """
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, key: str, limit: int) -> None:
        """Record a hit on ``key`` and enforce the per-window ``limit``.

        Args:
            key: The per-credential bucket key.
            limit: Maximum allowed hits within the current window.

        Raises:
            ProblemException: 429 when the limit is exceeded, carrying a
                ``Retry-After`` header for the remaining window.
        """
        now = self._clock()
        with self._lock:
            window_start, count = self._windows.get(key, (now, 0))
            if now - window_start >= _WINDOW_SECONDS:
                window_start, count = now, 0
            count += 1
            self._windows[key] = (window_start, count)
            if count > limit:
                retry_after = max(1, int(_WINDOW_SECONDS - (now - window_start)))
                raise rate_limited(retry_after)

    def reset(self) -> None:
        """Clear all rate-limit windows (test isolation)."""
        with self._lock:
            self._windows.clear()


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide rate limiter, creating it on first use.

    Returns:
        The shared :class:`RateLimiter` instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def rate_limit(*, sensitive: bool = False) -> Callable[..., Principal]:
    """Build a FastAPI dependency enforcing the per-credential rate limit.

    The dependency authenticates first (so an unauthenticated caller gets 401,
    not 429) and then applies the limit bucketed by the principal.

    Args:
        sensitive: When True, applies the tighter sensitive-operation budget
            (erasure / data export) instead of the default read budget.

    Returns:
        A dependency callable returning the authenticated :class:`Principal`.
    """

    def dependency(
        _request: Request,
        principal: Principal = Depends(require_principal),
    ) -> Principal:
        """Authenticate and enforce the rate limit for this request.

        Args:
            _request: The incoming request (unused; forces dependency wiring).
            principal: The authenticated principal.

        Returns:
            The authenticated principal once under the limit.

        Raises:
            ProblemException: 429 when the per-credential limit is exceeded.
        """
        settings = get_settings()
        limit = (
            settings.rate_limit_sensitive_per_minute
            if sensitive
            else settings.rate_limit_default_per_minute
        )
        scope = "sensitive" if sensitive else "default"
        bucket = f"{principal.rate_limit_key}:{scope}"
        get_rate_limiter().check(bucket, limit)
        return principal

    return dependency

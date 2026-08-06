"""Simple in-memory sliding-window rate limiter (per-process).

Suitable for single-instance self-hosted deployments. Behind multiple
workers/replicas, put a reverse-proxy limit (nginx/Caddy) in front as well.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.config import get_settings

# Bound in-process key growth for long-lived API processes.
_MAX_KEYS = 10_000


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Try again later.",
                    headers={"Retry-After": str(window_seconds)},
                )
            bucket.append(now)
            if len(self._hits) > _MAX_KEYS:
                stale = [k for k, q in self._hits.items() if not q]
                for k in stale:
                    del self._hits[k]


auth_rate_limiter = SlidingWindowRateLimiter()


def client_ip(request: Request) -> str:
    """Client IP for rate-limit keys.

    ``X-Forwarded-For`` is ignored unless ``TRUST_PROXY_HEADERS`` is enabled,
    so clients cannot spoof an IP to bypass auth limits on a bare deploy.
    """
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


async def limit_auth_endpoint(request: Request) -> None:
    """Dependency: rate-limit login / register / prelogin / refresh by IP."""
    settings = get_settings()
    key = f"auth:{client_ip(request)}:{request.url.path}"
    auth_rate_limiter.check(
        key,
        limit=settings.auth_rate_limit_requests,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )

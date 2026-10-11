"""Fixed-window rate limiting backed by Redis, with an in-process fallback.

Each (rule, identity) pair gets one counter per window: ``INCR`` the key for the
current window and set its expiry on first use. Fixed windows allow up to 2x the limit
across a window boundary, which is acceptable for abuse protection (this is not quota
billing) and costs one round trip per request.

If Redis is unavailable:
- ``strict`` rules (login, register) fall back to a per-process counter, because brute
  force protection must not disappear when Redis does;
- other rules fail open, so an outage of an optional dependency does not take private
  features down with it.
"""

import logging
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

import redis

from app.config import get_settings
from app.services.errors import RateLimitedError

log = logging.getLogger(__name__)
KEY_PREFIX = "piq:rl"


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_seconds: int
    strict: bool = False


LOGIN_IP = Rule("login_ip", limit=30, window_seconds=60, strict=True)
LOGIN_EMAIL = Rule("login_email", limit=10, window_seconds=900, strict=True)
REGISTER_IP = Rule("register_ip", limit=20, window_seconds=3600, strict=True)
UPLOAD = Rule("upload", limit=30, window_seconds=3600)
REPORT = Rule("report", limit=60, window_seconds=3600)
EXPORT = Rule("export", limit=60, window_seconds=3600)


class RateLimiter:
    def __init__(self, url: str, *, enabled: bool = True, socket_timeout: float = 0.25) -> None:
        self.enabled = enabled
        self._client = redis.Redis.from_url(
            url, socket_timeout=socket_timeout, socket_connect_timeout=socket_timeout
        )
        self._local: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, rule: Rule, identity: str, *, now: float | None = None) -> None:
        """Count one request; raise RateLimitedError if the window's limit is exceeded."""
        if not self.enabled:
            return
        ts = now if now is not None else time.time()
        window = int(ts // rule.window_seconds)
        key = f"{KEY_PREFIX}:{rule.name}:{identity}:{window}"
        retry_after = max(1, int((window + 1) * rule.window_seconds - ts))
        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, rule.window_seconds, nx=True)
            count = int(cast(list[int], pipe.execute())[0])
        except redis.RedisError:
            if not rule.strict:
                log.warning("rate limiter: Redis unavailable, allowing %s", rule.name)
                return
            count = self._local_hit(key, window)
        if count > rule.limit:
            raise RateLimitedError(retry_after)

    def _local_hit(self, key: str, window: int) -> int:
        with self._lock:
            # Drop counters from earlier windows so the dict cannot grow without bound.
            stale = [k for k in self._local if not k.endswith(f":{window}")]
            for k in stale:
                del self._local[k]
            self._local[key] = self._local.get(key, 0) + 1
            return self._local[key]


@lru_cache
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(settings.cache_url, enabled=settings.rate_limit_enabled)

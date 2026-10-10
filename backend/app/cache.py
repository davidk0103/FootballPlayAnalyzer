"""Redis cache for analytics responses.

Keys are deterministic: namespace, season, dataset checksum, a per-season generation
number, and a hash of the canonical request parameters. A completed import bumps the
season's generation, so every older key for that season stops being read immediately
(and is deleted best-effort). Redis is optional: on any Redis error the cache reports
DEGRADED, the caller computes the response directly, and Redis is skipped for a short
back-off window instead of paying a timeout on every request.
"""

import enum
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any, TypeVar, cast

import redis
from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
KEY_PREFIX = "piq:cache:v1"
GEN_PREFIX = "piq:cache:gen"
STATS_KEY = "piq:cache:stats"


class CacheStatus(enum.StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


def params_digest(params: Mapping[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def cache_key(
    namespace: str, season: int, dataset_sha: str, generation: int, params: Mapping[str, Any]
) -> str:
    return (
        f"{KEY_PREFIX}:{namespace}:s{season}:d{dataset_sha[:16]}:g{generation}:"
        f"{params_digest(params)}"
    )


class AnalyticsCache:
    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: int,
        socket_timeout: float,
        retry_after_seconds: float,
        enabled: bool = True,
    ) -> None:
        self.ttl = ttl_seconds
        self.enabled = enabled
        self.retry_after = retry_after_seconds
        self._client = redis.Redis.from_url(
            url, socket_timeout=socket_timeout, socket_connect_timeout=socket_timeout
        )
        self._down_until = 0.0
        self._lock = threading.Lock()
        self.local_errors = 0

    def _available(self) -> bool:
        return self.enabled and time.monotonic() >= self._down_until

    def _mark_down(self, exc: Exception) -> None:
        with self._lock:
            self.local_errors += 1
            self._down_until = time.monotonic() + self.retry_after
        log.warning("analytics cache unavailable, serving uncached: %s", exc)

    def _incr(self, field: str) -> None:
        try:
            self._client.hincrby(STATS_KEY, field, 1)
        except redis.RedisError as exc:
            self._mark_down(exc)

    def generation(self, season: int) -> int:
        raw = cast(bytes | None, self._client.get(f"{GEN_PREFIX}:{season}"))
        return int(raw) if raw is not None else 0

    def get_or_compute(
        self,
        *,
        namespace: str,
        season: int,
        dataset_sha: str,
        params: Mapping[str, Any],
        model: type[T],
        compute: Callable[[], T],
        bypass: bool = False,
    ) -> tuple[T, CacheStatus]:
        if not self.enabled:
            return compute(), CacheStatus.DISABLED
        if bypass:
            if self._available():
                self._incr("bypass")
            return compute(), CacheStatus.BYPASS
        if not self._available():
            return compute(), CacheStatus.DEGRADED
        try:
            key = cache_key(namespace, season, dataset_sha, self.generation(season), params)
            raw = cast(bytes | None, self._client.get(key))
        except redis.RedisError as exc:
            self._mark_down(exc)
            return compute(), CacheStatus.DEGRADED
        if raw is not None:
            try:
                value = model.model_validate_json(raw)
            except ValueError:
                log.warning("discarding unreadable cache entry %s", key)
            else:
                self._incr("hits")
                return value, CacheStatus.HIT

        value = compute()
        try:
            self._client.set(key, value.model_dump_json(), ex=self.ttl)
            self._client.hincrby(STATS_KEY, "misses", 1)
        except redis.RedisError as exc:
            self._mark_down(exc)
            return value, CacheStatus.DEGRADED
        return value, CacheStatus.MISS

    def invalidate_season(self, season: int) -> bool:
        """Bump the season's generation and delete its old keys. False if Redis is down.

        If Redis is unreachable here, entries for the old dataset can still be served
        until their TTL expires only if the dataset checksum did not change (a forced
        re-import of the same file); a new file changes the key regardless.
        """
        try:
            self._client.incr(f"{GEN_PREFIX}:{season}")
            deleted = 0
            for key in self._client.scan_iter(f"{KEY_PREFIX}:*:s{season}:*", count=500):
                deleted += cast(int, self._client.delete(key))
            self._client.hincrby(STATS_KEY, "invalidations", 1)
            log.info("invalidated %s cached responses for season %s", deleted, season)
            return True
        except redis.RedisError as exc:
            self._mark_down(exc)
            return False

    def stats(self) -> dict[str, Any]:
        counters = {"hits": 0, "misses": 0, "bypass": 0, "invalidations": 0}
        available = True
        try:
            raw = cast(dict[bytes, bytes], self._client.hgetall(STATS_KEY))
            for k, v in raw.items():
                name = k.decode() if isinstance(k, bytes) else str(k)
                counters[name] = int(v)
        except redis.RedisError:
            available = False
        lookups = counters["hits"] + counters["misses"]
        return {
            "enabled": self.enabled,
            "available": available,
            **counters,
            "hit_rate": round(counters["hits"] / lookups, 4) if lookups else None,
            "degraded_errors_this_process": self.local_errors,
            "ttl_seconds": self.ttl,
        }

    def reset_stats(self) -> None:
        self._client.delete(STATS_KEY)


@lru_cache
def get_cache() -> AnalyticsCache:
    s = get_settings()
    return AnalyticsCache(
        s.cache_url,
        ttl_seconds=s.cache_ttl_seconds,
        socket_timeout=s.cache_socket_timeout_seconds,
        retry_after_seconds=s.cache_retry_after_seconds,
        enabled=s.cache_enabled,
    )

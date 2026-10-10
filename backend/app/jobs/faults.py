"""Test-only fault injection, enabled by ENABLE_FAULT_INJECTION=true on the worker.

Integration tests set a Redis key ``piq:faults:season:<season>`` to a JSON object:

- ``transient_failures``: fail the first N attempts with a TransientJobError
- ``sleep_per_chunk``: seconds to sleep after each upserted chunk (to kill/cancel mid-run)
- ``fail_after_chunks``: raise a PermanentJobError after N chunks (to test rollback)
"""

import json
import time
from typing import Any, cast

import redis

from app.config import get_settings
from app.jobs.errors import PermanentJobError, TransientJobError

PREFIX = "piq:faults:season:"


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().cache_url, socket_timeout=1)


def _config(season: int) -> dict[str, Any]:
    raw = cast(bytes | None, _client().get(f"{PREFIX}{season}"))
    return json.loads(raw) if raw else {}


def on_attempt_start(season: int) -> None:
    if not get_settings().enable_fault_injection:
        return
    if _config(season).get("transient_failures"):
        remaining = cast(int, _client().decr(f"{PREFIX}{season}:transient_remaining"))
        if remaining >= 0:
            raise TransientJobError(f"injected transient failure ({remaining} left)")


def on_chunk(season: int, chunk_number: int) -> None:
    if not get_settings().enable_fault_injection:
        return
    config = _config(season)
    if config.get("sleep_per_chunk"):
        time.sleep(float(config["sleep_per_chunk"]))
    fail_after = config.get("fail_after_chunks")
    if fail_after is not None and chunk_number >= int(fail_after):
        raise PermanentJobError(f"injected permanent failure after chunk {chunk_number}")


def set_faults(season: int, **config: Any) -> None:
    client = _client()
    client.set(f"{PREFIX}{season}", json.dumps(config))
    client.set(f"{PREFIX}{season}:transient_remaining", int(config.get("transient_failures", 0)))


def clear_faults() -> None:
    client = _client()
    for key in client.scan_iter(f"{PREFIX}*"):
        client.delete(key)

from pydantic import BaseModel

from app.cache import AnalyticsCache, CacheStatus, cache_key, params_digest


class Payload(BaseModel):
    value: int


def test_key_is_deterministic_and_order_independent() -> None:
    a = cache_key("team-comparison", 2024, "a" * 64, 3, {"team_a": 1, "team_b": 2, "down": [3, 4]})
    b = cache_key("team-comparison", 2024, "a" * 64, 3, {"down": [3, 4], "team_b": 2, "team_a": 1})
    assert a == b
    assert a.startswith("piq:cache:v1:team-comparison:s2024:daaaaaaaaaaaaaaaa:g3:")


def test_key_changes_with_every_component() -> None:
    params = {"team_a": 1, "team_b": 2}
    base = cache_key("team-comparison", 2024, "a" * 64, 0, params)
    assert base != cache_key("team-stats", 2024, "a" * 64, 0, params)
    assert base != cache_key("team-comparison", 2023, "a" * 64, 0, params)
    assert base != cache_key("team-comparison", 2024, "b" * 64, 0, params)
    assert base != cache_key("team-comparison", 2024, "a" * 64, 1, params)
    assert base != cache_key("team-comparison", 2024, "a" * 64, 0, {"team_a": 2, "team_b": 1})


def test_digest_handles_none_and_nested() -> None:
    assert params_digest({"a": None, "b": {"c": 1}}) == params_digest({"b": {"c": 1}, "a": None})


def test_degrades_when_redis_is_unreachable() -> None:
    cache = AnalyticsCache(
        "redis://127.0.0.1:1/0", ttl_seconds=60, socket_timeout=0.1, retry_after_seconds=30
    )
    calls = 0

    def compute() -> Payload:
        nonlocal calls
        calls += 1
        return Payload(value=42)

    kwargs = {"namespace": "t", "season": 2024, "dataset_sha": "x" * 64, "params": {}}
    value, status = cache.get_or_compute(**kwargs, model=Payload, compute=compute)  # type: ignore[arg-type]
    assert (value.value, status) == (42, CacheStatus.DEGRADED)
    # Within the back-off window Redis is not contacted again, but requests still succeed.
    value, status = cache.get_or_compute(**kwargs, model=Payload, compute=compute)  # type: ignore[arg-type]
    assert status == CacheStatus.DEGRADED
    assert calls == 2
    assert cache.local_errors == 1
    assert cache.invalidate_season(2024) is False
    assert cache.stats()["available"] is False


def test_disabled_cache_always_computes() -> None:
    cache = AnalyticsCache(
        "redis://127.0.0.1:1/0",
        ttl_seconds=60,
        socket_timeout=0.1,
        retry_after_seconds=30,
        enabled=False,
    )
    _, status = cache.get_or_compute(
        namespace="t",
        season=2024,
        dataset_sha="x",
        params={},
        model=Payload,
        compute=lambda: Payload(value=1),
    )
    assert status == CacheStatus.DISABLED

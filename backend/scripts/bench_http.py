"""Measure HTTP latency and RPS for hot analytics endpoints."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import time
from typing import Any

import httpx

from scripts.bench_common import (
    capture_env,
    env_dict,
    percentiles,
    play_count,
    run_id,
    write_json,
)

ENDPOINTS = [
    (
        "team_comparison",
        "/api/v1/analytics/team-comparison",
        {"team_a": "KC", "team_b": "PHI", "season": 2024},
    ),
    (
        "situational",
        "/api/v1/analytics/situational",
        {"team": "DET", "season": 2024, "group_by": "down"},
    ),
    (
        "efficiency",
        "/api/v1/analytics/efficiency",
        {"team": "DET", "season": 2024},
    ),
]


def _one(client: httpx.Client, path: str, params: dict[str, Any]) -> tuple[float, int, str | None]:
    start = time.perf_counter()
    cache = None
    try:
        r = client.get(path, params=params)
        cache = r.headers.get("X-Cache")
        return time.perf_counter() - start, r.status_code, cache
    except httpx.HTTPError:
        return time.perf_counter() - start, 0, cache


def _collect_samples(
    client: httpx.Client, path: str, params: dict[str, Any], deadline: float
) -> list[tuple[float, int, str | None]]:
    samples: list[tuple[float, int, str | None]] = []
    while time.monotonic() < deadline:
        samples.append(_one(client, path, params))
    return samples


def _run_load(
    client: httpx.Client,
    path: str,
    params: dict[str, Any],
    *,
    concurrency: int,
    duration_seconds: int,
) -> tuple[list[float], int, int, int]:
    deadline = time.monotonic() + duration_seconds

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        chunks = list(
            pool.map(
                lambda _: _collect_samples(client, path, params, deadline),
                range(concurrency),
            )
        )

    latencies: list[float] = []
    cache_hits = 0
    cache_misses = 0
    errors = 0
    for chunk in chunks:
        for elapsed, status, cache in chunk:
            latencies.append(elapsed)
            if status >= 400 or status == 0:
                errors += 1
            elif cache == "HIT":
                cache_hits += 1
            elif cache == "MISS":
                cache_misses += 1
    return latencies, errors, cache_hits, cache_misses


def run(
    base: str,
    *,
    concurrency: int,
    duration_seconds: int,
    warmup_seconds: int,
    season: int,
) -> dict[str, Any]:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    env = capture_env(database_url, [season])
    plays = play_count(database_url, season)

    results: dict[str, Any] = {
        "run_id": run_id(),
        "kind": "http",
        "base_url": base,
        "concurrency": concurrency,
        "warmup_seconds": warmup_seconds,
        "duration_seconds": duration_seconds,
        "dataset": {"season": season, "plays": plays},
        "environment": env_dict(env),
        "endpoints": {},
    }

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    with httpx.Client(base_url=base, timeout=30.0, limits=limits) as client:
        for name, path, params in ENDPOINTS:
            # Warmup (fills analytics cache).
            warm_deadline = time.monotonic() + warmup_seconds
            while time.monotonic() < warm_deadline:
                _one(client, path, params)

            load_start = time.monotonic()
            latencies, errors, cache_hits, cache_misses = _run_load(
                client, path, params, concurrency=concurrency, duration_seconds=duration_seconds
            )
            elapsed = max(time.monotonic() - load_start, 1e-9)
            total = len(latencies)
            results["endpoints"][name] = {
                "path": path,
                "requests": total,
                "errors": errors,
                "rps": round(total / elapsed, 3),
                "latency_seconds": percentiles(latencies),
                "cache": {
                    "hits": cache_hits,
                    "misses": cache_misses,
                    "hit_rate": round(cache_hits / max(cache_hits + cache_misses, 1), 4),
                },
            }

    out = write_json("http.json", results)
    print(f"wrote {out}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8317")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=15)
    parser.add_argument("--season", type=int, default=2024)
    args = parser.parse_args()
    run(
        args.base.rstrip("/"),
        concurrency=args.concurrency,
        duration_seconds=args.duration,
        warmup_seconds=args.warmup,
        season=args.season,
    )


if __name__ == "__main__":
    main()

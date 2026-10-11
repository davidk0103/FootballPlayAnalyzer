"""Shared helpers for benchmark scripts: environment capture, percentiles, JSON output."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def results_dir() -> Path:
    path = repo_root() / "benchmarks" / "results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_id() -> str:
    return os.environ.get("BENCH_RUN_ID") or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def write_json(name: str, payload: dict[str, Any]) -> Path:
    out = results_dir() / run_id() / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return out


def percentiles(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
    ordered = sorted(samples)
    n = len(ordered)

    def pick(p: float) -> float:
        idx = min(n - 1, max(0, round(p * (n - 1))))
        return ordered[idx]

    return {
        "count": n,
        "min": round(ordered[0], 6),
        "p50": round(pick(0.50), 6),
        "p95": round(pick(0.95), 6),
        "p99": round(pick(0.99), 6),
        "max": round(ordered[-1], 6),
    }


@dataclass
class EnvSnapshot:
    captured_at: str
    python: str
    platform: str
    cpu_count: int
    load_avg: list[float] | None
    memory_mb: int | None
    database_url_host: str
    sqlalchemy: str
    httpx: str
    locust: str | None
    worker_concurrency: str
    seasons: list[int]


def capture_env(database_url: str, seasons: list[int]) -> EnvSnapshot:
    mem_mb: int | None = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_mb = int(line.split()[1]) // 1024
                    break
    except OSError:
        pass
    load: list[float] | None = None
    with contextlib.suppress(AttributeError, OSError):
        load = list(os.getloadavg())
    locust_ver: str | None = None
    try:
        import locust

        locust_ver = locust.__version__
    except ImportError:
        pass
    host = database_url.split("@")[-1] if "@" in database_url else database_url
    return EnvSnapshot(
        captured_at=datetime.now(UTC).isoformat(),
        python=sys.version.split()[0],
        platform=platform.platform(),
        cpu_count=os.cpu_count() or 0,
        load_avg=load,
        memory_mb=mem_mb,
        database_url_host=host,
        sqlalchemy=sqlalchemy.__version__,
        httpx=httpx.__version__,
        locust=locust_ver,
        worker_concurrency=os.environ.get("WORKER_CONCURRENCY", "2"),
        seasons=seasons,
    )


def play_count(database_url: str, season: int) -> int:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM plays WHERE season = :s"), {"s": season}
            ).scalar_one()
        )


def docker_worker_scale(workers: int) -> None:
    root = repo_root()
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "--scale", f"worker={workers}", "worker"],
        cwd=root,
        check=True,
    )


def wait_http_ready(base: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/health/ready", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"API not ready at {base}")


def env_dict(snapshot: EnvSnapshot) -> dict[str, Any]:
    return asdict(snapshot)

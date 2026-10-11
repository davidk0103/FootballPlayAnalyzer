"""Scale Celery worker containers and measure throughput with concurrent import jobs.

Each scale step submits the same batch of import jobs at once (one distinct season per job)
so worker processes can run in parallel. A single job per step leaves extra containers idle.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.jobs.state import JobStatus
from app.models import Job
from scripts.bench_common import (
    capture_env,
    docker_worker_scale,
    env_dict,
    percentiles,
    play_count,
    run_id,
    write_json,
)

DEFAULT_SEASONS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]


def _login(base: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=base, timeout=120.0)
    client.post(
        "/api/v1/auth/login",
        headers={"X-PlaybookIQ-CSRF": "1"},
        json={"email": email, "password": password},
    ).raise_for_status()
    return client


def _wait_batch(
    engine: Engine,
    submitted: list[tuple[uuid.UUID, float, int]],
    timeout: float,
) -> dict[str, Any]:
    """Wait until every job is terminal; record queue wait and total duration per job."""
    deadline = time.monotonic() + timeout
    tracking: dict[uuid.UUID, dict[str, Any]] = {
        job_id: {"queued_at": queued_at, "season": season, "wait": None, "total": None}
        for job_id, queued_at, season in submitted
    }
    peak_running = 0
    terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}

    while time.monotonic() < deadline:
        running = 0
        finished = 0
        now = time.monotonic()
        with Session(engine) as session:
            for job_id, meta in tracking.items():
                row = session.execute(select(Job.status).where(Job.id == job_id)).one()
                if row.status == JobStatus.RUNNING:
                    running += 1
                    if meta["wait"] is None:
                        meta["wait"] = now - meta["queued_at"]
                if row.status in terminal:
                    finished += 1
                    if meta["total"] is None:
                        meta["total"] = now - meta["queued_at"]
        peak_running = max(peak_running, running)
        if finished >= len(submitted):
            break
        time.sleep(0.5)

    waits = [float(m["wait"] or 0.0) for m in tracking.values()]
    totals = [float(m["total"] or 0.0) for m in tracking.values()]
    outcomes: dict[str, int] = {}
    with Session(engine) as session:
        for job_id in tracking:
            status = session.execute(select(Job.status).where(Job.id == job_id)).scalar_one()
            outcomes[status.value] = outcomes.get(status.value, 0) + 1

    return {
        "peak_concurrent_running": peak_running,
        "queue_wait_seconds": percentiles(waits),
        "per_job_total_seconds": percentiles(totals),
        "outcomes": outcomes,
        "per_job_totals": totals,
    }


def run_scale(
    base: str,
    *,
    worker_counts: list[int],
    seasons: list[int],
    admin_email: str,
    admin_password: str,
    job_timeout: float,
) -> dict[str, Any]:
    if len(seasons) < 2:
        raise SystemExit("need at least two distinct seasons for parallel imports")

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    concurrency = int(os.environ.get("WORKER_CONCURRENCY", "2"))
    env = capture_env(database_url, seasons)
    engine = create_engine(database_url)
    rows: list[dict[str, Any]] = []
    job_count = len(seasons)
    client = _login(base, admin_email, admin_password)

    for workers in worker_counts:
        docker_worker_scale(workers)
        time.sleep(8)
        submitted: list[tuple[uuid.UUID, float, int]] = []
        batch_start = time.monotonic()
        for season in seasons:
            queued_at = time.monotonic()
            r = client.post(
                "/api/v1/jobs/import",
                headers={"X-PlaybookIQ-CSRF": "1", "Idempotency-Key": str(uuid.uuid4())},
                json={"season": season, "force": True},
            )
            r.raise_for_status()
            submitted.append((uuid.UUID(r.json()["id"]), queued_at, season))

        stats = _wait_batch(engine, submitted, timeout=job_timeout)
        wall = time.monotonic() - batch_start
        rows.append(
            {
                "worker_containers": workers,
                "worker_processes_max": workers * concurrency,
                "jobs_submitted": job_count,
                "seasons": seasons,
                "submit_mode": "parallel_batch",
                "wall_seconds": round(wall, 3),
                "jobs_per_minute": round(job_count / max(wall / 60, 1e-9), 3),
                "mean_per_job_seconds": round(statistics.mean(stats["per_job_totals"]), 3)
                if stats["per_job_totals"]
                else 0.0,
                **{k: v for k, v in stats.items() if k != "per_job_totals"},
            }
        )

    payload = {
        "run_id": run_id(),
        "kind": "worker_scaling_parallel",
        "base_url": base,
        "worker_concurrency_per_container": concurrency,
        "jobs_per_scale_step": job_count,
        "job_timeout_seconds": job_timeout,
        "plays_per_season_before": {str(s): play_count(database_url, s) for s in seasons},
        "environment": env_dict(env),
        "runs": rows,
    }
    out = write_json("workers.json", payload)
    print(f"wrote {out}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8317")
    parser.add_argument("--workers", default="1,2,4,8")
    parser.add_argument(
        "--seasons",
        default=",".join(str(s) for s in DEFAULT_SEASONS),
        help="Distinct seasons, one job each (submitted in one batch)",
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="Max wait per batch (seconds)")
    parser.add_argument(
        "--email", default=os.environ.get("BENCH_ADMIN_EMAIL", "admin@playbookiq.test")
    )
    parser.add_argument(
        "--password", default=os.environ.get("BENCH_ADMIN_PASSWORD", "e2e-admin-password")
    )
    args = parser.parse_args()
    counts = [int(x) for x in args.workers.split(",") if x.strip()]
    seasons = [int(x) for x in args.seasons.split(",") if x.strip()]
    run_scale(
        args.base.rstrip("/"),
        worker_counts=counts,
        seasons=seasons,
        admin_email=args.email,
        admin_password=args.password,
        job_timeout=args.timeout,
    )


if __name__ == "__main__":
    main()

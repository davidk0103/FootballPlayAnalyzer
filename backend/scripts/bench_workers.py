"""Scale Celery workers (1/2/4/8 containers) and measure parallel import throughput."""

from __future__ import annotations

import argparse
import os
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
    play_count,
    run_id,
    write_json,
)


def _login(base: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=base, timeout=60.0)
    client.post(
        "/api/v1/auth/login",
        headers={"X-PlaybookIQ-CSRF": "1"},
        json={"email": email, "password": password},
    ).raise_for_status()
    return client


def _wait_jobs(engine: Engine, job_ids: list[uuid.UUID], timeout: float = 900.0) -> list[float]:
    deadline = time.monotonic() + timeout
    done: dict[uuid.UUID, float] = {}
    queued_at = time.monotonic()
    while len(done) < len(job_ids) and time.monotonic() < deadline:
        time.sleep(1.0)
        with Session(engine) as session:
            for job_id in job_ids:
                if job_id in done:
                    continue
                row = session.execute(select(Job.status).where(Job.id == job_id)).one_or_none()
                if row and row.status in (
                    JobStatus.SUCCEEDED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ):
                    done[job_id] = time.monotonic() - queued_at
    return [done[j] for j in job_ids if j in done]


def run_scale(
    base: str,
    *,
    worker_counts: list[int],
    seasons: list[int],
    admin_email: str,
    admin_password: str,
) -> dict[str, Any]:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    env = capture_env(database_url, seasons)
    engine = create_engine(database_url)
    rows: list[dict[str, Any]] = []

    for workers in worker_counts:
        docker_worker_scale(workers)
        time.sleep(5)
        client = _login(base, admin_email, admin_password)
        job_ids: list[uuid.UUID] = []
        t0 = time.monotonic()
        for season in seasons:
            r = client.post(
                "/api/v1/jobs/import",
                headers={"X-PlaybookIQ-CSRF": "1", "Idempotency-Key": str(uuid.uuid4())},
                json={"season": season, "force": True},
            )
            r.raise_for_status()
            job_ids.append(uuid.UUID(r.json()["id"]))
        durations = _wait_jobs(engine, job_ids)
        wall = time.monotonic() - t0
        rows.append(
            {
                "worker_containers": workers,
                "jobs": len(job_ids),
                "wall_seconds": round(wall, 3),
                "jobs_per_minute": round(len(job_ids) / max(wall / 60, 1e-9), 3),
                "per_job_seconds": durations,
            }
        )

    payload = {
        "run_id": run_id(),
        "kind": "worker_scaling",
        "base_url": base,
        "worker_concurrency_per_container": int(os.environ.get("WORKER_CONCURRENCY", "2")),
        "seasons": seasons,
        "plays_per_season": {str(s): play_count(database_url, s) for s in seasons},
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
    parser.add_argument("--seasons", default="2023,2024")
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
    )


if __name__ == "__main__":
    main()

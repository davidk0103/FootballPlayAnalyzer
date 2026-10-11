"""Measure season-import job throughput and queue wait time."""

from __future__ import annotations

import argparse
import os
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.jobs.state import JobStatus
from app.models import Job
from scripts.bench_common import capture_env, env_dict, percentiles, play_count, run_id, write_json


def _admin_session(base: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=base, timeout=30.0)
    r = client.post(
        "/api/v1/auth/login",
        headers={"X-PlaybookIQ-CSRF": "1"},
        json={"email": email, "password": password},
    )
    r.raise_for_status()
    return client


def run(
    base: str,
    *,
    season: int,
    jobs: int,
    admin_email: str,
    admin_password: str,
    force: bool,
) -> dict[str, Any]:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://playbookiq:playbookiq@localhost:5433/playbookiq"
    )
    env = capture_env(database_url, [season])
    plays_before = play_count(database_url, season)

    client = _admin_session(base, admin_email, admin_password)
    durations: list[float] = []
    waits: list[float] = []
    outcomes: dict[str, int] = {}
    engine = create_engine(database_url)

    for _ in range(jobs):
        key = str(uuid.uuid4())
        queued_at = time.perf_counter()
        r = client.post(
            "/api/v1/jobs/import",
            headers={"X-PlaybookIQ-CSRF": "1", "Idempotency-Key": key},
            json={"season": season, "force": force},
        )
        r.raise_for_status()
        job_id = uuid.UUID(r.json()["id"])
        started_running: float | None = None
        finished: float | None = None
        while finished is None:
            time.sleep(0.5)
            with Session(engine) as session:
                row = session.execute(
                    select(Job.status, Job.started_at, Job.finished_at).where(Job.id == job_id)
                ).one()
            status = row.status
            if status == JobStatus.RUNNING and started_running is None:
                started_running = time.monotonic()
                waits.append(started_running - queued_at)
            if status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
                finished = time.monotonic()
                durations.append(finished - queued_at)
                outcomes[status.value] = outcomes.get(status.value, 0) + 1

    plays_after = play_count(database_url, season)
    payload = {
        "run_id": run_id(),
        "kind": "jobs",
        "base_url": base,
        "season": season,
        "jobs_submitted": jobs,
        "force": force,
        "plays_before": plays_before,
        "plays_after": plays_after,
        "environment": env_dict(env),
        "outcomes": outcomes,
        "queue_wait_seconds": percentiles(waits),
        "total_duration_seconds": percentiles(durations),
        "throughput_jobs_per_minute": round(
            jobs / max(sum(durations) / len(durations), 1e-9) * 60, 3
        )
        if durations
        else 0.0,
    }
    out = write_json("jobs.json", payload)
    print(f"wrote {out}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8317")
    parser.add_argument("--season", type=int, default=2023)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument(
        "--email", default=os.environ.get("BENCH_ADMIN_EMAIL", "admin@playbookiq.test")
    )
    parser.add_argument(
        "--password", default=os.environ.get("BENCH_ADMIN_PASSWORD", "e2e-admin-password")
    )
    parser.add_argument("--force", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    run(
        args.base.rstrip("/"),
        season=args.season,
        jobs=args.jobs,
        admin_email=args.email,
        admin_password=args.password,
        force=args.force,
    )


if __name__ == "__main__":
    main()

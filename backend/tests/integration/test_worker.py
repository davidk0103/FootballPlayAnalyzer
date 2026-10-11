"""End-to-end job execution with a real Celery worker, Redis broker, and PostgreSQL.

These tests commit for real (the worker is a separate process), so every test starts
and ends with empty tables. Fault injection is enabled on the worker only.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.jobs import faults
from app.jobs.reaper import reap_stale_jobs
from app.jobs.state import AttemptStatus, JobStatus
from app.main import create_app
from app.models import Dataset, DatasetStatus, Job, JobAttempt, Play
from app.worker.tasks import _enqueue
from tests.conftest import PBP_SAMPLE, PLAYERS_SAMPLE
from tests.integration import TEST_BROKER_URL, TEST_CACHE_URL
from tests.integration.conftest import (
    BACKEND_DIR,
    CSRF,
    PASSWORD,
    TEST_DATABASE_URL,
    create_user,
)

pytestmark = [pytest.mark.integration, pytest.mark.worker]

SEASON = 2023
FIXTURE_PLAYS = 309  # stored plays in the fixture (see test_ingest)
WORKER_ENV = {
    "INGEST_CHUNK_SIZE": "50",
    "JOB_RETRY_BASE_SECONDS": "0.2",
    "JOB_RETRY_MAX_SECONDS": "1",
    "JOB_HEARTBEAT_SECONDS": "0.5",
    "JOB_STALE_AFTER_SECONDS": "3",
    "ENABLE_FAULT_INJECTION": "true",
}


class Worker:
    def __init__(self, cache_dir: Path, log_path: Path) -> None:
        self.cache_dir = cache_dir
        self.log_path = log_path
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        env = {
            **os.environ,
            **WORKER_ENV,
            "DATABASE_URL": TEST_DATABASE_URL,
            "BROKER_URL": TEST_BROKER_URL,
            "CACHE_URL": TEST_CACHE_URL,
            "DATA_CACHE_DIR": str(self.cache_dir),
        }
        log = self.log_path.open("ab")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.worker.celery_app",
                "worker",
                "--pool=prefork",
                "--concurrency=2",
                "--loglevel=INFO",
                "-n",
                f"test-{uuid.uuid4().hex[:6]}@%h",
            ],
            cwd=BACKEND_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # own process group, so we can kill parent + children
        )
        wait_for(lambda: b"ready." in self.log_path.read_bytes(), timeout=30, what="worker ready")

    def kill_all(self) -> None:
        """Simulate a container being killed: SIGKILL the whole process group."""
        assert self.proc is not None
        os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc.wait(timeout=10)
        self.proc = None

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.send_signal(signal.SIGTERM)  # warm shutdown
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=10)
        self.proc = None

    def logs(self) -> str:
        return self.log_path.read_text(errors="replace")[-6000:]


def wait_for(predicate: Callable[[], Any], *, timeout: float, what: str) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture(scope="module")
def worker_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cache = tmp_path_factory.mktemp("worker-cache")
    shutil.copy(PBP_SAMPLE, cache / f"play_by_play_{SEASON}.parquet")
    shutil.copy(PLAYERS_SAMPLE, cache / "players.parquet")
    (cache / "pbp_timestamp.json").write_text('{"last_updated": "fixture"}')
    return cache


@pytest.fixture(scope="module")
def worker(
    engine: Engine, worker_cache_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Worker]:
    redis.Redis.from_url(TEST_BROKER_URL).flushdb()
    w = Worker(worker_cache_dir, tmp_path_factory.mktemp("logs") / "worker.log")
    w.start()
    yield w
    w.stop()


def truncate(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE job_attempts, jobs, api_usage, users, rejected_rows, plays, players,"
                " games, teams, datasets RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db(engine: Engine, worker: Worker) -> Iterator[Session]:
    truncate(engine)
    redis.Redis.from_url(TEST_BROKER_URL).flushdb()
    with Session(engine) as session:
        yield session
    truncate(engine)


@pytest.fixture
def api(db: Session) -> Iterator[TestClient]:
    # Real app, session factory, and enqueue: the worker picks up the jobs.
    create_user(db, "admin@example.com", admin=True)
    with TestClient(create_app(), headers=CSRF) as c:
        login = c.post(
            "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        yield c


def job_row(db: Session, job_id: str) -> Job:
    db.expire_all()
    job = db.get(Job, uuid.UUID(job_id))
    assert job is not None
    return job


def attempts(db: Session, job_id: str) -> list[tuple[int, AttemptStatus]]:
    db.expire_all()
    rows = db.execute(
        select(JobAttempt.attempt_number, JobAttempt.status)
        .where(JobAttempt.job_id == uuid.UUID(job_id))
        .order_by(JobAttempt.attempt_number)
    ).all()
    return [(n, s) for n, s in rows]


def wait_status(
    db: Session, job_id: str, statuses: set[JobStatus], worker: Worker, timeout: float = 30
) -> Job:
    try:
        wait_for(
            lambda: job_row(db, job_id).status in statuses, timeout=timeout, what=str(statuses)
        )
    except AssertionError:
        job = job_row(db, job_id)
        pytest.fail(f"job {job_id} stuck in {job.status} ({job.error})\n{worker.logs()}")
    return job_row(db, job_id)


def submit(api: TestClient, **body: Any) -> str:
    resp = api.post("/api/v1/jobs/import", json={"season": SEASON, **body})
    assert resp.status_code == 202, resp.text
    return str(resp.json()["id"])


def play_count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Play)) or 0


def test_import_succeeds(api: TestClient, db: Session, worker: Worker) -> None:
    job_id = submit(api)
    job = wait_status(db, job_id, {JobStatus.SUCCEEDED}, worker)
    assert job.result_ref is not None
    assert job.result_ref["status"] == "imported"
    assert job.result_ref["stored"] == FIXTURE_PLAYS
    assert job.attempt_count == 1
    assert attempts(db, job_id) == [(1, AttemptStatus.SUCCEEDED)]
    assert play_count(db) == FIXTURE_PLAYS

    body = api.get(f"/api/v1/jobs/{job_id}/attempts").json()
    assert body[0]["worker"]
    # A second import of the same file is a successful no-op (checksum idempotency).
    again = submit(api)
    job = wait_status(db, again, {JobStatus.SUCCEEDED}, worker)
    assert job.result_ref and job.result_ref["status"] == "skipped_duplicate"
    assert play_count(db) == FIXTURE_PLAYS


def test_retries_after_transient_failure(api: TestClient, db: Session, worker: Worker) -> None:
    faults.set_faults(SEASON, transient_failures=2)
    job_id = submit(api)
    job = wait_status(db, job_id, {JobStatus.SUCCEEDED, JobStatus.FAILED}, worker)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert job.attempt_count == 3
    assert attempts(db, job_id) == [
        (1, AttemptStatus.FAILED),
        (2, AttemptStatus.FAILED),
        (3, AttemptStatus.SUCCEEDED),
    ]
    rows = api.get(f"/api/v1/jobs/{job_id}/attempts").json()
    assert rows[0]["error_type"] == "TransientJobError"
    assert 0 < rows[0]["retry_delay_seconds"] <= rows[1]["retry_delay_seconds"] * 2 + 0.2


def test_gives_up_after_max_attempts(api: TestClient, db: Session, worker: Worker) -> None:
    faults.set_faults(SEASON, transient_failures=10)
    job_id = submit(api)
    job = wait_status(db, job_id, {JobStatus.FAILED}, worker)
    # The limit is stamped on the job at submission (API settings), not read by the worker.
    assert job.attempt_count == job.max_attempts
    assert job.error and job.error.startswith(f"gave up after {job.max_attempts} attempts")
    assert [s for _, s in attempts(db, job_id)] == [AttemptStatus.FAILED] * job.max_attempts


def test_permanent_failure_rolls_back_the_whole_import(
    api: TestClient, db: Session, worker: Worker
) -> None:
    faults.set_faults(SEASON, fail_after_chunks=3)
    job_id = submit(api)
    job = wait_status(db, job_id, {JobStatus.FAILED}, worker)
    assert job.attempt_count == 1, "permanent errors are not retried"
    assert job.error and "injected permanent failure" in job.error
    # Three chunks (150 plays) were written before the failure; none survive.
    assert play_count(db) == 0
    db.expire_all()
    dataset = db.scalars(select(Dataset)).one()
    assert dataset.status == DatasetStatus.FAILED

    faults.clear_faults()
    retry = submit(api)
    assert wait_status(db, retry, {JobStatus.SUCCEEDED}, worker).status == JobStatus.SUCCEEDED
    assert play_count(db) == FIXTURE_PLAYS


def test_cancel_running_job(api: TestClient, db: Session, worker: Worker) -> None:
    faults.set_faults(SEASON, sleep_per_chunk=0.5)
    job_id = submit(api)
    wait_status(db, job_id, {JobStatus.RUNNING}, worker)
    time.sleep(0.6)
    resp = api.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 202
    assert resp.json()["status"] == "cancel_requested"

    job = wait_status(db, job_id, {JobStatus.CANCELLED}, worker)
    assert job.finished_at is not None
    assert attempts(db, job_id) == [(1, AttemptStatus.CANCELLED)]
    assert play_count(db) == 0, "cancelled imports are rolled back"


def test_duplicate_submissions(api: TestClient, db: Session, worker: Worker) -> None:
    faults.set_faults(SEASON, sleep_per_chunk=0.2)
    headers = {"Idempotency-Key": "client-retry-1"}
    first = api.post("/api/v1/jobs/import", json={"season": SEASON}, headers=headers)
    replay = api.post("/api/v1/jobs/import", json={"season": SEASON}, headers=headers)
    other = api.post("/api/v1/jobs/import", json={"season": SEASON})
    assert first.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert other.status_code == 409

    job_id = first.json()["id"]
    # Publishing the same job twice more (at-least-once) still runs it exactly once.
    job = job_row(db, job_id)
    _enqueue(job.id, job.task_type, 0, job.timeout_seconds)
    _enqueue(job.id, job.task_type, 0, job.timeout_seconds)
    wait_status(db, job_id, {JobStatus.SUCCEEDED}, worker)
    time.sleep(1.5)
    assert attempts(db, job_id) == [(1, AttemptStatus.SUCCEEDED)]
    assert db.scalar(select(func.count()).select_from(Job)) == 1
    assert play_count(db) == FIXTURE_PLAYS


def test_worker_child_killed_mid_task_is_redelivered(
    api: TestClient, db: Session, worker: Worker
) -> None:
    faults.set_faults(SEASON, sleep_per_chunk=0.5)
    job_id = submit(api)
    wait_status(db, job_id, {JobStatus.RUNNING}, worker)
    time.sleep(1.0)
    assert play_count(db) == 0, "nothing is visible until the import commits"

    pool_pid = int(attempts_worker(db, job_id).rsplit(":", 1)[1])
    os.kill(pool_pid, signal.SIGKILL)  # e.g. the OOM killer

    # reject_on_worker_lost requeues the message; another pool process picks it up.
    faults.set_faults(SEASON)
    job = wait_status(db, job_id, {JobStatus.SUCCEEDED}, worker, timeout=60)
    assert attempts(db, job_id) == [(1, AttemptStatus.LOST), (2, AttemptStatus.SUCCEEDED)]
    assert job.attempt_count == 2
    assert play_count(db) == FIXTURE_PLAYS


def test_whole_worker_killed_then_recovered_by_reaper(
    api: TestClient, db: Session, worker: Worker
) -> None:
    faults.set_faults(SEASON, sleep_per_chunk=0.5)
    job_id = submit(api)
    wait_status(db, job_id, {JobStatus.RUNNING}, worker)
    time.sleep(1.0)
    worker.kill_all()  # parent and children gone; the message stays unacked in Redis

    faults.set_faults(SEASON)
    assert job_row(db, job_id).status == JobStatus.RUNNING
    # Heartbeats stop; once stale (3s in tests) the reaper sees a free lease and recovers.
    assert reap_stale_jobs(_enqueue, stale_after_seconds=3).lost == []
    time.sleep(3.5)
    report = reap_stale_jobs(_enqueue, stale_after_seconds=3)
    assert report.lost == [job_id]
    assert job_row(db, job_id).status == JobStatus.RETRYING

    worker.start()
    job = wait_status(db, job_id, {JobStatus.SUCCEEDED}, worker, timeout=60)
    assert attempts(db, job_id) == [(1, AttemptStatus.LOST), (2, AttemptStatus.SUCCEEDED)]
    assert job.attempt_count == 2
    assert play_count(db) == FIXTURE_PLAYS


def test_reaper_fails_poison_job_whose_worker_always_dies(db: Session, worker: Worker) -> None:
    job = Job(
        id=uuid.uuid4(),
        task_type="import_season",
        target_key=f"season:{SEASON}",
        params={"season": SEASON, "force": False},
        status=JobStatus.RUNNING,
        idempotency_key="poison",
        request_fingerprint="x",
        attempt_count=3,
        max_attempts=3,
        timeout_seconds=60,
    )
    db.add(job)
    db.flush()
    db.add(JobAttempt(job_id=job.id, attempt_number=3, status=AttemptStatus.RUNNING))
    db.execute(
        text("UPDATE jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": job.id},
    )
    db.commit()

    assert reap_stale_jobs(_enqueue).lost == [str(job.id)]
    reaped = job_row(db, str(job.id))
    assert reaped.status == JobStatus.FAILED
    assert reaped.error and reaped.error.startswith("poison job")
    assert attempts(db, str(job.id)) == [(3, AttemptStatus.LOST)]


def test_import_invalidates_analytics_cache(api: TestClient, db: Session, worker: Worker) -> None:
    wait_status(db, submit(api), {JobStatus.SUCCEEDED}, worker)
    url = f"/api/v1/analytics/team-comparison?team_a=DET&team_b=KC&season={SEASON}"
    assert api.get(url).headers["X-Cache"] == "MISS"
    assert api.get(url).headers["X-Cache"] == "HIT"

    wait_status(db, submit(api, force=True), {JobStatus.SUCCEEDED}, worker)
    assert api.get(url).headers["X-Cache"] == "MISS"
    assert api.get(url).headers["X-Cache"] == "HIT"
    assert get_cache().stats()["invalidations"] == 2


def attempts_worker(db: Session, job_id: str) -> str:
    db.expire_all()
    name = db.scalar(
        select(JobAttempt.worker)
        .where(JobAttempt.job_id == uuid.UUID(job_id))
        .order_by(JobAttempt.attempt_number.desc())
        .limit(1)
    )
    assert name
    return name

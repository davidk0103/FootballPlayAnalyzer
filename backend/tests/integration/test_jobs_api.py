"""Jobs API and analytics cache behavior against real PostgreSQL + Redis (no worker)."""

import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_enqueue
from app.cache import AnalyticsCache, get_cache
from app.db import get_session
from app.main import create_app

pytestmark = pytest.mark.integration

COMPARE = "/api/v1/analytics/team-comparison?team_a=DET&team_b=KC&season=2023"


class FakeQueue:
    def __init__(self) -> None:
        self.published: list[uuid.UUID] = []
        self.fail = False

    def __call__(self, job_id: uuid.UUID, timeout_seconds: int) -> str:
        if self.fail:
            raise ConnectionError("broker down")
        self.published.append(job_id)
        return f"task-{len(self.published)}"


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


def _app(
    session: Session, queue: FakeQueue, cache: AnalyticsCache | None = None
) -> httpx.AsyncClient:
    app = create_app()

    def override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_enqueue] = lambda: queue
    if cache is not None:
        app.dependency_overrides[get_cache] = lambda: cache
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(db_session: Session, queue: FakeQueue) -> AsyncIterator[httpx.AsyncClient]:
    async with _app(db_session, queue) as c:
        yield c


@pytest.fixture
async def seeded(seeded_session: Session, queue: FakeQueue) -> AsyncIterator[httpx.AsyncClient]:
    async with _app(seeded_session, queue) as c:
        yield c


async def test_submit_returns_queued_job_and_publishes(
    client: httpx.AsyncClient, queue: FakeQueue
) -> None:
    resp = await client.post("/api/v1/jobs/import", json={"season": 2024})
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "queued"
    assert job["params"] == {"season": 2024, "force": False}
    assert job["attempt_count"] == 0
    assert job["user_id"] is None
    assert queue.published == [uuid.UUID(job["id"])]

    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.json()["id"] == job["id"]
    assert (await client.get(f"/api/v1/jobs/{job['id']}/attempts")).json() == []


async def test_idempotency_key_replays_original_job(
    client: httpx.AsyncClient, queue: FakeQueue
) -> None:
    headers = {"Idempotency-Key": "import-2024-abc"}
    first = await client.post("/api/v1/jobs/import", json={"season": 2024}, headers=headers)
    second = await client.post("/api/v1/jobs/import", json={"season": 2024}, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert len(queue.published) == 1

    body_key = await client.post(
        "/api/v1/jobs/import", json={"season": 2024, "idempotency_key": "import-2024-abc"}
    )
    assert body_key.json()["id"] == first.json()["id"]


async def test_idempotency_key_reuse_with_other_params_conflicts(client: httpx.AsyncClient) -> None:
    headers = {"Idempotency-Key": "k1"}
    await client.post("/api/v1/jobs/import", json={"season": 2024}, headers=headers)
    resp = await client.post(
        "/api/v1/jobs/import", json={"season": 2024, "force": True}, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_key_reused"


async def test_duplicate_active_submission_is_rejected(client: httpx.AsyncClient) -> None:
    first = await client.post("/api/v1/jobs/import", json={"season": 2024})
    dup = await client.post("/api/v1/jobs/import", json={"season": 2024, "force": True})
    assert dup.status_code == 409
    err = dup.json()["error"]
    assert err["code"] == "duplicate_job"
    assert err["details"]["existing_job_id"] == first.json()["id"]

    other_season = await client.post("/api/v1/jobs/import", json={"season": 2023})
    assert other_season.status_code == 202

    # Once the first job is finished, the season can be imported again.
    await client.post(f"/api/v1/jobs/{first.json()['id']}/cancel")
    again = await client.post("/api/v1/jobs/import", json={"season": 2024})
    assert again.status_code == 202


async def test_cancel_queued_job_and_terminal_conflict(client: httpx.AsyncClient) -> None:
    job = (await client.post("/api/v1/jobs/import", json={"season": 2024})).json()
    cancelled = await client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 202
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None
    assert body["cancel_requested_at"] is not None

    again = await client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "job_finished"


async def test_publish_failure_still_accepts_job(
    client: httpx.AsyncClient, queue: FakeQueue
) -> None:
    queue.fail = True
    resp = await client.post("/api/v1/jobs/import", json={"season": 2024})
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


async def test_list_and_filter_jobs(client: httpx.AsyncClient) -> None:
    a = (await client.post("/api/v1/jobs/import", json={"season": 2023})).json()
    b = (await client.post("/api/v1/jobs/import", json={"season": 2024})).json()
    await client.post(f"/api/v1/jobs/{a['id']}/cancel")

    page = (await client.get("/api/v1/jobs")).json()
    assert page["total"] == 2
    assert {j["id"] for j in page["items"]} == {a["id"], b["id"]}
    queued = (await client.get("/api/v1/jobs?status=queued")).json()
    assert [j["id"] for j in queued["items"]] == [b["id"]]


async def test_job_errors(client: httpx.AsyncClient) -> None:
    missing = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert (await client.get("/api/v1/jobs/not-a-uuid")).status_code == 422
    bad = await client.post("/api/v1/jobs/import", json={"season": 1990})
    assert bad.status_code == 422
    assert (await client.get("/api/v1/jobs?status=bogus")).status_code == 422


async def test_cache_miss_hit_bypass_and_stats(seeded: httpx.AsyncClient) -> None:
    first = await seeded.get(COMPARE)
    second = await seeded.get(COMPARE)
    bypass = await seeded.get(COMPARE + "&no_cache=true")
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert bypass.headers["X-Cache"] == "BYPASS"
    assert first.json() == second.json() == bypass.json()

    other_filters = await seeded.get(COMPARE + "&down=3")
    assert other_filters.headers["X-Cache"] == "MISS"

    team = await seeded.get("/api/v1/teams/DET/stats?season=2023")
    assert team.headers["X-Cache"] == "MISS"
    assert (await seeded.get("/api/v1/teams/DET/stats?season=2023")).headers["X-Cache"] == "HIT"

    stats = (await seeded.get("/api/v1/cache/stats")).json()
    assert stats["hits"] == 2
    assert stats["misses"] == 3
    assert stats["bypass"] == 1
    assert stats["hit_rate"] == 0.4
    assert stats["available"] is True


async def test_invalidation_bumps_generation(seeded: httpx.AsyncClient) -> None:
    await seeded.get(COMPARE)
    assert (await seeded.get(COMPARE)).headers["X-Cache"] == "HIT"
    assert get_cache().invalidate_season(2023)
    assert (await seeded.get(COMPARE)).headers["X-Cache"] == "MISS"
    assert (await seeded.get(COMPARE)).headers["X-Cache"] == "HIT"


async def test_redis_down_serves_uncached(seeded_session: Session, queue: FakeQueue) -> None:
    dead = AnalyticsCache(
        "redis://127.0.0.1:1/0", ttl_seconds=60, socket_timeout=0.1, retry_after_seconds=30
    )
    async with _app(seeded_session, queue, cache=dead) as c:
        resp = await c.get(COMPARE)
        assert resp.status_code == 200
        assert resp.headers["X-Cache"] == "DEGRADED"
        assert resp.json()["team_a"]["team"]["abbreviation"] == "DET"
        ready = (await c.get("/health/ready")).json()
        assert ready == {"status": "ok", "database": "ok", "redis": "unavailable"}

"""Uploads: content validation, mapping, processing, ownership, and isolation from public data."""

import io
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.state import JobStatus
from app.models import Job, Play, UploadStatus, UserDataset, UserPlay
from app.storage import LocalStorage
from app.uploads.processing import process_upload
from tests.conftest import PBP_SAMPLE
from tests.integration.conftest import CSRF, api_client, create_user, sign_in
from tests.integration.test_jobs_api import FakeQueue

pytestmark = pytest.mark.integration

UPLOADS = "/api/v1/uploads"
NFLVERSE_MAPPING = {
    "game_key": "game_id",
    "offense": "posteam",
    "defense": "defteam",
    "play_type": "play_type",
    "season": "season",
    "season_type": "season_type",
    "week": "week",
    "qtr": "qtr",
    "down": "down",
    "yards_to_go": "ydstogo",
    "yard_line_100": "yardline_100",
    "score_differential": "score_differential",
    "yards_gained": "yards_gained",
    "epa": "epa",
    "success": "success",
    "complete_pass": "complete_pass",
    "sack": "sack",
    "touchdown": "touchdown",
    "interception": "interception",
    "fumble_lost": "fumble_lost",
    "first_down": "first_down",
    "first_down_penalty": "first_down_penalty",
    "penalty": "penalty",
    "third_down_converted": "third_down_converted",
    "two_point_attempt": "two_point_attempt",
}


def nflverse_csv() -> bytes:
    """The public 2023 fixture exported as a CSV, exactly as a coach might export it."""
    df = pd.read_parquet(PBP_SAMPLE)
    for col in df.columns:
        if str(df[col].dtype) in ("float64", "Float64") and col != "epa":
            df[col] = df[col].astype("Int64")
    return df.to_csv(index=False).encode()


SMALL_CSV = (
    b"game,posteam,defteam,play,down,ydstogo,yards\n"
    b"G1,AAA,BBB,pass,1,10,12\n"
    b"G1,AAA,BBB,run,2,-3,4\n"
    b"G1,AAA,AAA,run,3,6,2\n"
    b'G1,AAA,BBB,"=HYPERLINK(""http://x"")",1,10,1\n'
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
async def coach(
    db_session: Session, storage: LocalStorage, queue: FakeQueue
) -> AsyncIterator[httpx.AsyncClient]:
    create_user(db_session, "coach@example.com")
    async with api_client(db_session, storage=lambda: storage, enqueue=lambda: queue) as c:
        await sign_in(c, "coach@example.com")
        yield c


@pytest.fixture
async def rival(db_session: Session, storage: LocalStorage) -> AsyncIterator[httpx.AsyncClient]:
    create_user(db_session, "rival@example.com")
    async with api_client(db_session, storage=lambda: storage) as c:
        await sign_in(c, "rival@example.com")
        yield c


async def upload(
    client: httpx.AsyncClient, content: bytes, filename: str = "plays.csv", name: str = ""
) -> httpx.Response:
    data = {"name": name} if name else {}
    return await client.post(
        UPLOADS, files={"file": (filename, io.BytesIO(content), "text/csv")}, data=data
    )


def stored_files(storage: LocalStorage) -> list[Path]:
    root = storage.root / "uploads"
    return sorted(root.iterdir()) if root.exists() else []


def noop(stage: str, done: int, total: int) -> None:
    return None


async def ready_upload(
    client: httpx.AsyncClient, session: Session, storage: LocalStorage
) -> dict[str, object]:
    created: dict[str, object] = (
        await upload(client, nflverse_csv(), "det_kc.csv", "DET at KC")
    ).json()
    resp = await client.post(
        f"{UPLOADS}/{created['id']}/validate", json={"mapping": NFLVERSE_MAPPING}
    )
    assert resp.json()["valid"], resp.text
    owner = session.scalar(select(UserDataset.user_id).where(UserDataset.id == created["id"]))
    process_upload(session, storage, uuid.UUID(str(created["id"])), owner, noop)
    return created


async def test_upload_requires_auth_and_csrf(db_session: Session, storage: LocalStorage) -> None:
    async with api_client(db_session, storage=lambda: storage) as anon:
        assert (await upload(anon, SMALL_CSV)).status_code == 401
    create_user(db_session, "c@example.com")
    async with api_client(db_session, storage=lambda: storage) as c:
        await sign_in(c, "c@example.com")
        resp = await c.post(
            UPLOADS,
            files={"file": ("p.csv", io.BytesIO(SMALL_CSV), "text/csv")},
            headers={"X-PlaybookIQ-CSRF": ""},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "csrf_failed"
    assert stored_files(storage) == []


async def test_upload_stores_under_random_name_and_suggests_mapping(
    coach: httpx.AsyncClient, storage: LocalStorage
) -> None:
    resp = await upload(coach, SMALL_CSV, filename="../../etc/passwd.csv")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"
    assert body["original_filename"] == "passwd.csv"
    assert body["columns"] == ["game", "posteam", "defteam", "play", "down", "ydstogo", "yards"]
    assert body["row_count"] == 4
    assert body["preview"][0] == ["G1", "AAA", "BBB", "pass", "1", "10", "12"]
    assert body["suggested_mapping"] == {
        "game_key": "game",
        "offense": "posteam",
        "defense": "defteam",
        "play_type": "play",
        "down": "down",
        "yards_to_go": "ydstogo",
        "yards_gained": "yards",
    }
    files = stored_files(storage)
    assert len(files) == 1
    assert files[0].name != "passwd.csv"
    assert len(files[0].stem) == 32  # uuid4 hex


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "binary_file"),
        ("game,team\nG1,caf\u00e9\n".encode("latin-1"), "not_utf8"),
        (b"", "empty_file"),
        (b"game,team\n", "no_rows"),
        (b"game,team\nG1,A,extra\n", "ragged_rows"),
        (b"game,game\nG1,G2\n", "bad_header"),
        (b"just one column\nvalue\n", "no_delimiter"),
    ],
)
async def test_upload_rejects_invalid_content(
    coach: httpx.AsyncClient, storage: LocalStorage, content: bytes, code: str
) -> None:
    resp = await upload(coach, content)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == code
    assert stored_files(storage) == []


async def test_upload_size_limit(
    coach: httpx.AsyncClient, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "64")
    get_settings.cache_clear()
    try:
        resp = await upload(coach, SMALL_CSV * 3)
    finally:
        monkeypatch.delenv("UPLOAD_MAX_BYTES")
        get_settings.cache_clear()
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"
    assert stored_files(storage) == []


async def test_duplicate_upload_conflicts(coach: httpx.AsyncClient, storage: LocalStorage) -> None:
    first = await upload(coach, SMALL_CSV)
    second = await upload(coach, SMALL_CSV)
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "duplicate_upload"
    assert error["details"]["existing_upload_id"] == first.json()["id"]
    assert len(stored_files(storage)) == 1


async def test_validate_reports_mapping_and_row_errors(coach: httpx.AsyncClient) -> None:
    upload_id = (await upload(coach, SMALL_CSV)).json()["id"]
    url = f"{UPLOADS}/{upload_id}/validate"

    missing = (await coach.post(url, json={"mapping": {"game_key": "game"}})).json()
    assert missing["valid"] is False
    assert "Offense is required; map a column to it" in missing["mapping_errors"]
    assert (await coach.get(f"{UPLOADS}/{upload_id}")).json()["status"] == "uploaded"

    bad_column = (
        await coach.post(url, json={"mapping": {"game_key": "nope", "offense": "game"}})
    ).json()
    assert "Game ID: column 'nope' is not in the file" in bad_column["mapping_errors"]

    mapping = {
        "game_key": "game",
        "offense": "posteam",
        "defense": "defteam",
        "play_type": "play",
        "down": "down",
        "yards_to_go": "ydstogo",
        "yards_gained": "yards",
    }
    body = (await coach.post(url, json={"mapping": mapping})).json()
    assert body["valid"] is True
    assert (body["checked_rows"], body["accepted_rows"], body["rejected_rows"]) == (4, 1, 3)
    reasons = {i["row_number"]: i["reason"] for i in body["issues"]}
    assert reasons[2] == "Yards to go must be a whole number from 0 to 100 (got '-3')"
    assert reasons[3] == "Offense and defense are the same team"
    assert reasons[4].startswith("Play type must be one of")
    assert body["issues"][0]["values"]["ydstogo"] == "-3"
    assert body["upload"]["status"] == "validated"
    assert body["upload"]["mapping"] == mapping


async def test_process_requires_validation_and_is_idempotent(
    coach: httpx.AsyncClient, db_session: Session, queue: FakeQueue
) -> None:
    upload_id = (await upload(coach, nflverse_csv())).json()["id"]
    process = f"{UPLOADS}/{upload_id}/process"
    early = await coach.post(process)
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "upload_not_validated"

    await coach.post(f"{UPLOADS}/{upload_id}/validate", json={"mapping": NFLVERSE_MAPPING})
    first = await coach.post(process, headers={"Idempotency-Key": "proc-1"})
    assert first.status_code == 202, first.text
    job = first.json()
    assert job["task_type"] == "import_upload"
    assert job["params"] == {"dataset_id": upload_id}
    assert job["timeout_seconds"] == get_settings().upload_job_timeout_seconds
    assert queue.published == [uuid.UUID(job["id"])]

    replay = await coach.post(process, headers={"Idempotency-Key": "proc-1"})
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == job["id"]

    busy = await coach.post(process)
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "upload_busy"

    detail = (await coach.get(f"{UPLOADS}/{upload_id}")).json()
    assert detail["status"] == "processing"
    assert detail["job"]["id"] == job["id"]

    delete = await coach.delete(f"{UPLOADS}/{upload_id}")
    assert delete.status_code == 409
    assert delete.json()["error"]["code"] == "upload_processing"


async def test_failed_job_makes_upload_retryable(
    coach: httpx.AsyncClient, db_session: Session
) -> None:
    upload_id = (await upload(coach, nflverse_csv())).json()["id"]
    await coach.post(f"{UPLOADS}/{upload_id}/validate", json={"mapping": NFLVERSE_MAPPING})
    job_id = (await coach.post(f"{UPLOADS}/{upload_id}/process")).json()["id"]
    job = db_session.get_one(Job, uuid.UUID(job_id))
    job.status = JobStatus.FAILED
    job.error = "job exceeded its time limit"
    db_session.commit()

    detail = (await coach.get(f"{UPLOADS}/{upload_id}")).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "job exceeded its time limit"
    retry = await coach.post(f"{UPLOADS}/{upload_id}/process")
    assert retry.status_code == 202


async def test_processing_stores_rows_separately_and_matches_public_metrics(
    coach: httpx.AsyncClient, seeded_session: Session, storage: LocalStorage
) -> None:
    public_plays = seeded_session.scalar(select(func.count()).select_from(Play))
    created = await ready_upload(coach, seeded_session, storage)
    upload_id = str(created["id"])

    dataset = seeded_session.get_one(UserDataset, uuid.UUID(upload_id))
    assert dataset.status == UploadStatus.READY
    raw_rows = len(pd.read_parquet(PBP_SAMPLE))
    assert dataset.stored_count is not None and dataset.rejected_count is not None
    assert dataset.stored_count + dataset.rejected_count == raw_rows
    assert dataset.rejected_count > 0  # rows with no possession team (e.g. game start)
    assert seeded_session.scalar(select(func.count()).select_from(Play)) == public_plays
    assert (
        seeded_session.scalar(
            select(func.count()).select_from(UserPlay).where(UserPlay.dataset_id == dataset.id)
        )
        == dataset.stored_count
    )

    rejected = (await coach.get(f"{UPLOADS}/{upload_id}/rejected")).json()
    assert rejected["total"] == dataset.rejected_count
    assert "Offense is blank" in rejected["items"][0]["reason"]

    teams = (await coach.get(f"{UPLOADS}/{upload_id}/teams")).json()
    assert {t["abbreviation"] for t in teams} == {"ARI", "DET", "KC", "WAS"}

    detail = (await coach.get(f"{UPLOADS}/{upload_id}")).json()
    assert detail["seasons"] == [2023]

    query = "/api/v1/analytics/efficiency?team=DET&season=2023"
    public = (await coach.get(query)).json()
    private = (await coach.get(f"{query}&dataset_id={upload_id}")).json()
    assert private["dataset"]["kind"] == "upload"
    assert private["dataset"]["name"] == "DET at KC"
    assert public["dataset"]["kind"] == "public"
    assert [s["key"] for s in private["splits"]] == [s["key"] for s in public["splits"]]
    for pub, mine in zip(public["splits"], private["splits"], strict=True):
        assert mine["plays"] == pub["plays"] > 0
        for metric in ("epa_per_play", "success_rate", "yards_per_play"):
            assert mine["metrics"][metric] == pub["metrics"][metric], (pub["key"], metric)

    situational = await coach.get(
        f"/api/v1/analytics/situational?team=DET&group_by=down&dataset_id={upload_id}"
    )
    assert situational.status_code == 200
    assert any("uploaded dataset" in w for w in situational.json()["warnings"])


async def test_uploads_are_private_to_their_owner(
    coach: httpx.AsyncClient,
    rival: httpx.AsyncClient,
    db_session: Session,
    storage: LocalStorage,
) -> None:
    created = await ready_upload(coach, db_session, storage)
    upload_id = created["id"]
    base = f"{UPLOADS}/{upload_id}"
    for method, url in [
        ("GET", base),
        ("POST", f"{base}/validate"),
        ("POST", f"{base}/process"),
        ("DELETE", base),
        ("GET", f"{base}/teams"),
        ("GET", f"{base}/rejected"),
        ("GET", f"/api/v1/analytics/situational?team=DET&dataset_id={upload_id}"),
        ("GET", f"/api/v1/teams/DET/tendencies?dataset_id={upload_id}"),
    ]:
        kwargs = {"json": {"mapping": NFLVERSE_MAPPING}} if url.endswith("validate") else {}
        resp = await rival.request(method, url, **kwargs)  # type: ignore[arg-type]
        assert resp.status_code == 404, (method, url, resp.text)
    assert (await rival.get(UPLOADS)).json()["total"] == 0

    async with api_client(db_session, storage=lambda: storage) as anon:
        resp = await anon.get(f"/api/v1/analytics/trends?team=DET&dataset_id={upload_id}")
        assert resp.status_code == 404
    assert (await coach.get(base)).status_code == 200


async def test_analytics_on_unprocessed_upload_conflicts(coach: httpx.AsyncClient) -> None:
    upload_id = (await upload(coach, SMALL_CSV)).json()["id"]
    resp = await coach.get(f"/api/v1/analytics/efficiency?team=AAA&dataset_id={upload_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "upload_not_ready"


async def test_delete_removes_rows_and_file(
    coach: httpx.AsyncClient, db_session: Session, storage: LocalStorage
) -> None:
    created = await ready_upload(coach, db_session, storage)
    upload_id = uuid.UUID(str(created["id"]))
    assert len(stored_files(storage)) == 1
    resp = await coach.delete(f"{UPLOADS}/{upload_id}", headers=CSRF)
    assert resp.status_code == 204
    assert db_session.get(UserDataset, upload_id) is None
    assert (
        db_session.scalar(
            select(func.count()).select_from(UserPlay).where(UserPlay.dataset_id == upload_id)
        )
        == 0
    )
    assert stored_files(storage) == []
    assert (await coach.get(f"{UPLOADS}/{upload_id}")).status_code == 404


async def test_reprocessing_replaces_rows(
    coach: httpx.AsyncClient, db_session: Session, storage: LocalStorage
) -> None:
    created = await ready_upload(coach, db_session, storage)
    dataset_id = uuid.UUID(str(created["id"]))
    first = db_session.get_one(UserDataset, dataset_id).stored_count
    process_upload(
        db_session, storage, dataset_id, db_session.get_one(UserDataset, dataset_id).user_id, noop
    )
    count = db_session.scalar(
        select(func.count()).select_from(UserPlay).where(UserPlay.dataset_id == dataset_id)
    )
    assert count == first

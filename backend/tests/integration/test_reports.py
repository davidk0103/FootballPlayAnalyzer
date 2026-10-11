"""Saved reports and exports: async generation, ownership, export safety."""

import csv
import io
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReportExport, ReportStatus, SavedReport, User
from app.reports.jobs import generate_saved_report, write_export
from app.storage import LocalStorage
from tests.integration.conftest import api_client, create_user, sign_in
from tests.integration.test_jobs_api import FakeQueue
from tests.integration.test_uploads import noop, ready_upload

pytestmark = pytest.mark.integration

REPORTS = "/api/v1/reports"
EVIL_TITLE = '=HYPERLINK("http://evil.example","click")'


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
async def analyst(
    seeded_session: Session, storage: LocalStorage, queue: FakeQueue
) -> AsyncIterator[httpx.AsyncClient]:
    create_user(seeded_session, "analyst@example.com")
    async with api_client(seeded_session, storage=lambda: storage, enqueue=lambda: queue) as c:
        await sign_in(c, "analyst@example.com")
        yield c


def owner_id(session: Session, email: str) -> int:
    return session.scalars(select(User.id).where(User.email == email)).one()


async def generated(
    client: httpx.AsyncClient, session: Session, payload: dict[str, object]
) -> dict[str, Any]:
    resp = await client.post(REPORTS, json=payload)
    assert resp.status_code == 202, resp.text
    report_id = uuid.UUID(resp.json()["id"])
    generate_saved_report(session, report_id, owner_id(session, "analyst@example.com"), noop)
    body: dict[str, Any] = (await client.get(f"{REPORTS}/{report_id}")).json()
    return body


async def test_report_is_generated_by_a_job(
    analyst: httpx.AsyncClient, seeded_session: Session, queue: FakeQueue
) -> None:
    resp = await analyst.post(REPORTS, json={"team": "det", "season": 2023})
    assert resp.status_code == 202, resp.text
    pending = resp.json()
    assert pending["status"] == "pending"
    assert pending["title"] == "DET scouting report"
    assert pending["report"] is None
    assert len(queue.published) == 1

    report_id = uuid.UUID(pending["id"])
    generate_saved_report(
        seeded_session, report_id, owner_id(seeded_session, "analyst@example.com"), noop
    )
    body = (await analyst.get(f"{REPORTS}/{report_id}")).json()
    assert body["status"] == "ready"
    report = body["report"]
    assert report["team"]["abbreviation"] == "DET"
    assert report["dataset"]["kind"] == "public"
    assert report["offense"]["side"] == "offense" and report["defense"]["side"] == "defense"
    names = [m["name"] for m in report["offense"]["metrics"]]
    assert names[:3] == ["epa_per_play", "success_rate", "yards_per_play"]
    epa = report["offense"]["metrics"][0]
    assert epa["of"] == 4 and 1 <= epa["rank"] <= 4
    assert report["offense"]["plays"] > 0
    assert any("statistical significance" in x for x in report["limitations"])
    assert {p["category"] for p in report["top_players"]} == {"passing", "rushing", "receiving"}
    assert report["definitions"]["findings"].startswith("Rule-based")

    listing = (await analyst.get(REPORTS)).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == str(report_id)


async def test_report_is_deterministic(analyst: httpx.AsyncClient, seeded_session: Session) -> None:
    a = await generated(analyst, seeded_session, {"team": "KC", "season": 2023})
    b = await generated(analyst, seeded_session, {"team": "KC", "season": 2023, "title": "B"})
    strip = {"generated_at"}
    ra = {k: v for k, v in a["report"].items() if k not in strip}
    rb = {k: v for k, v in b["report"].items() if k not in strip}
    assert ra == rb


async def test_report_request_validation(analyst: httpx.AsyncClient) -> None:
    missing = await analyst.post(REPORTS, json={"team": "DET"})
    assert missing.status_code == 422
    assert "season is required" in missing.json()["error"]["message"]
    unknown = await analyst.post(REPORTS, json={"team": "ZZZ", "season": 2023})
    assert unknown.status_code == 404
    no_season = await analyst.post(REPORTS, json={"team": "DET", "season": 1999})
    assert no_season.status_code == 404


async def test_report_idempotency(analyst: httpx.AsyncClient) -> None:
    headers = {"Idempotency-Key": "r-1"}
    first = await analyst.post(REPORTS, json={"team": "DET", "season": 2023}, headers=headers)
    again = await analyst.post(REPORTS, json={"team": "DET", "season": 2023}, headers=headers)
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    other = await analyst.post(REPORTS, json={"team": "KC", "season": 2023}, headers=headers)
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "idempotency_key_reused"
    assert (await analyst.get(REPORTS)).json()["total"] == 1


async def test_reports_are_private(
    analyst: httpx.AsyncClient, seeded_session: Session, storage: LocalStorage
) -> None:
    body = await generated(analyst, seeded_session, {"team": "DET", "season": 2023})
    report_id = body["id"]
    create_user(seeded_session, "other@example.com")
    async with api_client(seeded_session, storage=lambda: storage) as other:
        await sign_in(other, "other@example.com")
        for method, url in [
            ("GET", f"{REPORTS}/{report_id}"),
            ("DELETE", f"{REPORTS}/{report_id}"),
            ("POST", f"{REPORTS}/{report_id}/exports"),
        ]:
            kwargs = {"json": {"format": "csv"}} if method == "POST" else {}
            resp = await other.request(method, url, **kwargs)  # type: ignore[arg-type]
            assert resp.status_code == 404, (method, url)
        assert (await other.get(REPORTS)).json()["total"] == 0
    async with api_client(seeded_session, storage=lambda: storage) as anon:
        assert (await anon.get(REPORTS)).status_code == 401
        assert (await anon.post(REPORTS, json={"team": "DET", "season": 2023})).status_code == 401


async def test_report_on_upload_requires_ownership(
    analyst: httpx.AsyncClient, seeded_session: Session, storage: LocalStorage
) -> None:
    upload = await ready_upload(analyst, seeded_session, storage)
    body = await generated(
        analyst, seeded_session, {"team": "DET", "dataset_id": upload["id"], "title": "Mine"}
    )
    assert body["status"] == "ready"
    report = body["report"]
    assert report["dataset"]["kind"] == "upload"
    assert report["top_players"] == []

    create_user(seeded_session, "thief@example.com")
    async with api_client(seeded_session, storage=lambda: storage) as thief:
        await sign_in(thief, "thief@example.com")
        resp = await thief.post(REPORTS, json={"team": "DET", "dataset_id": upload["id"]})
        assert resp.status_code == 404

    # Deleting the upload keeps the saved snapshot.
    assert (await analyst.delete(f"/api/v1/uploads/{upload['id']}")).status_code == 204
    kept = (await analyst.get(f"{REPORTS}/{body['id']}")).json()
    assert kept["status"] == "ready" and kept["dataset_id"] is None


async def test_csv_and_json_exports(
    analyst: httpx.AsyncClient, seeded_session: Session, storage: LocalStorage
) -> None:
    resp = await analyst.post(REPORTS, json={"team": "DET", "season": 2023, "title": EVIL_TITLE})
    report_id = resp.json()["id"]
    early = await analyst.post(f"{REPORTS}/{report_id}/exports", json={"format": "csv"})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "report_not_ready"

    owner = owner_id(seeded_session, "analyst@example.com")
    generate_saved_report(seeded_session, uuid.UUID(report_id), owner, noop)
    downloads = {}
    for fmt in ("csv", "json"):
        created = await analyst.post(f"{REPORTS}/{report_id}/exports", json={"format": fmt})
        assert created.status_code == 202, created.text
        export = created.json()
        assert export["status"] == "pending" and export["download_url"] is None
        not_ready = await analyst.get(f"{REPORTS}/{report_id}/exports/{export['id']}/download")
        assert not_ready.status_code == 409
        write_export(seeded_session, storage, uuid.UUID(export["id"]), owner)
        ready = (await analyst.get(f"{REPORTS}/{report_id}/exports/{export['id']}")).json()
        assert ready["status"] == "ready"
        dl = await analyst.get(ready["download_url"])
        assert dl.status_code == 200
        assert dl.headers["x-content-type-options"] == "nosniff"
        assert "attachment;" in dl.headers["content-disposition"]
        assert ".." not in dl.headers["content-disposition"]
        downloads[fmt] = dl

    assert downloads["csv"].headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(downloads["csv"].content.decode("utf-8-sig"))))
    assert rows[0][:5] == ["section", "side", "item", "label", "value"]
    title_row = next(r for r in rows if r[0] == "meta" and r[2] == "title")
    assert title_row[4] == "'" + EVIL_TITLE
    for row in rows[1:]:
        for cell in row:
            if cell[:1] in ("=", "+", "@"):
                pytest.fail(f"unsafe cell {cell!r}")
    epa = next(r for r in rows if r[0] == "metric" and r[1] == "offense" and r[2] == "epa_per_play")
    float(epa[4])  # numbers stay numeric

    payload = json.loads(downloads["json"].content)
    assert payload["title"] == EVIL_TITLE
    assert payload["team"]["abbreviation"] == "DET"

    detail = (await analyst.get(f"{REPORTS}/{report_id}")).json()
    assert {e["format"] for e in detail["exports"]} == {"csv", "json"}

    files = list((storage.root / "exports").iterdir())
    assert len(files) == 2
    assert (await analyst.delete(f"{REPORTS}/{report_id}")).status_code == 204
    assert list((storage.root / "exports").iterdir()) == []
    assert seeded_session.scalar(select(ReportExport)) is None


async def test_failed_generation_is_reported(
    analyst: httpx.AsyncClient, seeded_session: Session
) -> None:
    resp = await analyst.post(REPORTS, json={"team": "DET", "season": 2023})
    report = seeded_session.get_one(SavedReport, uuid.UUID(resp.json()["id"]))
    report.filters_json = {**report.filters_json, "season": 1999}
    seeded_session.commit()
    with pytest.raises(Exception, match="No imported data"):
        generate_saved_report(
            seeded_session, report.id, owner_id(seeded_session, "analyst@example.com"), noop
        )
    body = (await analyst.get(f"{REPORTS}/{report.id}")).json()
    assert body["status"] == ReportStatus.FAILED.value
    assert "No imported data" in body["error"]

"""Saved reports and exports: create (async jobs), read, delete. Owner-scoped (404 otherwise)."""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import repository as job_repo
from app.jobs.service import Enqueue, Submission, find_by_idempotency_key, submit_job
from app.jobs.state import JobStatus
from app.jobs.types import EXPORT_REPORT, GENERATE_REPORT
from app.models import ExportFormat, ReportExport, ReportStatus, SavedReport, User
from app.reports.contracts import ReportRequest
from app.services.errors import ConflictError, NotFoundError
from app.services.sources import resolve_source
from app.storage import Storage

FAILED_JOB = (JobStatus.FAILED, JobStatus.CANCELLED)


def _reconcile(session: Session, row: SavedReport | ReportExport) -> None:
    """A generation/export job that failed or was cancelled marks its row failed."""
    if row.status != ReportStatus.PENDING or row.job_id is None:
        return
    job = job_repo.get_job(session, row.job_id)
    if job is None or job.status not in FAILED_JOB:
        return
    message = "Cancelled" if job.status == JobStatus.CANCELLED else (job.error or "Job failed")
    model = type(row)
    session.execute(
        update(model)
        .where(model.id == row.id, model.status == ReportStatus.PENDING)
        .values(status=ReportStatus.FAILED, error=message)
    )
    session.commit()
    session.refresh(row)


def _params(body: ReportRequest) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"title", "idempotency_key"})


def create_report(
    session: Session,
    body: ReportRequest,
    *,
    user: User,
    idempotency_key: str | None,
    enqueue: Enqueue,
) -> tuple[SavedReport, bool]:
    """Validate access to the data now (so errors are immediate), then generate async."""
    key = idempotency_key or body.idempotency_key
    previous = find_by_idempotency_key(session, user.id, key)
    if previous is not None and previous.task_type == GENERATE_REPORT:
        report = session.get(SavedReport, uuid.UUID(str(previous.params["report_id"])))
        if report is not None and report.user_id == user.id:
            if report.filters_json != _params(body):
                raise ConflictError(
                    "idempotency_key_reused",
                    "This Idempotency-Key was already used with different parameters",
                    {"existing_report_id": str(report.id)},
                )
            return report, True

    source = resolve_source(session, body.season, body.dataset_id, user)
    team = source.require_team(session, body.team)
    params = _params(body)
    params["team"] = team.abbreviation
    title = (body.title or "").strip() or f"{team.abbreviation} scouting report"
    report = SavedReport(
        id=uuid.uuid4(),
        user_id=user.id,
        title=title[:120],
        team=team.abbreviation,
        season=body.season,
        dataset_id=body.dataset_id,
        filters_json=params,
        status=ReportStatus.PENDING,
    )
    session.add(report)
    session.commit()
    submission = submit_job(
        session,
        task_type=GENERATE_REPORT,
        target_key=f"report:{report.id}",
        params={"report_id": str(report.id)},
        user_id=user.id,
        idempotency_key=key,
        enqueue=enqueue,
        duplicate_message="This report is already being generated",
        timeout_seconds=get_settings().report_job_timeout_seconds,
    )
    report.job_id = submission.job.id
    session.commit()
    return report, False


def get_report(session: Session, report_id: uuid.UUID, user: User) -> SavedReport:
    report = session.get(SavedReport, report_id)
    if report is None or report.user_id != user.id:
        raise NotFoundError(f"Report {report_id} not found")
    _reconcile(session, report)
    return report


def list_reports(
    session: Session, user: User, *, page: int, page_size: int
) -> tuple[list[SavedReport], int]:
    where = SavedReport.user_id == user.id
    total = session.scalar(select(func.count()).select_from(SavedReport).where(where)) or 0
    items = list(
        session.scalars(
            select(SavedReport)
            .where(where)
            .order_by(SavedReport.created_at.desc(), SavedReport.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    for report in items:
        _reconcile(session, report)
    return items, total


def list_exports(session: Session, report: SavedReport) -> list[ReportExport]:
    rows = list(
        session.scalars(
            select(ReportExport)
            .where(ReportExport.report_id == report.id)
            .order_by(ReportExport.created_at.desc(), ReportExport.id)
        )
    )
    for row in rows:
        _reconcile(session, row)
    return rows


def delete_report(session: Session, storage: Storage, report: SavedReport) -> None:
    keys = [e.storage_key for e in list_exports(session, report) if e.storage_key]
    session.delete(report)
    session.commit()
    for key in keys:
        storage.delete(key)


def create_export(
    session: Session,
    report: SavedReport,
    fmt: ExportFormat,
    *,
    user: User,
    idempotency_key: str | None,
    enqueue: Enqueue,
) -> tuple[ReportExport, bool]:
    previous = find_by_idempotency_key(session, user.id, idempotency_key)
    if previous is not None and previous.task_type == EXPORT_REPORT:
        sub = _submit_export(
            session, report, fmt, previous.params["export_id"], user, idempotency_key, enqueue
        )
        export = session.get_one(ReportExport, uuid.UUID(str(sub.job.params["export_id"])))
        return export, True
    if report.status != ReportStatus.READY:
        raise ConflictError(
            "report_not_ready",
            f"Report is {report.status.value}; exports need a ready report",
            {"status": report.status.value},
        )
    export = ReportExport(
        id=uuid.uuid4(), report_id=report.id, format=fmt, status=ReportStatus.PENDING
    )
    session.add(export)
    session.commit()
    sub = _submit_export(session, report, fmt, str(export.id), user, idempotency_key, enqueue)
    export.job_id = sub.job.id
    session.commit()
    return export, False


def _submit_export(
    session: Session,
    report: SavedReport,
    fmt: ExportFormat,
    export_id: str,
    user: User,
    idempotency_key: str | None,
    enqueue: Enqueue,
) -> Submission:
    return submit_job(
        session,
        task_type=EXPORT_REPORT,
        target_key=f"export:{export_id}",
        params={"report_id": str(report.id), "export_id": export_id, "format": fmt.value},
        user_id=user.id,
        idempotency_key=idempotency_key,
        enqueue=enqueue,
        duplicate_message="This export is already being generated",
        timeout_seconds=get_settings().report_job_timeout_seconds,
    )


def get_export(session: Session, report: SavedReport, export_id: uuid.UUID) -> ReportExport:
    export = session.get(ReportExport, export_id)
    if export is None or export.report_id != report.id:
        raise NotFoundError(f"Export {export_id} not found")
    _reconcile(session, export)
    return export

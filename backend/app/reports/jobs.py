"""generate_report and export_report job handlers. Both are idempotent: a re-run
recomputes the same report body or rewrites the same export."""

import uuid

from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.jobs.errors import PermanentJobError
from app.jobs.handler_types import Checkpoint, HandlerResult
from app.models import ExportFormat, Job, ReportExport, ReportStatus, SavedReport, User
from app.reports.builder import generate
from app.reports.contracts import ScoutingReportOut
from app.reports.export import render_csv, render_json
from app.services.errors import ConflictError, InvalidRequestError, NotFoundError
from app.storage import Storage, get_storage


def _owned_report(s: Session, report_id: uuid.UUID, owner_id: int | None) -> SavedReport:
    report = s.get(SavedReport, report_id)
    if report is None or report.user_id != owner_id:
        raise PermanentJobError("report no longer exists")
    return report


def generate_saved_report(
    s: Session, report_id: uuid.UUID, owner_id: int | None, checkpoint: Checkpoint
) -> SavedReport:
    report = _owned_report(s, report_id, owner_id)
    owner = s.get_one(User, report.user_id)
    checkpoint("computing", 0, 1)
    try:
        body = generate(s, dict(report.filters_json), owner)
    except (NotFoundError, ConflictError, InvalidRequestError) as exc:
        report.status = ReportStatus.FAILED
        report.error = str(exc)
        s.commit()
        raise PermanentJobError(str(exc)) from exc
    report.report_json = body.model_dump(mode="json")
    report.status = ReportStatus.READY
    report.error = None
    s.commit()
    checkpoint("computing", 1, 1)
    return report


def write_export(
    s: Session, storage: Storage, export_id: uuid.UUID, owner_id: int | None
) -> ReportExport:
    export = s.get(ReportExport, export_id)
    if export is None:
        raise PermanentJobError("export no longer exists")
    report = _owned_report(s, export.report_id, owner_id)
    if report.report_json is None:
        raise PermanentJobError("report has no content to export")
    body = ScoutingReportOut.model_validate(report.report_json)
    if export.format == ExportFormat.CSV:
        data, suffix = render_csv(report.title, body), ".csv"
    else:
        data, suffix = render_json(report.title, body), ".json"
    old = export.storage_key
    export.storage_key = storage.write_bytes("exports", data, suffix=suffix)
    export.size_bytes = len(data)
    export.status = ReportStatus.READY
    export.error = None
    s.commit()
    if old:
        storage.delete(old)
    return export


def generate_report_handler(job: Job, checkpoint: Checkpoint) -> HandlerResult:
    report_id = uuid.UUID(str(job.params["report_id"]))
    with get_sessionmaker()() as s:
        report = generate_saved_report(s, report_id, job.user_id, checkpoint)
        findings = len((report.report_json or {}).get("findings", []))
    return HandlerResult({"report_id": str(report_id), "findings": findings})


def export_report_handler(job: Job, checkpoint: Checkpoint) -> HandlerResult:
    export_id = uuid.UUID(str(job.params["export_id"]))
    checkpoint("rendering", 0, 1)
    with get_sessionmaker()() as s:
        export = write_export(s, get_storage(), export_id, job.user_id)
        result = {"export_id": str(export_id), "size_bytes": export.size_bytes}
    checkpoint("rendering", 1, 1)
    return HandlerResult(result)

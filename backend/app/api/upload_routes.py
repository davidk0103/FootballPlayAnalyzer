"""Private CSV uploads: store, map, validate, process (async), inspect, delete."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile

from app.api.deps import CurrentUserDep, EnqueueDep, SessionDep, rate_limit
from app.api.routes import AUTH, CONFLICT, ERRORS
from app.auth.ratelimit import UPLOAD
from app.config import get_settings
from app.jobs import repository as job_repo
from app.models import UserDataset
from app.schemas import ErrorResponse, JobOut
from app.services.errors import PayloadTooLargeError
from app.storage import Storage, get_storage
from app.uploads import service as uploads
from app.uploads.contracts import (
    MappingIn,
    ProcessIn,
    QuarantinePage,
    RowIssueOut,
    SchemaFieldOut,
    TeamCountOut,
    UploadDetailOut,
    UploadOut,
    UploadPage,
    ValidationOut,
    upload_out,
)
from app.uploads.mapping import suggest_mapping
from app.uploads.processing import MAX_STORED_REJECTIONS
from app.uploads.schema import FIELDS

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"], responses={**ERRORS, **AUTH})
StorageDep = Annotated[Storage, Depends(get_storage)]
TOO_LARGE: dict[int | str, dict[str, Any]] = {413: {"model": ErrorResponse}}
MULTIPART_OVERHEAD = 64 * 1024


def _summary(session: SessionDep, dataset: UserDataset) -> UploadOut:
    return UploadOut.model_validate(upload_out(dataset, uploads.seasons(session, dataset)))


def _schema_fields() -> list[SchemaFieldOut]:
    return [
        SchemaFieldOut(
            name=f.name,
            label=f.label,
            kind=f.kind.value,
            description=f.description,
            required=f.required,
        )
        for f in FIELDS
    ]


def _detail(session: SessionDep, dataset: UserDataset) -> UploadDetailOut:
    job = job_repo.get_job(session, dataset.job_id) if dataset.job_id else None
    return UploadDetailOut.model_validate(
        {
            **upload_out(dataset, uploads.seasons(session, dataset)),
            "preview": dataset.preview,
            "suggested_mapping": suggest_mapping(dataset.columns),
            "schema_fields": _schema_fields(),
            "job": JobOut.model_validate(job) if job is not None else None,
        }
    )


@router.get("/schema")
def upload_schema() -> list[SchemaFieldOut]:
    """The standard fields an upload's columns can be mapped to."""
    return _schema_fields()


@router.post(
    "",
    status_code=201,
    responses={**CONFLICT, **TOO_LARGE},
    dependencies=[Depends(rate_limit(UPLOAD))],
)
def create_upload(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUserDep,
    file: Annotated[UploadFile, File(description="CSV file, UTF-8, at most 25 MB")],
    name: Annotated[str | None, Form(max_length=120)] = None,
) -> UploadDetailOut:
    """Store a CSV under a random name and inspect it. Contents are never executed."""
    limit = get_settings().upload_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + MULTIPART_OVERHEAD:
        raise PayloadTooLargeError(f"File exceeds the {limit // (1024 * 1024)} MB limit")
    dataset = uploads.create_upload(
        session,
        storage,
        user=user,
        stream=file.file,
        filename=file.filename or "upload.csv",
        name=name,
    )
    return _detail(session, dataset)


@router.get("")
def list_uploads(
    session: SessionDep,
    user: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> UploadPage:
    items, total = uploads.list_uploads(session, user, page=page, page_size=page_size)
    return UploadPage(
        items=[_summary(session, d) for d in items], page=page, page_size=page_size, total=total
    )


@router.get("/{upload_id}")
def get_upload(upload_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> UploadDetailOut:
    return _detail(session, uploads.get_upload(session, upload_id, user))


@router.post("/{upload_id}/validate", responses=CONFLICT)
def validate_upload(
    upload_id: uuid.UUID,
    body: MappingIn,
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUserDep,
) -> ValidationOut:
    """Dry-run a column mapping on the first rows. Saves the mapping when it is usable."""
    dataset = uploads.get_upload(session, upload_id, user)
    result = uploads.validate_mapping(session, storage, dataset, body.mapping)
    return ValidationOut(
        valid=result.valid,
        mapping_errors=result.mapping_errors,
        checked_rows=result.checked_rows,
        total_rows=dataset.row_count,
        accepted_rows=result.accepted_rows,
        rejected_rows=result.rejected_rows,
        issues=[RowIssueOut(row_number=n, reason=r, values=v) for n, r, v in result.issues],
        warnings=result.warnings,
        upload=_summary(session, dataset),
    )


@router.post("/{upload_id}/process", status_code=202, responses=CONFLICT)
def process_upload(
    upload_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    enqueue: EnqueueDep,
    response: Response,
    body: ProcessIn | None = None,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ] = None,
) -> JobOut:
    """Start the background job that stores every valid row. Poll the returned job."""
    dataset = uploads.get_upload(session, upload_id, user)
    submission = uploads.submit_processing(
        session,
        dataset,
        user=user,
        idempotency_key=idempotency_key or (body.idempotency_key if body else None),
        enqueue=enqueue,
    )
    if submission.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return JobOut.model_validate(submission.job)


@router.delete("/{upload_id}", status_code=204, responses=CONFLICT)
def delete_upload(
    upload_id: uuid.UUID, session: SessionDep, storage: StorageDep, user: CurrentUserDep
) -> Response:
    """Delete the dataset, its stored rows, and its file. Saved reports keep their snapshot."""
    uploads.delete_upload(session, storage, uploads.get_upload(session, upload_id, user))
    return Response(status_code=204)


@router.get("/{upload_id}/teams")
def upload_teams(
    upload_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> list[TeamCountOut]:
    dataset = uploads.get_upload(session, upload_id, user)
    return [
        TeamCountOut(abbreviation=t, offense_plays=o, defense_plays=d)
        for t, o, d in uploads.team_counts(session, dataset)
    ]


@router.get("/{upload_id}/rejected")
def upload_rejected_rows(
    upload_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> QuarantinePage:
    """Rows that failed validation during processing, with the reason and original values."""
    dataset = uploads.get_upload(session, upload_id, user)
    rows, total = uploads.quarantine(session, dataset, page=page, page_size=page_size)
    return QuarantinePage(
        items=[RowIssueOut(row_number=r.row_number, reason=r.reason, values=r.raw) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        stored_limit=MAX_STORED_REJECTIONS,
    )

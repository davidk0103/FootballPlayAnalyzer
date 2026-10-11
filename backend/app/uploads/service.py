"""Upload lifecycle: store + inspect, dry-run a mapping, submit processing, delete.

Every lookup is scoped to the owner; another user's dataset id behaves exactly like a
missing one (404). Status transitions:

    uploaded -> validated -> processing -> ready
                     ^            |
                     +-- failed <-+   (failed keeps the file so the user can fix the
                                       mapping and process again)
"""

import hashlib
import uuid
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.service import Enqueue, Submission, find_by_idempotency_key, submit_job
from app.jobs.state import JobStatus
from app.jobs.types import IMPORT_UPLOAD
from app.models import Job, UploadStatus, User, UserDataset, UserPlay, UserRejectedRow
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.storage import FileTooLargeError, Storage, opened
from app.uploads.csvfile import CsvValidationError, inspect_csv, read_frame
from app.uploads.mapping import Mapping, mapping_errors
from app.uploads.normalize import normalize, raw_values

MAX_ISSUES = 50
PROCESSABLE = (UploadStatus.UPLOADED, UploadStatus.VALIDATED, UploadStatus.FAILED)


def _sha256(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _safe_filename(filename: str) -> str:
    """Display-only: the stored file always gets a random name."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(ch for ch in base if ch.isprintable()).strip()[:255] or "upload.csv"


def _display_name(name: str | None, filename: str) -> str:
    base = (name or "").strip() or _safe_filename(filename).rsplit(".", 1)[0]
    return "".join(ch for ch in base if ch.isprintable()).strip()[:120] or "Uploaded dataset"


def create_upload(
    session: Session,
    storage: Storage,
    *,
    user: User,
    stream: BinaryIO,
    filename: str,
    name: str | None,
) -> UserDataset:
    settings = get_settings()
    try:
        key, size = storage.save(
            "uploads", stream, suffix=".csv", max_bytes=settings.upload_max_bytes
        )
    except FileTooLargeError as exc:
        raise PayloadTooLargeError(str(exc)) from exc
    try:
        with opened(storage, key) as f:
            sha = _sha256(f)
            duplicate = session.scalar(
                select(UserDataset).where(
                    UserDataset.user_id == user.id,
                    UserDataset.sha256 == sha,
                    UserDataset.status != UploadStatus.FAILED,
                )
            )
            if duplicate is not None:
                raise ConflictError(
                    "duplicate_upload",
                    f"You already uploaded this file as '{duplicate.name}'",
                    {"existing_upload_id": str(duplicate.id)},
                )
            f.seek(0)
            info = inspect_csv(
                f,
                max_columns=settings.upload_max_columns,
                max_rows=settings.upload_max_rows,
                preview_rows=settings.upload_preview_rows,
            )
    except CsvValidationError as exc:
        storage.delete(key)
        raise InvalidRequestError(str(exc), code=exc.code) from exc
    except BaseException:
        storage.delete(key)
        raise

    dataset = UserDataset(
        id=uuid.uuid4(),
        user_id=user.id,
        name=_display_name(name, filename),
        original_filename=_safe_filename(filename),
        storage_key=key,
        size_bytes=size,
        sha256=sha,
        delimiter=info.delimiter,
        status=UploadStatus.UPLOADED,
        columns=info.columns,
        preview=info.preview,
        row_count=info.row_count,
        warnings=[],
    )
    session.add(dataset)
    session.commit()
    return dataset


def _reconcile(session: Session, dataset: UserDataset) -> None:
    """A processing job that failed or was cancelled leaves the dataset retryable."""
    if dataset.status != UploadStatus.PROCESSING or dataset.job_id is None:
        return
    job = session.get(Job, dataset.job_id)
    if job is None or job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        return
    cancelled = job.status == JobStatus.CANCELLED
    session.execute(
        update(UserDataset)
        .where(UserDataset.id == dataset.id, UserDataset.status == UploadStatus.PROCESSING)
        .values(
            status=UploadStatus.VALIDATED if cancelled else UploadStatus.FAILED,
            error="Processing was cancelled" if cancelled else job.error,
        )
    )
    session.commit()
    session.refresh(dataset)


def get_upload(session: Session, upload_id: uuid.UUID, user: User) -> UserDataset:
    dataset = session.get(UserDataset, upload_id)
    if dataset is None or dataset.user_id != user.id:
        raise NotFoundError(f"Upload {upload_id} not found")
    _reconcile(session, dataset)
    return dataset


def get_ready_upload(session: Session, upload_id: uuid.UUID, user: User | None) -> UserDataset:
    if user is None:
        raise NotFoundError(f"Upload {upload_id} not found")
    dataset = get_upload(session, upload_id, user)
    if dataset.status != UploadStatus.READY:
        raise ConflictError(
            "upload_not_ready",
            f"Upload '{dataset.name}' is {dataset.status.value}; process it before analyzing",
            {"status": dataset.status.value},
        )
    return dataset


def list_uploads(
    session: Session, user: User, *, page: int, page_size: int
) -> tuple[list[UserDataset], int]:
    where = UserDataset.user_id == user.id
    total = session.scalar(select(func.count()).select_from(UserDataset).where(where)) or 0
    items = list(
        session.scalars(
            select(UserDataset)
            .where(where)
            .order_by(UserDataset.created_at.desc(), UserDataset.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    for dataset in items:
        _reconcile(session, dataset)
    return items, total


def seasons(session: Session, dataset: UserDataset) -> list[int]:
    if dataset.status != UploadStatus.READY:
        return []
    rows = session.scalars(
        select(UserPlay.season)
        .where(UserPlay.dataset_id == dataset.id, UserPlay.season.is_not(None))
        .distinct()
        .order_by(UserPlay.season)
    )
    return [int(s) for s in rows if s is not None]


@dataclass(frozen=True)
class Validation:
    valid: bool
    mapping_errors: list[str]
    checked_rows: int
    accepted_rows: int
    rejected_rows: int
    issues: list[tuple[int, str, dict[str, str]]]
    warnings: list[str]


def _require_file(dataset: UserDataset) -> str:
    if dataset.storage_key is None:
        raise ConflictError(
            "upload_file_removed",
            "The original file was removed after processing; upload it again to remap",
        )
    return dataset.storage_key


def validate_mapping(
    session: Session, storage: Storage, dataset: UserDataset, mapping: Mapping
) -> Validation:
    """Dry-run the mapping on the first rows. A valid mapping is saved for processing."""
    if dataset.status not in PROCESSABLE:
        raise ConflictError(
            "upload_busy", f"Upload is {dataset.status.value}", {"status": dataset.status.value}
        )
    key = _require_file(dataset)
    mapping = {f: c for f, c in mapping.items() if c}
    errors = mapping_errors(mapping, dataset.columns)
    if errors:
        return Validation(False, errors, 0, 0, 0, [], [])

    sample_rows = get_settings().upload_validate_sample_rows
    with opened(storage, key) as f:
        raw = read_frame(f, dataset.delimiter, nrows=sample_rows)
    result = normalize(raw, mapping)
    shown = result.rejected.head(MAX_ISSUES)
    values = raw_values(raw, [int(n) for n in shown["row_number"]])
    issues = [
        (int(n), str(reason), values.get(int(n), {}))
        for n, reason in zip(shown["row_number"].tolist(), shown["reason"].tolist(), strict=True)
    ]
    valid = len(result.plays) > 0
    if valid:
        dataset.mapping = mapping
        dataset.status = UploadStatus.VALIDATED
        dataset.error = None
        dataset.warnings = result.warnings
        session.commit()
    return Validation(
        valid=valid,
        mapping_errors=[] if valid else ["No rows in the sample are valid with this mapping"],
        checked_rows=len(raw),
        accepted_rows=len(result.plays),
        rejected_rows=len(result.rejected),
        issues=issues,
        warnings=result.warnings,
    )


def submit_processing(
    session: Session,
    dataset: UserDataset,
    *,
    user: User,
    idempotency_key: str | None,
    enqueue: Enqueue,
) -> Submission:
    params = {"dataset_id": str(dataset.id)}

    def submit() -> Submission:
        return submit_job(
            session,
            task_type=IMPORT_UPLOAD,
            target_key=f"upload:{dataset.id}",
            params=params,
            user_id=user.id,
            idempotency_key=idempotency_key,
            enqueue=enqueue,
            duplicate_message="This upload is already being processed",
            timeout_seconds=get_settings().upload_job_timeout_seconds,
        )

    if find_by_idempotency_key(session, user.id, idempotency_key) is not None:
        return submit()
    if dataset.status not in PROCESSABLE:
        raise ConflictError(
            "upload_busy",
            f"Upload is already {dataset.status.value}",
            {"status": dataset.status.value},
        )
    if dataset.status == UploadStatus.UPLOADED or not dataset.mapping:
        raise ConflictError(
            "upload_not_validated",
            "Validate a column mapping before processing",
            {"status": dataset.status.value},
        )
    _require_file(dataset)

    previous = dataset.status
    claimed = session.execute(  # type: ignore[attr-defined]
        update(UserDataset)
        .where(UserDataset.id == dataset.id, UserDataset.status == previous)
        .values(status=UploadStatus.PROCESSING, error=None)
    ).rowcount
    session.commit()
    if not claimed:
        raise ConflictError("upload_busy", "Upload state changed; reload and try again")
    try:
        submission = submit()
    except BaseException:
        session.execute(
            update(UserDataset)
            .where(UserDataset.id == dataset.id, UserDataset.status == UploadStatus.PROCESSING)
            .values(status=previous)
        )
        session.commit()
        raise
    session.execute(
        update(UserDataset).where(UserDataset.id == dataset.id).values(job_id=submission.job.id)
    )
    session.commit()
    session.refresh(dataset)
    return submission


def delete_upload(session: Session, storage: Storage, dataset: UserDataset) -> None:
    if dataset.status == UploadStatus.PROCESSING:
        raise ConflictError(
            "upload_processing", "Cancel the processing job before deleting this upload"
        )
    key = dataset.storage_key
    session.delete(dataset)
    session.commit()
    if key is not None:
        storage.delete(key)


def team_counts(session: Session, dataset: UserDataset) -> list[tuple[str, int, int]]:
    off = dict(
        session.execute(
            select(UserPlay.offense, func.count())
            .where(UserPlay.dataset_id == dataset.id)
            .group_by(UserPlay.offense)
        ).all()
    )
    de = dict(
        session.execute(
            select(UserPlay.defense, func.count())
            .where(UserPlay.dataset_id == dataset.id)
            .group_by(UserPlay.defense)
        ).all()
    )
    return [(t, int(off.get(t, 0)), int(de.get(t, 0))) for t in sorted(set(off) | set(de))]


def quarantine(
    session: Session, dataset: UserDataset, *, page: int, page_size: int
) -> tuple[list[UserRejectedRow], int]:
    where = UserRejectedRow.dataset_id == dataset.id
    total = session.scalar(select(func.count()).select_from(UserRejectedRow).where(where)) or 0
    rows = list(
        session.scalars(
            select(UserRejectedRow)
            .where(where)
            .order_by(UserRejectedRow.row_number)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total

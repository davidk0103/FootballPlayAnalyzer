"""The import_upload job: normalize every row of an uploaded file and store it.

Idempotent: a re-run deletes the dataset's previous rows in the same transaction that
inserts the new ones. The original file is deleted only after the job is committed
as succeeded, so a crashed attempt can always start over from the file.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import delete, insert, update
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.jobs.errors import PermanentJobError
from app.jobs.handler_types import Checkpoint, HandlerResult
from app.models import Job, UploadStatus, UserDataset, UserPlay, UserRejectedRow
from app.repositories.frames import clear_upload_frames
from app.storage import Storage, get_storage, opened
from app.uploads.csvfile import CsvValidationError, read_frame
from app.uploads.mapping import mapping_errors
from app.uploads.normalize import PLAY_COLUMNS, Normalized, normalize, raw_values

log = logging.getLogger(__name__)

NORMALIZE_CHUNK = 20_000
INSERT_CHUNK = 5_000
MAX_STORED_REJECTIONS = 1_000


def content_version(dataset: UserDataset) -> str:
    payload = json.dumps(
        {"id": str(dataset.id), "sha": dataset.sha256, "mapping": dataset.mapping},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _records(df: pd.DataFrame) -> list[dict[str, object]]:
    obj = df.astype(object)
    return obj.where(df.notna(), None).to_dict("records")  # type: ignore[return-value]


def _normalize_all(
    raw: pd.DataFrame, mapping: dict[str, str], checkpoint: Checkpoint
) -> Normalized:
    total = len(raw)
    parts: list[Normalized] = []
    for start in range(0, total, NORMALIZE_CHUNK):
        parts.append(normalize(raw.iloc[start : start + NORMALIZE_CHUNK], mapping))
        checkpoint("validating", min(start + NORMALIZE_CHUNK, total), total)
    return Normalized(
        plays=pd.concat([p.plays for p in parts], ignore_index=True),
        rejected=pd.concat([p.rejected for p in parts], ignore_index=True),
        warnings=parts[0].warnings if parts else [],
    )


@dataclass(frozen=True)
class Processed:
    stored: int
    rejected: int
    version: str
    storage_key: str


def process_upload(
    s: Session,
    storage: Storage,
    dataset_id: uuid.UUID,
    owner_id: int | None,
    checkpoint: Checkpoint,
) -> Processed:
    """Normalize and store every row in one transaction (committed on success)."""
    dataset = s.get(UserDataset, dataset_id)
    if dataset is None or dataset.user_id != owner_id:
        raise PermanentJobError("upload no longer exists")
    key = dataset.storage_key
    if key is None or not storage.exists(key):
        raise PermanentJobError("the uploaded file is no longer available; upload it again")
    mapping = dict(dataset.mapping or {})
    problems = mapping_errors(mapping, dataset.columns)
    if problems:
        raise PermanentJobError("; ".join(problems))

    checkpoint("reading", 0, dataset.row_count)
    try:
        with opened(storage, key) as f:
            raw = read_frame(f, dataset.delimiter)
    except CsvValidationError as exc:
        raise PermanentJobError(str(exc)) from exc
    result = _normalize_all(raw, mapping, checkpoint)

    s.execute(delete(UserPlay).where(UserPlay.dataset_id == dataset_id))
    s.execute(delete(UserRejectedRow).where(UserRejectedRow.dataset_id == dataset_id))
    kept = result.rejected.head(MAX_STORED_REJECTIONS)
    values = raw_values(raw, [int(n) for n in kept["row_number"]])
    if len(kept):
        s.execute(
            insert(UserRejectedRow),
            [
                {
                    "dataset_id": dataset_id,
                    "row_number": int(n),
                    "reason": str(reason),
                    "raw": values.get(int(n), {}),
                }
                for n, reason in zip(
                    kept["row_number"].tolist(), kept["reason"].tolist(), strict=True
                )
            ],
        )

    plays = result.plays
    if plays.empty:
        dataset.status = UploadStatus.FAILED
        dataset.stored_count = 0
        dataset.rejected_count = len(result.rejected)
        dataset.error = "No rows were valid; see the rejected rows for reasons"
        s.commit()
        raise PermanentJobError(dataset.error)

    total = len(plays)
    columns = ["row_number", *PLAY_COLUMNS]
    for start in range(0, total, INSERT_CHUNK):
        chunk = plays.iloc[start : start + INSERT_CHUNK][columns]
        rows = _records(chunk)
        for row in rows:
            row["dataset_id"] = dataset_id
        s.execute(insert(UserPlay), rows)
        checkpoint("storing", min(start + INSERT_CHUNK, total), total)

    warnings = list(result.warnings)
    if len(result.rejected) > MAX_STORED_REJECTIONS:
        warnings.append(
            f"{len(result.rejected):,} rows were rejected; the first "
            f"{MAX_STORED_REJECTIONS:,} are kept for review"
        )
    version = content_version(dataset)
    dataset.status = UploadStatus.READY
    dataset.stored_count = total
    dataset.rejected_count = len(result.rejected)
    dataset.warnings = warnings
    dataset.error = None
    dataset.content_version = version
    dataset.processed_at = datetime.now(UTC)
    s.commit()
    return Processed(total, len(result.rejected), version, key)


def import_upload_handler(job: Job, checkpoint: Checkpoint) -> HandlerResult:
    dataset_id = uuid.UUID(str(job.params["dataset_id"]))
    storage = get_storage()
    with get_sessionmaker()() as s:
        done = process_upload(s, storage, dataset_id, job.user_id, checkpoint)

    def remove_file() -> None:
        with get_sessionmaker()() as s2:
            s2.execute(
                update(UserDataset).where(UserDataset.id == dataset_id).values(storage_key=None)
            )
            s2.commit()
        storage.delete(done.storage_key)
        clear_upload_frames(dataset_id)

    after: list[Callable[[], object]] = [remove_file]
    return HandlerResult(
        {
            "dataset_id": str(dataset_id),
            "stored": done.stored,
            "rejected": done.rejected,
            "content_version": done.version,
        },
        after_success=after,
    )

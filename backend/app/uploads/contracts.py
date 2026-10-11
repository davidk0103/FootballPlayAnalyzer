"""Request and response models for the uploads API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import UploadStatus
from app.schemas import JobOut


class SchemaFieldOut(BaseModel):
    name: str
    label: str
    kind: str
    description: str
    required: bool


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    original_filename: str
    size_bytes: int
    status: UploadStatus
    delimiter: str
    columns: list[str]
    row_count: int
    mapping: dict[str, str] | None
    stored_count: int | None
    rejected_count: int | None
    seasons: list[int] = []
    warnings: list[str]
    error: str | None
    job_id: uuid.UUID | None
    file_retained: bool
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None


class UploadDetailOut(UploadOut):
    preview: list[list[str]]
    suggested_mapping: dict[str, str]
    schema_fields: list[SchemaFieldOut]
    job: JobOut | None = None


class UploadPage(BaseModel):
    items: list[UploadOut]
    page: int
    page_size: int
    total: int


class MappingIn(BaseModel):
    mapping: dict[str, str] = Field(
        description="Standard field name -> column in your file", max_length=50
    )


class RowIssueOut(BaseModel):
    row_number: int
    reason: str
    values: dict[str, str]


class ValidationOut(BaseModel):
    """Dry run of a mapping on the first rows of the file. Nothing is stored."""

    valid: bool
    mapping_errors: list[str]
    checked_rows: int
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    issues: list[RowIssueOut]
    warnings: list[str]
    upload: UploadOut


class ProcessIn(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class TeamCountOut(BaseModel):
    abbreviation: str
    offense_plays: int
    defense_plays: int


class QuarantinePage(BaseModel):
    items: list[RowIssueOut]
    page: int
    page_size: int
    total: int
    stored_limit: int


def upload_out(dataset: Any, seasons: list[int] | None = None) -> dict[str, Any]:
    return {
        **{k: getattr(dataset, k) for k in UploadOut.model_fields if hasattr(dataset, k)},
        "file_retained": dataset.storage_key is not None,
        "seasons": seasons or [],
    }

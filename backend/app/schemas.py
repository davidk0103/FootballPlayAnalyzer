import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.state import AttemptStatus, JobStatus


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    abbreviation: str
    name: str
    conference: str
    division: str


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    abbreviation: str
    name: str


class SeasonOut(BaseModel):
    season: int
    plays: int
    games: int
    dataset_version: str | None
    sha256: str


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_game_id: str
    season: int
    season_type: str
    week: int
    game_date: date | None
    home_team: TeamRef
    away_team: TeamRef


class GameDetailOut(GameOut):
    play_count: int


class GamePage(BaseModel):
    items: list[GameOut]
    page: int
    page_size: int
    total: int


class MetricOut(BaseModel):
    value: float | None
    numerator: float
    denominator: int


class MetricsOut(BaseModel):
    epa_per_play: MetricOut
    success_rate: MetricOut
    yards_per_play: MetricOut
    pass_rate: MetricOut
    third_down_conversion_rate: MetricOut
    explosive_play_rate: MetricOut
    turnovers_per_game: MetricOut


class SampleOut(BaseModel):
    plays: int
    games: int


class DatasetOut(BaseModel):
    source: str
    version: str | None
    sha256: str


class FiltersOut(BaseModel):
    season: int
    side: str
    season_type: str | None = None
    down: list[int] | None = None
    distance: str | None = None
    field_zone: str | None = None
    qtr: list[int] | None = None
    play_type: str | None = None


class TeamStatsOut(BaseModel):
    team: TeamRef
    sample: SampleOut
    metrics: MetricsOut
    warnings: list[str]


class TeamStatsResponse(TeamStatsOut):
    filters: FiltersOut
    definitions: dict[str, str]
    dataset: DatasetOut


class TeamComparisonResponse(BaseModel):
    filters: FiltersOut
    team_a: TeamStatsOut
    team_b: TeamStatsOut
    definitions: dict[str, str]
    dataset: DatasetOut
    warnings: list[str]


class HealthOut(BaseModel):
    status: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None
    details: list[dict[str, object]] | dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ImportJobRequest(BaseModel):
    season: int = Field(ge=1999, le=2100, description="Season to import, e.g. 2024")
    force: bool = Field(default=False, description="Re-import even if the file checksum matches")
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Alternative to the Idempotency-Key header",
    )


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: str
    status: JobStatus
    params: dict[str, Any]
    user_id: int | None
    attempt_count: int
    max_attempts: int
    timeout_seconds: int
    result: dict[str, Any] | None = Field(validation_alias="result_ref")
    progress: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    next_retry_at: datetime | None
    cancel_requested_at: datetime | None


class JobPage(BaseModel):
    items: list[JobOut]
    page: int
    page_size: int
    total: int


class JobAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_number: int
    status: AttemptStatus
    worker: str | None
    error_type: str | None
    error: str | None
    retry_delay_seconds: float | None
    started_at: datetime
    finished_at: datetime | None


class CacheStatsOut(BaseModel):
    enabled: bool
    available: bool
    hits: int
    misses: int
    bypass: int
    invalidations: int
    hit_rate: float | None
    degraded_errors_this_process: int
    ttl_seconds: int


class ReadinessOut(BaseModel):
    status: str
    database: str
    redis: str


class CredentialsIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, examples=["coach@example.com"])
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
    created_at: datetime

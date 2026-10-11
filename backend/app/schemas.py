import uuid
from datetime import date, datetime
from typing import Any, Literal

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
    kind: Literal["public", "upload"] = "public"
    # Upload datasets only: the private dataset id and its display name.
    id: str | None = None
    name: str | None = None


class FiltersOut(BaseModel):
    season: int | None
    side: str
    season_type: str | None = None
    week_min: int | None = None
    week_max: int | None = None
    opponent: str | None = None
    down: list[int] | None = None
    distance: str | None = None
    field_zone: str | None = None
    qtr: list[int] | None = None
    score_state: str | None = None
    play_type: str | None = None
    explosive_run_yards: int | None = None
    explosive_pass_yards: int | None = None


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


# --- M3 analytics -------------------------------------------------------------------


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TeamKey(AnalyticsModel):
    """A team as named in the dataset (public datasets also carry the full name)."""

    abbreviation: str
    name: str | None = None


class RankOut(AnalyticsModel):
    metric: str
    rank: int
    of: int
    better: Literal["higher", "lower"]


class Envelope(BaseModel):
    filters: FiltersOut
    definitions: dict[str, str]
    dataset: DatasetOut
    warnings: list[str]


class SituationRowOut(AnalyticsModel):
    key: str
    label: str
    plays: int
    games: int
    metrics: dict[str, MetricOut]
    league: dict[str, MetricOut] | None


class SituationalResponse(Envelope):
    team: TeamKey | None
    group_by: str
    overall: SituationRowOut
    rows: list[SituationRowOut]


class EfficiencySplitOut(AnalyticsModel):
    key: str
    label: str
    plays: int
    games: int
    metrics: dict[str, MetricOut]
    league: dict[str, MetricOut]
    rank: RankOut | None


class EfficiencyResponse(Envelope):
    team: TeamKey
    splits: list[EfficiencySplitOut]


class TrendPointOut(AnalyticsModel):
    game_key: str
    week: int | None
    season_type: str | None
    opponent: str | None
    plays: int
    metrics: dict[str, MetricOut]
    league_epa_per_play: float | None


class TrendsResponse(Envelope):
    team: TeamKey
    games: list[TrendPointOut]


class TendencyCellOut(AnalyticsModel):
    down: int
    distance: str
    plays: int
    pass_rate: MetricOut
    epa_per_play: MetricOut
    success_rate: MetricOut
    league_pass_rate: MetricOut


class ThirdDownBucketOut(AnalyticsModel):
    distance: str
    plays: int
    conversion_rate: MetricOut
    league_conversion_rate: MetricOut
    pass_rate: MetricOut
    epa_per_play: MetricOut


class ThirdDownOut(AnalyticsModel):
    plays: int
    games: int
    conversion_rate: MetricOut
    converted_by_penalty: int
    avg_yards_to_go: float | None
    pass_rate: MetricOut
    epa_per_play: MetricOut
    league_conversion_rate: MetricOut
    rank: RankOut | None
    by_distance: list[ThirdDownBucketOut]


class TendenciesResponse(Envelope):
    team: TeamKey
    sample: SampleOut
    down_distance: list[TendencyCellOut]
    third_down: ThirdDownOut


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Stable nflverse GSIS player id, e.g. 00-0034796")
    name: str | None
    position: str | None


class PlayerListItem(PlayerOut):
    season_plays: int | None = Field(
        default=None, description="Plays as passer, rusher, or target in the season filter"
    )


class PlayerPage(BaseModel):
    items: list[PlayerListItem]
    page: int
    page_size: int
    total: int


StatValue = int | MetricOut


class PlayerStatsResponse(Envelope):
    player: PlayerOut
    teams: list[str]
    sample: SampleOut
    passing: dict[str, StatValue]
    rushing: dict[str, StatValue]
    receiving: dict[str, StatValue]
    limitations: list[str]


class GamePlayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    play_id: int
    qtr: int | None
    game_seconds_remaining: int | None
    offense: str | None
    defense: str | None
    down: int | None
    yards_to_go: int | None
    yard_line_100: int | None
    score_differential: int | None
    play_type: str
    yards_gained: int | None
    epa: float | None
    success: bool | None
    touchdown: bool | None
    interception: bool | None
    fumble_lost: bool | None
    penalty: bool | None
    passer: str | None
    rusher: str | None
    receiver: str | None


class GamePlayPage(BaseModel):
    game: GameOut
    items: list[GamePlayOut]
    page: int
    page_size: int
    total: int

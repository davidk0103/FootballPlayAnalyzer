from datetime import date

from pydantic import BaseModel, ConfigDict


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
    details: list[dict[str, object]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody

"""Request and response models for scouting reports and exports."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.filters import SeasonType
from app.analytics.metrics import EXPLOSIVE_PASS_YARDS, EXPLOSIVE_RUN_YARDS
from app.models import ExportFormat, ReportStatus
from app.schemas import (
    AnalyticsModel,
    DatasetOut,
    FiltersOut,
    MetricOut,
    TeamKey,
    TendencyCellOut,
    ThirdDownOut,
)


class ReportRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    team: str = Field(min_length=2, max_length=5, description="Team abbreviation, e.g. DET")
    season: int | None = Field(default=None, ge=1999, le=2100)
    dataset_id: uuid.UUID | None = Field(
        default=None, description="One of your processed uploads; omit for public data"
    )
    season_type: SeasonType | None = None
    week_min: int | None = Field(default=None, ge=1, le=22)
    week_max: int | None = Field(default=None, ge=1, le=22)
    opponent: str | None = Field(default=None, min_length=2, max_length=5)
    explosive_run_yards: int = Field(default=EXPLOSIVE_RUN_YARDS, ge=5, le=50)
    explosive_pass_yards: int = Field(default=EXPLOSIVE_PASS_YARDS, ge=10, le=60)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "ReportRequest":
        if self.dataset_id is None and self.season is None:
            raise ValueError("season is required for public data")
        if self.week_min and self.week_max and self.week_min > self.week_max:
            raise ValueError("week_min must not be after week_max")
        return self


class ReportMetricOut(AnalyticsModel):
    name: str
    label: str
    value: float | None
    numerator: float
    denominator: int
    league_value: float | None
    difference: float | None
    rank: int | None
    of: int | None
    better: Literal["higher", "lower"] | None


class RedZoneOut(AnalyticsModel):
    plays: int
    epa_per_play: MetricOut
    success_rate: MetricOut
    touchdown_rate: MetricOut


class SideReportOut(AnalyticsModel):
    side: Literal["offense", "defense"]
    plays: int
    games: int
    metrics: list[ReportMetricOut]
    third_down: ThirdDownOut
    red_zone: RedZoneOut
    league_red_zone: RedZoneOut


class FindingOut(AnalyticsModel):
    side: Literal["offense", "defense"]
    metric: str
    kind: Literal["strength", "weakness", "tendency"]
    text: str


class PlayerLeaderOut(BaseModel):
    category: Literal["passing", "rushing", "receiving"]
    player_id: str
    name: str | None
    position: str | None
    volume: int
    yards: int


class ScoutingReportOut(BaseModel):
    """The stored report body. A snapshot: it does not change if data is re-imported."""

    team: TeamKey
    generated_at: datetime
    dataset: DatasetOut
    filters: FiltersOut
    offense: SideReportOut
    defense: SideReportOut
    tendencies: list[TendencyCellOut]
    findings: list[FindingOut]
    top_players: list[PlayerLeaderOut]
    definitions: dict[str, str]
    warnings: list[str]
    limitations: list[str]


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    team: str
    season: int | None
    dataset_id: uuid.UUID | None
    status: ReportStatus
    error: str | None
    job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_id: uuid.UUID
    format: ExportFormat
    status: ReportStatus
    size_bytes: int | None
    error: str | None
    job_id: uuid.UUID | None
    created_at: datetime
    download_url: str | None = None


class ReportOut(ReportSummaryOut):
    filters: dict[str, object] = Field(validation_alias="filters_json")
    report: ScoutingReportOut | None = Field(validation_alias="report_json")
    exports: list[ExportOut] = []


class ReportPage(BaseModel):
    items: list[ReportSummaryOut]
    page: int
    page_size: int
    total: int


class ExportRequest(BaseModel):
    format: ExportFormat
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

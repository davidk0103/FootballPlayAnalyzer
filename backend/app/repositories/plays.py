import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.filters import Side
from app.analytics.metrics import SCRIMMAGE_PLAY_TYPES
from app.models import Dataset, DatasetStatus, Play

ANALYTICS_COLUMNS = (
    Play.game_id,
    Play.season_type,
    Play.play_type,
    Play.down,
    Play.yards_to_go,
    Play.yard_line_100,
    Play.qtr,
    Play.yards_gained,
    Play.epa,
    Play.success,
    Play.interception,
    Play.fumble_lost,
    Play.third_down_converted,
    Play.two_point_attempt,
    Play.play_deleted,
)


def team_season_plays(session: Session, team_id: int, season: int, side: Side) -> pd.DataFrame:
    """Pass/run plays for one team-season on offense or defense, analytics columns only."""
    team_col = Play.offense_team_id if side == Side.OFFENSE else Play.defense_team_id
    stmt = select(*ANALYTICS_COLUMNS).where(
        Play.season == season,
        team_col == team_id,
        Play.play_type.in_(SCRIMMAGE_PLAY_TYPES),
    )
    rows = session.execute(stmt).all()
    df = pd.DataFrame(rows, columns=[c.key for c in ANALYTICS_COLUMNS])
    for col in ("down", "yards_to_go", "yard_line_100", "qtr", "yards_gained"):
        df[col] = df[col].astype("Int64")
    df["epa"] = df["epa"].astype("Float64")
    return df


def latest_dataset(session: Session, season: int) -> Dataset | None:
    return session.scalar(
        select(Dataset)
        .where(Dataset.season == season, Dataset.status == DatasetStatus.COMPLETED)
        .order_by(Dataset.completed_at.desc(), Dataset.id.desc())
        .limit(1)
    )


def season_summaries(session: Session) -> list[tuple[int, int, int]]:
    """(season, plays, games) for every season with stored plays."""
    stmt = (
        select(Play.season, func.count(), func.count(func.distinct(Play.game_id)))
        .group_by(Play.season)
        .order_by(Play.season.desc())
    )
    return [(int(s), int(p), int(g)) for s, p, g in session.execute(stmt)]

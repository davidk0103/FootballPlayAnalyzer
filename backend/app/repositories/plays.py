from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Dataset, DatasetStatus, Play


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

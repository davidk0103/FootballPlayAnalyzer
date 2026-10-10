from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Game, Play


def _filtered(season: int | None, week: int | None, team_id: int | None) -> Select[Game]:
    stmt = select(Game)
    if season is not None:
        stmt = stmt.where(Game.season == season)
    if week is not None:
        stmt = stmt.where(Game.week == week)
    if team_id is not None:
        stmt = stmt.where(or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
    return stmt


def list_games(
    session: Session,
    *,
    season: int | None,
    week: int | None,
    team_id: int | None,
    offset: int,
    limit: int,
) -> tuple[list[Game], int]:
    base = _filtered(season, week, team_id)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.scalars(
        base.order_by(Game.season, Game.week, Game.game_date, Game.external_game_id)
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), total


def get_game(session: Session, game_id: int) -> Game | None:
    return session.get(Game, game_id)


def count_game_plays(session: Session, game_id: int) -> int:
    return session.scalar(select(func.count()).where(Play.game_id == game_id)) or 0

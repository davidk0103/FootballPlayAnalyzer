from sqlalchemy import func, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app.models import Play, Player, Team


def search_players(
    session: Session,
    *,
    search: str | None,
    season: int | None,
    position: str | None,
    offset: int,
    limit: int,
) -> tuple[list[tuple[Player, int | None]], int]:
    """Players matching a name search, most involved first when a season is given.

    With a season, only players who appear as passer, rusher, or receiver in that
    season are returned, with their play count.
    """
    stmt = select(Player)
    involvement = None
    if season is not None:
        roles = union_all(
            *[
                select(col.label("player_id")).where(Play.season == season, col.is_not(None))
                for col in (Play.passer_player_id, Play.rusher_player_id, Play.receiver_player_id)
            ]
        ).subquery()
        involvement = (
            select(roles.c.player_id, func.count().label("plays"))
            .group_by(roles.c.player_id)
            .subquery()
        )
        stmt = select(Player, involvement.c.plays).join(
            involvement, involvement.c.player_id == Player.id
        )
    if search:
        pattern = f"%{search.strip().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Player.name.ilike(pattern), Player.external_player_id == search))
    if position:
        stmt = stmt.where(func.upper(Player.position) == position.upper())
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (
        [involvement.c.plays.desc(), Player.name]
        if involvement is not None
        else [Player.name, Player.id]
    )
    rows = session.execute(stmt.order_by(*order).offset(offset).limit(limit)).all()
    if involvement is None:
        return [(row[0], None) for row in rows], total
    return [(row[0], int(row._mapping["plays"])) for row in rows], total


def get_player(session: Session, external_id: str) -> Player | None:
    return session.scalar(select(Player).where(Player.external_player_id == external_id))


def game_plays(
    session: Session, game_id: int, *, play_type: str | None, offset: int, limit: int
) -> tuple[list[dict[str, object]], int]:
    off, de = aliased(Team), aliased(Team)
    passer, rusher, receiver = aliased(Player), aliased(Player), aliased(Player)
    base = select(Play.id).where(Play.game_id == game_id)
    if play_type:
        base = base.where(Play.play_type == play_type)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = (
        select(
            Play.external_play_id.label("play_id"),
            Play.qtr,
            Play.game_seconds_remaining,
            off.abbreviation.label("offense"),
            de.abbreviation.label("defense"),
            Play.down,
            Play.yards_to_go,
            Play.yard_line_100,
            Play.score_differential,
            Play.play_type,
            Play.yards_gained,
            Play.epa,
            Play.success,
            Play.touchdown,
            Play.interception,
            Play.fumble_lost,
            Play.penalty,
            passer.name.label("passer"),
            rusher.name.label("rusher"),
            receiver.name.label("receiver"),
        )
        .outerjoin(off, off.id == Play.offense_team_id)
        .outerjoin(de, de.id == Play.defense_team_id)
        .outerjoin(passer, passer.id == Play.passer_player_id)
        .outerjoin(rusher, rusher.id == Play.rusher_player_id)
        .outerjoin(receiver, receiver.id == Play.receiver_player_id)
        .where(Play.game_id == game_id)
    )
    if play_type:
        stmt = stmt.where(Play.play_type == play_type)
    rows = session.execute(stmt.order_by(Play.external_play_id).offset(offset).limit(limit))
    return [dict(r._mapping) for r in rows], total

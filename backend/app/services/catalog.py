"""Teams, games, and seasons lookups."""

from sqlalchemy.orm import Session

from app.models import Team
from app.repositories import games as games_repo
from app.repositories import plays as plays_repo
from app.repositories import teams as teams_repo
from app.schemas import GameDetailOut, GameOut, GamePage, SeasonOut, TeamOut
from app.services.errors import NotFoundError


def list_teams(session: Session) -> list[TeamOut]:
    return [TeamOut.model_validate(t) for t in teams_repo.list_teams(session)]


def require_team(session: Session, key: str) -> Team:
    team = teams_repo.get_team(session, key)
    if team is None:
        raise NotFoundError(f"Team '{key}' not found")
    return team


def get_team(session: Session, key: str) -> TeamOut:
    return TeamOut.model_validate(require_team(session, key))


def list_seasons(session: Session) -> list[SeasonOut]:
    out = []
    for season, plays, games in plays_repo.season_summaries(session):
        dataset = plays_repo.latest_dataset(session, season)
        if dataset is None:
            continue
        out.append(
            SeasonOut(
                season=season,
                plays=plays,
                games=games,
                dataset_version=dataset.source_version,
                sha256=dataset.sha256,
            )
        )
    return out


def list_games(
    session: Session,
    *,
    season: int | None,
    week: int | None,
    team: str | None,
    page: int,
    page_size: int,
) -> GamePage:
    team_id = require_team(session, team).id if team else None
    games, total = games_repo.list_games(
        session,
        season=season,
        week=week,
        team_id=team_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return GamePage(
        items=[GameOut.model_validate(g) for g in games],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_game(session: Session, game_id: int) -> GameDetailOut:
    game = games_repo.get_game(session, game_id)
    if game is None:
        raise NotFoundError(f"Game {game_id} not found")
    base = GameOut.model_validate(game)
    return GameDetailOut(
        **base.model_dump(), play_count=games_repo.count_game_plays(session, game.id)
    )

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Team


def list_teams(session: Session) -> list[Team]:
    return list(session.scalars(select(Team).order_by(Team.abbreviation)))


def get_team(session: Session, key: str) -> Team | None:
    """Look a team up by numeric id or abbreviation (case-insensitive)."""
    if key.isdigit():
        return session.get(Team, int(key))
    return session.scalar(select(Team).where(Team.abbreviation == key.upper()))

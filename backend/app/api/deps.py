import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.analytics.filters import Distance, FieldZone, PlayFilters, PlayType, SeasonType, Side
from app.cache import AnalyticsCache, get_cache
from app.db import get_session
from app.jobs.service import Enqueue
from app.services.errors import InvalidRequestError

SessionDep = Annotated[Session, Depends(get_session)]
CacheDep = Annotated[AnalyticsCache, Depends(get_cache)]


def get_enqueue() -> Enqueue:
    from app.jobs.queue import enqueue_import

    def enqueue(job_id: uuid.UUID, timeout_seconds: int) -> str:
        return enqueue_import(job_id, timeout_seconds=timeout_seconds)

    return enqueue


EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]


def play_filters(
    season: Annotated[int, Query(ge=1999, le=2100, description="Season year, e.g. 2024")],
    side: Annotated[Side, Query(description="Team's plays on offense or allowed on defense")] = (
        Side.OFFENSE
    ),
    season_type: Annotated[SeasonType | None, Query(description="REG or POST")] = None,
    down: Annotated[list[int] | None, Query(description="Down(s) 1-4")] = None,
    distance: Annotated[
        Distance | None, Query(description="Yards to go: short 1-3, medium 4-7, long 8+")
    ] = None,
    field_zone: Annotated[
        FieldZone | None,
        Query(description="yardline_100: own_deep 80-99, own 50-79, opp 21-49, red_zone 1-20"),
    ] = None,
    qtr: Annotated[list[int] | None, Query(description="Quarter(s) 1-5 (5 = overtime)")] = None,
    play_type: Annotated[PlayType | None, Query(description="pass or run")] = None,
) -> PlayFilters:
    downs = tuple(sorted(set(down or [])))
    qtrs = tuple(sorted(set(qtr or [])))
    if any(d not in (1, 2, 3, 4) for d in downs):
        raise InvalidRequestError("down must be between 1 and 4")
    if any(q not in (1, 2, 3, 4, 5) for q in qtrs):
        raise InvalidRequestError("qtr must be between 1 and 5")
    return PlayFilters(
        season=season,
        side=side,
        season_type=season_type,
        down=downs,
        distance=distance,
        field_zone=field_zone,
        qtr=qtrs,
        play_type=play_type,
    )


FiltersDep = Annotated[PlayFilters, Depends(play_filters)]

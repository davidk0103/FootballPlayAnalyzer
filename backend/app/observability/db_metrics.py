"""SQLAlchemy event hooks for per-statement latency histograms."""

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.observability.metrics import DB_LATENCY, DB_QUERIES


def _operation(statement: str) -> str:
    head = statement.lstrip().split(None, 1)
    return head[0].upper() if head else "OTHER"


def install_db_metrics(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _before(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        conn.info.setdefault("piq_query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        starts = conn.info.get("piq_query_start")
        if not starts:
            return
        elapsed = time.perf_counter() - starts.pop()
        op = _operation(statement)
        DB_QUERIES.labels(operation=op).inc()
        DB_LATENCY.labels(operation=op).observe(elapsed)

"""Prometheus metrics for HTTP, jobs, cache, database, and queue depth."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "piq_http_requests_total",
    "HTTP requests",
    ["method", "route", "status_class"],
)
HTTP_LATENCY = Histogram(
    "piq_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_ERRORS = Counter(
    "piq_http_errors_total",
    "HTTP responses with status >= 500",
    ["method", "route"],
)

CACHE_LOOKUPS = Counter(
    "piq_cache_lookups_total",
    "Analytics cache lookups by outcome",
    ["result"],
)

DB_QUERIES = Counter("piq_db_queries_total", "SQL statements executed", ["operation"])
DB_LATENCY = Histogram(
    "piq_db_query_duration_seconds",
    "SQL statement duration",
    ["operation"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)

JOBS_STARTED = Counter("piq_jobs_started_total", "Job attempts started", ["task_type"])
JOBS_FINISHED = Counter(
    "piq_jobs_finished_total",
    "Job terminal outcomes",
    ["task_type", "outcome"],
)
JOB_DURATION = Histogram(
    "piq_job_duration_seconds",
    "Wall time for a job attempt until success or permanent failure",
    ["task_type"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 900),
)

QUEUE_DEPTH = Gauge("piq_queue_depth", "Jobs waiting in PostgreSQL", ["status"])
CELERY_QUEUE = Gauge("piq_celery_redis_queue_length", "Messages waiting in the Celery Redis list")


def status_class(code: int) -> str:
    return f"{code // 100}xx"


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return str(route.path)
    path = request.url.path
    if path.startswith("/api/v1/"):
        return "/api/v1/*"
    return path


def record_cache_result(result: str) -> None:
    CACHE_LOOKUPS.labels(result=result.lower()).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def refresh_queue_gauges(session_factory: Callable[[], Any], broker_url: str) -> None:
    """Called when /metrics is scraped so queue depth reflects the current moment."""
    from sqlalchemy import func, select

    from app.jobs.state import JobStatus
    from app.models import Job

    try:
        import redis

        client = redis.Redis.from_url(broker_url, socket_connect_timeout=0.2, socket_timeout=0.2)
        QUEUE_DEPTH.labels(status="queued").set(0)
        QUEUE_DEPTH.labels(status="retrying").set(0)
        QUEUE_DEPTH.labels(status="running").set(0)
        with session_factory() as session:
            rows = session.execute(
                select(Job.status, func.count())
                .where(
                    Job.status.in_(
                        [JobStatus.QUEUED, JobStatus.RETRYING, JobStatus.RUNNING],
                    )
                )
                .group_by(Job.status)
            ).all()
            for status, count in rows:
                QUEUE_DEPTH.labels(status=status.value).set(int(count))
        queued = client.llen("celery")
        CELERY_QUEUE.set(int(queued) if isinstance(queued, int) else 0)
    except Exception:
        pass


async def prometheus_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path == "/metrics":
        return await call_next(request)
    route = route_template(request)
    method = request.method
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    HTTP_REQUESTS.labels(
        method=method, route=route, status_class=status_class(response.status_code)
    ).inc()
    HTTP_LATENCY.labels(method=method, route=route).observe(elapsed)
    if response.status_code >= 500:
        HTTP_ERRORS.labels(method=method, route=route).inc()
    return response

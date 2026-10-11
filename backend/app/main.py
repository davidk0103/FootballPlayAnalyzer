from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.analytics_routes import router as analytics_router
from app.api.auth_routes import router as auth_router
from app.api.errors import csrf_middleware, install_error_handlers, request_id_middleware
from app.api.report_routes import router as report_router
from app.api.routes import api, health
from app.api.upload_routes import router as upload_router
from app.config import get_settings
from app.db import get_sessionmaker
from app.observability import configure_logging
from app.observability.metrics import metrics_payload, prometheus_middleware, refresh_queue_gauges


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.check_secrets()
    app = FastAPI(
        title="PlaybookIQ API",
        version="0.2.0",
        description=(
            "Team, situational, and player analytics on nflverse play-by-play data, plus "
            "private CSV uploads and saved scouting reports. Unsafe requests require the "
            f"`{settings.csrf_header_name}: 1` header; private endpoints require a session "
            "cookie from /api/v1/auth/login."
        ),
    )
    # Middleware added last runs first: request id -> CORS -> CSRF -> routes.
    app.middleware("http")(csrf_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key", settings.csrf_header_name],
        expose_headers=["X-Request-ID", "X-Cache", "Retry-After", "Content-Disposition"],
    )
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(prometheus_middleware)
    install_error_handlers(app)

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        def prometheus_metrics() -> Response:
            refresh_queue_gauges(get_sessionmaker, settings.broker_url)
            body, content_type = metrics_payload()
            return Response(content=body, media_type=content_type)

    app.include_router(health)
    app.include_router(auth_router)
    app.include_router(api)
    app.include_router(analytics_router)
    app.include_router(upload_router)
    app.include_router(report_router)
    return app


app = create_app()

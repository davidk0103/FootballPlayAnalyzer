from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers, request_id_middleware
from app.api.routes import api, health
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="PlaybookIQ API",
        version="0.1.0",
        description="Team analytics on nflverse play-by-play data.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_id_middleware)
    install_error_handlers(app)
    app.include_router(health)
    app.include_router(api)
    return app


app = create_app()

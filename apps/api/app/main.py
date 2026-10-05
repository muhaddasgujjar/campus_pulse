"""FastAPI application factory and ASGI entry point (`uvicorn app.main:app`)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, public
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import create_redis
from app.db.session import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Clients are created lazily and only when configured, so the app starts with no
        # cloud services at all (local dev, CI, Render cold start).
        app.state.db_engine = (
            create_engine(settings.database_url) if settings.database_url else None
        )
        app.state.redis = create_redis(settings)
        log.info(
            "startup",
            env=settings.app_env,
            institution=settings.institution_slug,
            database="configured" if app.state.db_engine else "not_configured",
            redis="configured" if app.state.redis else "not_configured",
        )
        try:
            yield
        finally:
            if app.state.redis is not None:
                await app.state.redis.aclose()
            if app.state.db_engine is not None:
                await app.state.db_engine.dispose()

    app = FastAPI(
        title="Campus Pulse AI API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(public.router)
    return app


app = create_app()

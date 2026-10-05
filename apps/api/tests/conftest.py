"""Shared fixtures. Unit tests never touch the network or real env files."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides: Any) -> Settings:
    """Settings with no cloud services, ignoring any .env file and env vars for these keys."""
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": None,
        "database_url_migrations": None,
        "redis_url": None,
        "supabase_url": None,
        "gemini_api_key": None,
        "cors_origins": ["http://localhost:3000"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@asynccontextmanager
async def running_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app lifespan (startup/shutdown) around an in-process HTTP client."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async with running_client(create_app(settings)) as http:
        yield http

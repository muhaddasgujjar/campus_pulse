"""Public REST endpoints under /api (no auth): GET /api/config (ADP-2, CHAT-6, CHAT-8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import Institution
from app.services.chat import ChatServices

router = APIRouter(prefix="/api", tags=["public"])
log = get_logger("public")


class PublicConfig(BaseModel):
    institution_slug: str
    institution_name: str | None = None
    short_name: str | None = None
    disclaimer: str
    starter_questions: list[str] = []


@router.get("/config", response_model=PublicConfig)
async def public_config(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> PublicConfig:
    """Institution text for the web app. Never returns secrets. Without a database (or if it
    is unreachable) the page still loads: starter questions are then empty."""
    config = PublicConfig(
        institution_slug=settings.institution_slug, disclaimer=settings.institution_disclaimer
    )
    services: ChatServices | None = getattr(request.app.state, "chat", None)
    if services is None or services.sessionmaker is None:
        return config
    try:
        async with services.sessionmaker() as session:
            institution = (
                await session.execute(
                    select(Institution).where(Institution.slug == settings.institution_slug)
                )
            ).scalar_one_or_none()
    except (OperationalError, DBAPIError, OSError) as exc:
        log.warning("config_database_unavailable", error=type(exc).__name__)
        return config
    if institution is None:
        return config
    extra = dict(institution.config or {})
    questions = [str(q) for q in extra.get("starter_questions") or []][:6]
    return config.model_copy(
        update={
            "institution_name": institution.name,
            "short_name": extra.get("short_name"),
            "starter_questions": questions,
        }
    )

"""Public REST endpoints under /api (no auth). M1: GET /api/config only."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api", tags=["public"])


class PublicConfig(BaseModel):
    institution_slug: str
    disclaimer: str


@router.get("/config", response_model=PublicConfig)
async def public_config(settings: Annotated[Settings, Depends(get_settings)]) -> PublicConfig:
    """Institution text for the web app (ADP-2). Never returns secrets."""
    return PublicConfig(
        institution_slug=settings.institution_slug,
        disclaimer=settings.institution_disclaimer,
    )

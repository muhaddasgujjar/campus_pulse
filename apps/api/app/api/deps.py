"""Shared FastAPI dependencies: database session, institution, signed-in user, RBAC (rule 5).

Every admin route depends on `require(action)`, so the check runs on the server whatever the
UI shows. 401 = no or bad token; 403 = signed in but not allowed.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, AuthError, TokenVerifier
from app.core.config import Settings, get_settings
from app.core.rbac import Action, allowed
from app.services.accounts import AccountError, resolve_user
from app.services.chat import ChatServices
from app.services.content_admin import ContentError, institution_id_for


def chat_services(request: Request) -> ChatServices:
    services: ChatServices = request.app.state.chat
    return services


async def db_session(
    services: Annotated[ChatServices, Depends(chat_services)],
) -> AsyncIterator[AsyncSession]:
    if services.sessionmaker is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not configured")
    async with services.sessionmaker() as session:
        yield session


Session = Annotated[AsyncSession, Depends(db_session)]


def token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.auth
    return verifier


async def institution_id(
    request: Request, session: Session, settings: Annotated[Settings, Depends(get_settings)]
) -> uuid.UUID:
    """The configured institution's id, looked up once and cached on the app."""
    cached: uuid.UUID | None = getattr(request.app.state, "institution_id", None)
    if cached is not None:
        return cached
    try:
        found = await institution_id_for(session, settings.institution_slug)
    except ContentError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await session.commit()
    request.app.state.institution_id = found
    return found


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def authenticate(
    token: str | None, verifier: TokenVerifier, session: AsyncSession, inst: uuid.UUID
) -> AuthenticatedUser:
    if token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "sign in required", {"WWW-Authenticate": "Bearer"}
        )
    try:
        claims = await verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid or expired token", {"WWW-Authenticate": "Bearer"}
        ) from exc
    try:
        return await resolve_user(session, claims, inst)
    except AccountError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


async def current_user(
    request: Request,
    session: Session,
    verifier: Annotated[TokenVerifier, Depends(token_verifier)],
    inst: Annotated[uuid.UUID, Depends(institution_id)],
) -> AuthenticatedUser:
    return await authenticate(bearer_token(request), verifier, session, inst)


async def optional_user(
    request: Request,
    session: Session,
    verifier: Annotated[TokenVerifier, Depends(token_verifier)],
    inst: Annotated[uuid.UUID, Depends(institution_id)],
) -> AuthenticatedUser | None:
    """No token = anonymous (chat is open to everyone). A bad token is still a 401."""
    token = bearer_token(request)
    return None if token is None else await authenticate(token, verifier, session, inst)


async def read_capped(request: Request, max_bytes: int, too_large: str) -> bytes:
    """Read a raw request body (uploads without multipart), refusing more than max_bytes."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, too_large)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, too_large)
    return bytes(body)


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(optional_user)]


def require(action: Action) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Dependency factory: the signed-in user, if their role may perform `action`."""

    async def dependency(user: CurrentUser) -> AuthenticatedUser:
        if not allowed(user.role, action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for your role")
        return user

    return dependency


StaffUser = Annotated[AuthenticatedUser, Depends(require("edit_content"))]
AdminApprover = Annotated[AuthenticatedUser, Depends(require("approve_content"))]

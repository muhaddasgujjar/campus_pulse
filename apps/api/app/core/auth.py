"""Supabase JWT verification (AUTH-2, D16).

- Supabase access tokens are verified here: signature, expiry, audience and issuer.
  HS256 tokens use the legacy JWT secret (SUPABASE_JWT_SECRET). Asymmetric tokens (ES256,
  RS256: the newer Supabase signing keys) use the project's public JWKS.
- The token only proves *who* the user is. The role comes from `profiles.role` on the server
  (app.services.accounts), never from token claims or user-editable metadata.
- With nothing configured, every token fails closed.
- Local laptop only (DEV_AUTH, refused outside APP_ENV=local/test): `issue_dev_token` signs HS256
  tokens with SUPABASE_JWT_SECRET so the portal works without a Supabase project.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import jwt

from app.core.config import Settings

Role = Literal["anonymous", "student", "staff", "admin"]

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
DEV_ISSUER = "campus-pulse-local"
DEV_TOKEN_SECONDS = 8 * 3600


class AuthError(Exception):
    """The token is missing, invalid or cannot be verified. Maps to HTTP 401."""


@dataclass(frozen=True)
class TokenClaims:
    """What a verified token proves. Deliberately has no role."""

    user_id: uuid.UUID
    is_anonymous: bool
    email: str | None


@dataclass(frozen=True)
class AuthenticatedUser:
    """A signed-in person with the role read from `profiles`."""

    user_id: uuid.UUID
    role: Role
    is_anonymous: bool
    institution_id: uuid.UUID
    department_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    email: str | None = None
    full_name: str | None = None

    @property
    def label(self) -> str:
        """Actor label for the audit log."""
        return f"{self.role}:{self.email or self.user_id}"


class KeySource(Protocol):
    def key_for(self, token: str) -> Any: ...


class JwksKeySource:
    """Public keys from the Supabase JWKS endpoint, cached by PyJWKClient."""

    def __init__(self, url: str, timeout: float) -> None:
        self._client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=int(timeout))

    def key_for(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token).key


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._secret = (
            settings.supabase_jwt_secret.get_secret_value()
            if settings.supabase_jwt_secret
            else None
        )
        self._audience = settings.supabase_jwt_audience
        self._dev_auth = settings.dev_auth
        base = settings.supabase_url.rstrip("/") if settings.supabase_url else None
        self.issuer: str | None = f"{base}/auth/v1" if base else None
        self.jwks: KeySource | None = (
            JwksKeySource(f"{self.issuer}/.well-known/jwks.json", settings.supabase_timeout_seconds)
            if self.issuer
            else None
        )

    @property
    def configured(self) -> bool:
        return bool(self._secret or self.jwks)

    async def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        algorithm = header.get("alg")
        key: Any
        if algorithm == "HS256":
            if not self._secret:
                raise AuthError("HS256 tokens are not accepted (no JWT secret configured)")
            key = self._secret
        elif algorithm in ASYMMETRIC_ALGORITHMS and self.jwks is not None:
            try:
                key = await asyncio.to_thread(self.jwks.key_for, token)
            except jwt.PyJWTError as exc:
                raise AuthError("signing key not found") from exc
        else:
            raise AuthError("unsupported token algorithm")

        issuer = self.issuer if self.issuer else DEV_ISSUER if self._dev_auth else None
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=issuer,
                options={"require": ["exp", "sub", "aud"], "verify_iss": issuer is not None},
                leeway=10,
            )
        except jwt.PyJWTError as exc:
            raise AuthError("invalid token") from exc
        try:
            user_id = uuid.UUID(str(payload["sub"]))
        except ValueError as exc:
            raise AuthError("invalid subject") from exc
        email = payload.get("email") or None
        return TokenClaims(
            user_id=user_id,
            is_anonymous=bool(payload.get("is_anonymous", False)),
            email=str(email) if email else None,
        )

    def issue_dev_token(self, user_id: uuid.UUID, *, email: str | None, is_anonymous: bool) -> str:
        """Local laptop only (DEV_AUTH). Same shape as a Supabase access token."""
        if not (self._dev_auth and self._secret):
            raise AuthError("dev tokens are disabled")
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "aud": self._audience,
            "iss": self.issuer or DEV_ISSUER,
            "iat": now,
            "exp": now + DEV_TOKEN_SECONDS,
            "role": "authenticated",
            "is_anonymous": is_anonymous,
        }
        if email:
            payload["email"] = email
        return jwt.encode(payload, self._secret, algorithm="HS256")

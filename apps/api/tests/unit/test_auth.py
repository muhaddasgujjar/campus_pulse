"""Supabase JWT verification (AUTH-2). Written before the code. Tokens are made in the test with
fake secrets and a throwaway EC key; nothing touches the network."""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.auth import AuthError, TokenVerifier
from tests.conftest import make_settings

SECRET = "test-jwt-secret-that-is-long-enough-for-hs256"
SUPABASE_URL = "https://example-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


def claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    values: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
        "role": "authenticated",
        "email": "dr.test@example.edu",
        "is_anonymous": False,
    }
    values.update(overrides)
    return {k: v for k, v in values.items() if v is not None}


def hs_token(**overrides: Any) -> str:
    return jwt.encode(claims(**overrides), SECRET, algorithm="HS256")


def verifier(**settings: Any) -> TokenVerifier:
    values = {"supabase_url": SUPABASE_URL, "supabase_jwt_secret": SECRET}
    values.update(settings)
    return TokenVerifier(make_settings(**values))


async def test_valid_hs256_token() -> None:
    sub = str(uuid.uuid4())
    result = await verifier().verify(hs_token(sub=sub))
    assert str(result.user_id) == sub
    assert result.email == "dr.test@example.edu"
    assert result.is_anonymous is False


async def test_anonymous_sign_in_token_is_marked_anonymous() -> None:
    result = await verifier().verify(hs_token(is_anonymous=True, email=None))
    assert result.is_anonymous is True
    assert result.email is None


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("expired", {"exp": int(time.time()) - 10}),
        ("wrong audience", {"aud": "something-else"}),
        ("wrong issuer", {"iss": "https://evil.example/auth/v1"}),
        ("no subject", {"sub": None}),
        ("subject is not a uuid", {"sub": "admin"}),
        ("no expiry", {"exp": None}),
    ],
)
async def test_rejected_claims(label: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(AuthError):
        await verifier().verify(hs_token(**overrides))


async def test_wrong_secret_is_rejected() -> None:
    token = jwt.encode(claims(), "another-secret-that-is-also-long-enough", algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier().verify(token)


async def test_unsigned_token_is_rejected() -> None:
    token = jwt.encode(claims(), key=None, algorithm="none")
    with pytest.raises(AuthError):
        await verifier().verify(token)


async def test_garbage_is_rejected() -> None:
    with pytest.raises(AuthError):
        await verifier().verify("not-a-jwt")


async def test_role_claims_in_the_token_are_ignored() -> None:
    """The role comes from `profiles` on the server, never from the token (AUTH-2)."""
    result = await verifier().verify(
        hs_token(
            role="service_role", app_metadata={"role": "admin"}, user_metadata={"role": "admin"}
        )
    )
    assert not hasattr(result, "role")


async def test_without_any_key_configured_every_token_fails_closed() -> None:
    v = TokenVerifier(make_settings(supabase_url=None, supabase_jwt_secret=None))
    assert not v.configured
    with pytest.raises(AuthError):
        await v.verify(hs_token())


async def test_hs256_without_a_secret_is_rejected_even_with_jwks() -> None:
    """With only asymmetric keys configured, an HS256 token cannot be trusted."""
    with pytest.raises(AuthError):
        await verifier(supabase_jwt_secret=None).verify(hs_token())


class FakeJwks:
    """Stands in for PyJWKClient: returns the public key for the token's kid."""

    def __init__(self, keys: dict[str, Any]) -> None:
        self.keys = keys

    def key_for(self, token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self.keys:
            raise jwt.PyJWKClientError("unknown kid")
        return self.keys[kid]


async def test_es256_token_verified_with_jwks() -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    v = verifier(supabase_jwt_secret=None)
    v.jwks = FakeJwks({"key-1": private.public_key()})
    sub = str(uuid.uuid4())
    token = jwt.encode(claims(sub=sub), private, algorithm="ES256", headers={"kid": "key-1"})
    assert str((await v.verify(token)).user_id) == sub


async def test_es256_token_with_an_unknown_key_is_rejected() -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    v = verifier(supabase_jwt_secret=None)
    v.jwks = FakeJwks({})
    token = jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "key-9"})
    with pytest.raises(AuthError):
        await v.verify(token)


async def test_dev_token_round_trip_without_supabase() -> None:
    """Local dev (no Supabase project): api-local signs HS256 tokens with a local secret."""
    v = TokenVerifier(make_settings(supabase_url=None, supabase_jwt_secret=SECRET, dev_auth=True))
    sub = uuid.uuid4()
    token = v.issue_dev_token(sub, email="dr.test@example.edu", is_anonymous=False)
    result = await v.verify(token)
    assert result.user_id == sub


def test_dev_auth_is_refused_outside_local_and_test() -> None:
    with pytest.raises(ValueError, match="DEV_AUTH"):
        make_settings(app_env="prod", dev_auth=True, supabase_jwt_secret=SECRET)


def test_dev_tokens_cannot_be_issued_when_dev_auth_is_off() -> None:
    with pytest.raises(AuthError):
        verifier().issue_dev_token(uuid.uuid4(), email=None, is_anonymous=True)

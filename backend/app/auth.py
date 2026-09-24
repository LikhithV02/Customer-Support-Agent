"""Authentication: signed JWTs issued by the host site.

The customer's identity comes *only* from a verified token (`sub` = customer
id). The agent never "verifies" anyone from chat text, so a user cannot claim
to be someone else by typing their email.

Supported verification:
- HS256 with a shared secret (`JWT_SECRET`), or
- RS256/ES256 via the issuer's JWKS endpoint (`JWT_JWKS_URL`).

Claims: `sub` (customer id, or admin user id), optional `role` ("customer" by
default, or "admin"), `exp` (required), and `iss`/`aud` when configured. An
admin token may carry `scope` (a customer id): it then only sees that
customer's conversations. The public demo issues such scoped admin tokens so
each visitor can inspect their own agent traces and nobody else's.

`AUTH_MODE=dev` additionally exposes `POST /api/dev/token` so the local demo and
load tests can mint tokens; in production that route does not exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request

from app.config import get_settings

ROLE_CUSTOMER = "customer"
ROLE_ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str
    # Admin tokens only: restrict visibility to this customer's data.
    scope: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class AuthError(Exception):
    pass


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Caches keys in-process; refetches on unknown `kid`.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def decode_token(token: str) -> Principal:
    settings = get_settings()
    options = {"require": ["exp", "sub"]}
    kwargs: dict = {}
    if settings.jwt_audience:
        kwargs["audience"] = settings.jwt_audience
    else:
        options["verify_aud"] = False
    if settings.jwt_issuer:
        kwargs["issuer"] = settings.jwt_issuer
    try:
        if settings.jwt_jwks_url:
            key = _jwks_client(settings.jwt_jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256", "ES256"], options=options, **kwargs
            )
        else:
            secret = settings.effective_jwt_secret
            if not secret:
                raise AuthError("server has no JWT verification key configured")
            claims = jwt.decode(
                token, secret, algorithms=["HS256"], options=options, **kwargs
            )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc

    role = claims.get("role", ROLE_CUSTOMER)
    if role not in (ROLE_CUSTOMER, ROLE_ADMIN):
        raise AuthError("unknown role")
    scope = claims.get("scope")
    return Principal(sub=str(claims["sub"]), role=role, scope=str(scope) if scope else None)


def mint_token(
    sub: str, role: str = ROLE_CUSTOMER, ttl_s: int | None = None, scope: str | None = None
) -> str:
    """Sign an HS256 token with the configured secret (dev, tests, load tests)."""
    settings = get_settings()
    now = int(time.time())
    claims = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + (ttl_s or settings.dev_token_ttl_s),
    }
    if scope:
        claims["scope"] = scope
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    return jwt.encode(claims, settings.effective_jwt_secret, algorithm="HS256")


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


def principal_from_request(request: Request) -> Principal | None:
    """Best-effort decode without raising (used for rate-limit keys, logging)."""
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    token = bearer_token(request)
    if not token:
        return None
    try:
        principal = decode_token(token)
    except AuthError:
        return None
    request.state.principal = principal
    return principal


async def get_principal(request: Request) -> Principal:
    token = bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        principal = decode_token(token)
    except AuthError:
        raise HTTPException(
            status_code=401,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    request.state.principal = principal
    return principal


async def require_customer(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != ROLE_CUSTOMER:
        raise HTTPException(status_code=403, detail="customer token required")
    return principal


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin token required")
    return principal

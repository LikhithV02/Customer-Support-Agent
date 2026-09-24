"""Shared helpers for the load test: config, token minting, SSE reading."""

from __future__ import annotations

import itertools
import json
import os
import time

import jwt

# Must match the backend's JWT_SECRET (the dev default is used by compose).
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-0123456789")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")
# Number of synthetic customers created by `scripts/seed_synthetic.py`.
CUSTOMER_COUNT = int(os.getenv("LT_CUSTOMERS", "10000"))

_counter = itertools.count()


def mint(sub: str, role: str = "customer", ttl_s: int = 4 * 3600) -> str:
    now = int(time.time())
    claims = {"sub": sub, "role": role, "iat": now, "exp": now + ttl_s}
    if JWT_ISSUER:
        claims["iss"] = JWT_ISSUER
    if JWT_AUDIENCE:
        claims["aud"] = JWT_AUDIENCE
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def next_customer_id(runner) -> str:
    """Hand every simulated user its own synthetic customer.

    Unique across distributed workers: worker i takes ids i, i+W, i+2W, …
    """
    index = getattr(runner, "worker_index", 0) or 0
    count = max(getattr(runner, "worker_count", 1) or 1, int(os.getenv("LT_WORKERS", "1")))
    n = next(_counter) * count + index
    return f"LT-{(n % CUSTOMER_COUNT) + 1:06d}"


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def iter_sse(response):
    """Yield decoded JSON events from a streaming FastHttp response."""
    data_lines: list[str] = []
    while True:
        raw = response.readline()
        if not raw:  # connection closed
            if data_lines:
                yield json.loads("\n".join(data_lines))
            return
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if data_lines:
                yield json.loads("\n".join(data_lines))
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        # ignore comments (": ping") and other fields

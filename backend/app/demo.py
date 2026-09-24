"""Public demo sandboxes (`AUTH_MODE=demo`).

Anyone can try the live agent without an account: `POST /api/demo/session`
creates a throwaway customer with one order per refund-policy branch and hands
back two short-lived tokens:

- a **customer** token for the chat (identity still comes only from the token —
  the same code path as production), and
- a **scoped admin** token (`scope` = that customer) for the admin dashboard,
  so the visitor can watch their own agent traces and nobody else's.

Abuse controls: sandbox creation is rate limited per client IP (and optionally
gated by Cloudflare Turnstile); chat keeps its normal per-customer rate limit,
turn cap and concurrency cap; LLM spend is capped per visitor and demo-wide
(turns fall back to the scripted model once spent — see `agent/runner.py`);
sandboxes are purged after `DEMO_DATA_TTL_HOURS` by the retention job.
"""

from __future__ import annotations

import logging
import random
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import redis as shared
from app.auth import ROLE_ADMIN, ROLE_CUSTOMER, mint_token
from app.config import get_settings
from app.db import session as db
from app.db.fixtures import scenario_for, scenario_orders
from app.db.models import Customer
from app.observability import REJECTIONS, log_event
from app.schemas import OrderOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_PREFIX = "DM-"
_TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class DemoSessionRequest(BaseModel):
    turnstile_token: str | None = None


class DemoCustomer(BaseModel):
    id: str
    name: str
    email: str


class DemoSession(BaseModel):
    customer: DemoCustomer
    orders: list[OrderOut]
    token: str
    admin_token: str
    expires_in: int
    data_ttl_hours: int


def client_ip(request: Request) -> str:
    """The caller's IP, honouring `TRUSTED_PROXY_HOPS` X-Forwarded-For entries.

    Each trusted proxy appends the address it saw, so the real client is the
    Nth entry from the right; anything further left is client-controlled.
    """
    hops = get_settings().trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for", "")
    if hops > 0 and forwarded:
        chain = [p.strip() for p in forwarded.split(",") if p.strip()]
        if chain:
            return chain[max(0, len(chain) - hops)]
    return request.client.host if request.client else "unknown"


def new_demo_customer_id() -> str:
    # Digits only, so ids look like the order ids the agent is used to.
    return f"{DEMO_PREFIX}{secrets.randbelow(10**10):010d}"


async def _verify_turnstile(token: str | None, ip: str) -> bool:
    secret = get_settings().turnstile_secret
    if not secret:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            res = await http.post(
                _TURNSTILE_URL, data={"secret": secret, "response": token, "remoteip": ip}
            )
        return bool(res.json().get("success"))
    except (httpx.HTTPError, ValueError):
        log_event(logger, "turnstile verification unavailable", level=logging.WARNING)
        return False


async def _create_sandbox() -> tuple[Customer, list]:
    for _ in range(5):
        cid = new_demo_customer_id()
        customer = Customer(
            id=cid, name="Demo Shopper", email=f"{cid.lower()}@demo.acme.test"
        )
        orders = scenario_orders(cid, random.Random())
        try:
            async with db.SessionLocal() as session:
                session.add(customer)
                session.add_all(orders)
                await session.commit()
            return customer, orders
        except IntegrityError:  # id collision: astronomically rare, just retry
            continue
    raise HTTPException(status_code=503, detail="could not create a demo sandbox")


def order_out(order) -> OrderOut:
    return OrderOut(
        id=order.id,
        product_name=order.product_name,
        amount=float(order.amount),
        status=order.status,
        order_date=order.order_date,
        delivered_date=order.delivered_date,
        is_final_sale=order.is_final_sale,
        refunded=order.refunded,
        scenario=scenario_for(order.id),
    )


@router.post("/session", response_model=DemoSession)
async def create_session(request: Request, body: DemoSessionRequest | None = None):
    settings = get_settings()
    if not settings.is_demo:
        raise HTTPException(status_code=404, detail="Not Found")

    ip = client_ip(request)
    allowed, reset_in = await shared.hit_rate_limit(
        f"demo-session:ip:{ip}", settings.demo_session_rate_limit
    )
    if not allowed:
        REJECTIONS.labels("demo_rate_limited").inc()
        raise HTTPException(
            status_code=429,
            detail="Too many demo sessions from your network. Please try again later.",
            headers={"Retry-After": str(reset_in)},
        )
    if not await _verify_turnstile(body.turnstile_token if body else None, ip):
        raise HTTPException(status_code=403, detail="bot check failed")

    customer, orders = await _create_sandbox()
    ttl = settings.demo_token_ttl_s
    log_event(logger, "demo session created", customer_id=customer.id)
    return DemoSession(
        customer=DemoCustomer(id=customer.id, name=customer.name, email=customer.email),
        orders=[order_out(o) for o in orders],
        token=mint_token(customer.id, ROLE_CUSTOMER, ttl_s=ttl),
        admin_token=mint_token(f"demo-admin:{customer.id}", ROLE_ADMIN, ttl_s=ttl, scope=customer.id),
        expires_in=ttl,
        data_ttl_hours=settings.demo_data_ttl_hours,
    )

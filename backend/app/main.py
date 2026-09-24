import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sse_starlette.sse import EventSourceResponse

from app import redis as shared
from app.agent.runner import (
    ConversationNotFound,
    create_conversation,
    load_owned_conversation,
    new_conversation_id,
    run_agent_turn,
)
from app.auth import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    Principal,
    mint_token,
    principal_from_request,
    require_admin,
    require_customer,
)
from app.config import get_settings
from app.db import session as db
from app.db.models import Conversation, Customer, Message, ReasoningEvent
from app.db.seed import seed_if_empty
from app.events import broadcaster
from app.observability import (
    REJECTIONS,
    SSE_STREAMS,
    RequestContextMiddleware,
    configure_logging,
    configure_sentry,
    customer_id_var,
    log_event,
)
from app.schemas import (
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    MessageOut,
    ReasoningEventOut,
)

settings = get_settings()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    configure_sentry()
    if settings.seed_on_startup:
        await seed_if_empty(create_tables=True)
    log_event(logger, "startup", env=settings.env, llm_provider=settings.llm_provider)
    yield
    await shared.close_redis()
    await db.dispose()


app = FastAPI(title="ACME Refund Support Agent", lifespan=lifespan)

# In Docker/k8s the SPA is same-origin (nginx/ingress route /api), so CORS is
# only needed when embedding the widget on another origin — allowlist those.
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
app.add_middleware(RequestContextMiddleware, max_body_bytes=settings.max_request_bytes)


@app.exception_handler(Exception)
async def _unhandled(_request: Request, exc: Exception):
    log_event(
        logger,
        "unhandled error",
        level=logging.ERROR,
        error_type=type(exc).__name__,
        error=str(exc)[:500],
    )
    return JSONResponse(status_code=500, content={"detail": "internal error"})


# ---------------------------------------------------------------------------
# Health & metrics
# ---------------------------------------------------------------------------


@app.get("/api/health")
@app.get("/api/health/live")
async def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_key_configured": settings.has_llm_key,
    }


@app.get("/api/health/ready")
async def ready() -> Response:
    checks = {}
    try:
        async with db.SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised in k8s
        checks["db"] = f"error: {type(exc).__name__}"
    try:
        await shared.get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["redis"] = f"error: {type(exc).__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, **checks})


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Dev-only token minting (AUTH_MODE=dev). In production this route 404s and
# tokens are issued by the host site.
# ---------------------------------------------------------------------------


class DevTokenRequest(BaseModel):
    customer_id: str | None = None
    admin: bool = False


@app.post("/api/dev/token")
async def dev_token(req: DevTokenRequest) -> dict:
    if settings.auth_mode != "dev" or settings.env == "prod":
        raise HTTPException(status_code=404, detail="Not Found")
    if req.admin:
        return {"token": mint_token("dev-admin", ROLE_ADMIN), "role": ROLE_ADMIN}
    if not req.customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    async with db.SessionLocal() as session:
        if await session.get(Customer, req.customer_id) is None:
            raise HTTPException(status_code=404, detail="unknown customer")
    return {"token": mint_token(req.customer_id, ROLE_CUSTOMER), "role": ROLE_CUSTOMER}


@app.get("/api/dev/customers")
async def dev_customers() -> list[dict]:
    """Customer picker for the local demo UI."""
    if settings.auth_mode != "dev" or settings.env == "prod":
        raise HTTPException(status_code=404, detail="Not Found")
    async with db.SessionLocal() as session:
        rows = (await session.scalars(select(Customer).order_by(Customer.id).limit(20))).all()
    return [{"id": c.id, "name": c.name, "email": c.email} for c in rows]


# ---------------------------------------------------------------------------
# Customer chat
# ---------------------------------------------------------------------------


def _rate_limit_key(request: Request) -> str:
    principal = principal_from_request(request)
    if principal is not None:
        return f"sub:{principal.sub}"
    # Uvicorn runs with --proxy-headers, so this is the real client IP when
    # the ingress/nginx is a trusted forwarder.
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def enforce_chat_rate_limit(request: Request) -> None:
    allowed, reset_in = await shared.hit_rate_limit(
        f"chat:{_rate_limit_key(request)}", settings.chat_rate_limit
    )
    if not allowed:
        REJECTIONS.labels("rate_limited").inc()
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.chat_rate_limit}",
            headers={"Retry-After": str(reset_in)},
        )


@app.post("/api/chat", dependencies=[Depends(enforce_chat_rate_limit)])
async def chat(req: ChatRequest, principal: Principal = Depends(require_customer)):
    customer_id_var.set(principal.sub)
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    # Guardrail 1: per-message length cap.
    if len(req.message) > settings.max_message_chars:
        REJECTIONS.labels("too_long").inc()
        raise HTTPException(
            status_code=400,
            detail=(
                f"message is too long ({len(req.message)} chars); the limit is "
                f"{settings.max_message_chars}."
            ),
        )

    # Ownership: a client may only continue a conversation it owns. Unknown and
    # foreign ids are both 404 so they can't be probed.
    if req.conversation_id:
        try:
            await load_owned_conversation(principal.sub, req.conversation_id)
        except ConversationNotFound:
            raise HTTPException(status_code=404, detail="conversation not found") from None

        # Guardrail 2: per-conversation turn cap. Counted before the SSE opens
        # so the client gets a real HTTP status, not a half-stream.
        async with db.SessionLocal() as session:
            existing = (
                await session.scalar(
                    select(func.count(Message.id)).where(
                        Message.conversation_id == req.conversation_id
                    )
                )
                or 0
            )
        if existing >= settings.max_conversation_turns:
            REJECTIONS.labels("turn_cap").inc()
            raise HTTPException(
                status_code=429,
                detail=(
                    f"this conversation has reached its message limit "
                    f"({settings.max_conversation_turns}). Please start a new chat."
                ),
            )
        cid = req.conversation_id
        is_new = False
    else:
        cid = new_conversation_id()
        is_new = True

    # One turn at a time per conversation (across all pods).
    lock_ttl = settings.turn_timeout_s + 30
    lock = await shared.acquire_turn_lock(cid, lock_ttl)
    if lock is None:
        REJECTIONS.labels("turn_in_progress").inc()
        raise HTTPException(
            status_code=409, detail="a reply is still being generated for this conversation"
        )

    # Global back-pressure: shed load before the LLM provider starts 429ing.
    slot = await shared.acquire_turn_slot(settings.max_concurrent_turns, lock_ttl)
    if slot is None:
        await shared.release_turn_lock(cid, lock)
        REJECTIONS.labels("overloaded").inc()
        raise HTTPException(
            status_code=503,
            detail="We're experiencing high demand. Please try again shortly.",
            headers={"Retry-After": "5"},
        )

    if is_new:
        await create_conversation(principal.sub, cid)

    async def event_stream():
        SSE_STREAMS.labels("chat").inc()
        try:
            async for event in run_agent_turn(principal.sub, cid, req.message):
                yield {"data": json.dumps(event)}
        finally:
            SSE_STREAMS.labels("chat").dec()
            await shared.release_turn_slot(slot)
            await shared.release_turn_lock(cid, lock)

    return EventSourceResponse(event_stream(), ping=15)


def _messages_out(messages) -> list[MessageOut]:
    return [
        MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
        for m in messages
    ]


@app.get("/api/me/conversations", response_model=list[ConversationSummary])
async def my_conversations(
    principal: Principal = Depends(require_customer),
    limit: int = Query(20, ge=1, le=100),
    before: datetime | None = None,
) -> list[ConversationSummary]:
    return await _conversation_summaries(limit, before, customer_id=principal.sub)


@app.get("/api/me/conversations/{conversation_id}", response_model=ConversationDetail)
async def my_conversation(
    conversation_id: str, principal: Principal = Depends(require_customer)
) -> ConversationDetail:
    try:
        convo = await load_owned_conversation(principal.sub, conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="conversation not found") from None
    async with db.SessionLocal() as session:
        messages = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id)
            )
        ).all()
    return ConversationDetail(
        id=convo.id,
        customer_id=convo.customer_id,
        customer_name=None,
        messages=_messages_out(messages),
        events=[],
    )


# ---------------------------------------------------------------------------
# Admin (requires role=admin)
# ---------------------------------------------------------------------------


async def _conversation_summaries(
    limit: int, before: datetime | None, customer_id: str | None = None
) -> list[ConversationSummary]:
    msg_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_message = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    stmt = (
        select(Conversation, Customer.name, msg_count, last_message)
        .outerjoin(Customer, Customer.id == Conversation.customer_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    if before is not None:
        stmt = stmt.where(Conversation.created_at < before)
    if customer_id is not None:
        stmt = stmt.where(Conversation.customer_id == customer_id)
    async with db.SessionLocal() as session:
        rows = (await session.execute(stmt)).all()
    return [
        ConversationSummary(
            id=c.id,
            customer_id=c.customer_id,
            customer_name=name,
            created_at=c.created_at,
            message_count=count or 0,
            last_message=last,
        )
        for c, name, count, last in rows
    ]


@app.get(
    "/api/conversations",
    response_model=list[ConversationSummary],
    dependencies=[Depends(require_admin)],
)
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None, description="cursor: created_at of last row"),
) -> list[ConversationSummary]:
    return await _conversation_summaries(limit, before)


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetail,
    dependencies=[Depends(require_admin)],
)
async def get_conversation(conversation_id: str) -> ConversationDetail:
    async with db.SessionLocal() as session:
        convo = await session.get(Conversation, conversation_id)
        if convo is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        name = None
        if convo.customer_id:
            cust = await session.get(Customer, convo.customer_id)
            name = cust.name if cust else None
        messages = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id)
            )
        ).all()
        events = (
            await session.scalars(
                select(ReasoningEvent)
                .where(ReasoningEvent.conversation_id == conversation_id)
                .order_by(ReasoningEvent.seq)
            )
        ).all()
    return ConversationDetail(
        id=convo.id,
        customer_id=convo.customer_id,
        customer_name=name,
        messages=_messages_out(messages),
        events=[
            ReasoningEventOut(
                id=e.id,
                seq=e.seq,
                step_type=e.step_type,
                node=e.node,
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@app.get(
    "/api/conversations/{conversation_id}/stream",
    dependencies=[Depends(require_admin)],
)
async def stream_conversation(conversation_id: str):
    """Live reasoning events for a conversation (admin dashboard)."""

    async def event_stream():
        SSE_STREAMS.labels("admin").inc()
        try:
            async for event in broadcaster.subscribe(conversation_id):
                yield {"data": json.dumps(event)}
        finally:
            SSE_STREAMS.labels("admin").dec()

    return EventSourceResponse(event_stream(), ping=15)

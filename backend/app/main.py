import json
from datetime import timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.agent.runner import run_agent_turn
from app.config import get_settings
from app.db.models import Conversation, Customer, Message, ReasoningEvent
from app.db.seed import seed_if_empty
from app.db.session import get_session
from app.events import broadcaster
from app.schemas import (
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    MessageOut,
    ReasoningEventOut,
)

app = FastAPI(title="ACME Refund Support Agent")

# Same-origin in Docker (nginx proxies /api); permissive CORS eases local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    seed_if_empty()


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_key_configured": settings.has_llm_key,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    async def event_stream():
        session = get_session()
        try:
            async for event in run_agent_turn(
                session, req.conversation_id, req.message
            ):
                yield {"data": json.dumps(event)}
        finally:
            session.close()

    return EventSourceResponse(event_stream())


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations() -> list[ConversationSummary]:
    with get_session() as session:
        convos = session.scalars(
            select(Conversation).order_by(Conversation.created_at.desc())
        ).all()
        out: list[ConversationSummary] = []
        for c in convos:
            msgs = c.messages
            name = None
            if c.customer_id:
                cust = session.get(Customer, c.customer_id)
                name = cust.name if cust else None
            out.append(
                ConversationSummary(
                    id=c.id,
                    customer_id=c.customer_id,
                    customer_name=name,
                    created_at=c.created_at,
                    message_count=len(msgs),
                    last_message=msgs[-1].content if msgs else None,
                )
            )
        return out


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str) -> ConversationDetail:
    with get_session() as session:
        convo = session.get(Conversation, conversation_id)
        if convo is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        name = None
        if convo.customer_id:
            cust = session.get(Customer, convo.customer_id)
            name = cust.name if cust else None
        messages = session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        ).all()
        events = session.scalars(
            select(ReasoningEvent)
            .where(ReasoningEvent.conversation_id == conversation_id)
            .order_by(ReasoningEvent.seq)
        ).all()
        return ConversationDetail(
            id=convo.id,
            customer_id=convo.customer_id,
            customer_name=name,
            messages=[
                MessageOut(
                    id=m.id, role=m.role, content=m.content, created_at=m.created_at
                )
                for m in messages
            ],
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


@app.get("/api/conversations/{conversation_id}/stream")
async def stream_conversation(conversation_id: str):
    """Live reasoning events for a conversation (admin dashboard)."""

    async def event_stream():
        queue = broadcaster.subscribe(conversation_id)
        try:
            while True:
                event = await queue.get()
                yield {"data": json.dumps(event)}
        finally:
            broadcaster.unsubscribe(conversation_id, queue)

    return EventSourceResponse(event_stream())

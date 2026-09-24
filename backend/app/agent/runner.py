"""Drives one agent turn and emits reasoning events.

`run_agent_turn` is an async generator: it runs the LangGraph agent over the
conversation, and for every step (model thoughts, tool calls, tool results,
decisions) it persists a ReasoningEvent, publishes it to the live broadcaster
(Redis pub/sub, for the admin dashboard), and yields it to the caller (the
chat SSE stream). The deterministic policy gate lives in the tools; this layer
only observes.

The customer id comes from the verified JWT (see `app/auth.py`) and the
conversation has already been ownership-checked by the endpoint; both are
re-checked here as defence in depth.

DB sessions are opened per write and never held across LLM calls, so a pod's
connection pool is not consumed by idle, long-running streams.

Guardrails enforced here (see `docs/HARDENING.md`):
- A per-conversation **token budget** (`max_conversation_tokens`) and a
  per-customer **daily** budget (`customer_daily_token_budget`): once exceeded,
  the next turn short-circuits with a polite refusal — no model call.
- The LangGraph **recursion limit** (`agent_recursion_limit`) bounds the
  tool-call loop, and `turn_timeout_s` bounds wall-clock time.
- An **output sanitizer**: if the assistant's final message claims a refund was
  approved/processed but no `issue_refund` tool returned `approved` this turn,
  a clear correction note is prepended (and an `output_correction` event is
  emitted). The deterministic gate already protects the money; this extends the
  same guarantee to the chat surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from datetime import timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select, update

from app import redis as shared
from app.agent.graph import build_agent
from app.agent.guard import detect_injection
from app.agent.llm import use_prompt_caching
from app.agent.prompts import get_system_prompt
from app.agent.tools import ToolContext
from app.config import get_settings
from app.db import session as db
from app.db.models import Conversation, Message, ReasoningEvent
from app.events import broadcaster
from app.observability import (
    INJECTION_FLAGS,
    LLM_TOKENS,
    REFUND_DECISIONS,
    TOOL_CALLS,
    TURN_LATENCY,
    TURNS,
    TURNS_IN_FLIGHT,
    conversation_id_var,
    log_event,
)

logger = logging.getLogger(__name__)

# How many prior messages are replayed to the model (bounded prompt size).
_HISTORY_LIMIT = 40

_ERROR_MESSAGE = (
    "Sorry — something went wrong on our side while handling that. "
    "Please try again in a moment."
)

_DECISION_TOOLS = {"issue_refund", "escalate_to_human"}

# Phrases that make an *affirmative* claim a refund was granted. If the agent's
# final reply contains one of these but no `issue_refund` returned "approved"
# this turn, the sanitizer prepends a correction.
#
# These must be affirmative success phrasings — NOT bare words like "approved"
# or "refunded" — so that legitimate denials ("this order has already been
# refunded") and escalations ("it cannot be approved automatically") don't trip
# the sanitizer. The intervening-word structure also naturally excludes negated
# forms ("has not been approved"), since the negation breaks "has been approved".
_APPROVAL_CLAIM = re.compile(
    r"(?:"
    # "your/the refund [of $X] has been | is | was approved|processed|issued|…"
    r"(?:your |the )?refund(?:\s+of\s+\$[\d,.]+)?\s+(?:has been|is|was)\s+"
    r"(?:approved|processed|issued|completed|refunded)"
    # "successfully | now approved|processed|issued|refunded"
    r"|(?:successfully|now)\s+(?:approved|processed|issued|refunded)"
    # "I've | I have approved|processed|issued (your|the) refund"
    r"|i(?:'ve| have)\s+(?:approved|processed|issued)\s+(?:your |the )?refund"
    # "approved|processed|issued your refund"
    r"|(?:approved|processed|issued)\s+your\s+refund"
    r")",
    re.I,
)

_BUDGET_MESSAGE = (
    "I'm sorry, this conversation has reached its usage limit for the day. "
    "Please start a new chat or contact a human specialist if you still need help."
)

_CORRECTION_PREFIX = (
    "_System note: the refund system did not record this as approved. "
    "Please disregard any approval language below — the database is the "
    "source of truth._\n\n"
)


class ConversationNotFound(Exception):
    pass


def new_conversation_id() -> str:
    return f"conv-{uuid.uuid4().hex}"


async def create_conversation(customer_id: str, cid: str | None = None) -> str:
    cid = cid or new_conversation_id()
    async with db.SessionLocal() as session:
        session.add(Conversation(id=cid, customer_id=customer_id))
        await session.commit()
    return cid


async def load_owned_conversation(customer_id: str, conversation_id: str) -> Conversation:
    """Return the conversation if it belongs to `customer_id`, else raise.

    Unknown and foreign conversations are indistinguishable to the caller, so
    ids can't be probed.
    """
    async with db.SessionLocal() as session:
        convo = await session.get(Conversation, conversation_id)
    if convo is None or convo.customer_id != customer_id:
        raise ConversationNotFound(conversation_id)
    return convo


async def _history(conversation_id: str) -> list:
    async with db.SessionLocal() as session:
        rows = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc())
                .limit(_HISTORY_LIMIT)
            )
        ).all()
    return [
        HumanMessage(m.content) if m.role == "user" else AIMessage(m.content)
        for m in reversed(rows)
    ]


def _system_message() -> SystemMessage:
    prompt = get_system_prompt()
    if use_prompt_caching():
        # Cache breakpoint on the system prompt: tools + system are the stable
        # prefix of every request, so repeat turns read them from cache.
        return SystemMessage(
            content=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
        )
    return SystemMessage(prompt)


def _step_type_for_tool(name: str) -> str:
    if name == "check_refund_eligibility":
        return "policy_eval"
    if name in _DECISION_TOOLS:
        return "decision"
    return "tool_result"


async def _save_message(cid: str, role: str, content: str) -> int:
    async with db.SessionLocal() as session:
        msg = Message(conversation_id=cid, role=role, content=content)
        session.add(msg)
        await session.commit()
        return msg.id


async def run_agent_turn(
    customer_id: str, conversation_id: str | None, user_text: str
) -> AsyncIterator[dict]:
    settings = get_settings()
    started = time.perf_counter()
    if conversation_id is None:
        conversation_id = await create_conversation(customer_id)
    convo = await load_owned_conversation(customer_id, conversation_id)
    cid = convo.id
    conversation_id_var.set(cid)

    # Persist the user's message first so it survives reloads.
    user_msg_id = await _save_message(cid, "user", user_text)
    # Mirror it to live admin subscribers (not yielded to the chat stream, which
    # already renders the user's own message locally).
    await broadcaster.publish(cid, {"kind": "message", "role": "user", "content": user_text})

    async def emit(step_type: str, node: str, payload: dict, tokens: int = 0) -> dict:
        async with db.SessionLocal() as session:
            # Atomic per-conversation sequence number (safe across pods).
            values = {"event_seq": Conversation.event_seq + 1}
            if tokens:
                values["tokens_used"] = Conversation.tokens_used + tokens
            seq = await session.scalar(
                update(Conversation)
                .where(Conversation.id == cid)
                .values(**values)
                .returning(Conversation.event_seq)
            )
            row = ReasoningEvent(
                conversation_id=cid,
                message_id=user_msg_id,
                seq=seq,
                step_type=step_type,
                node=node,
                payload=payload,
            )
            session.add(row)
            await session.commit()
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        event = {
            "kind": "step",
            "id": row.id,
            "seq": seq,
            "step_type": step_type,
            "node": node,
            "payload": payload,
            "created_at": created.isoformat(),
        }
        await broadcaster.publish(cid, event)
        return event

    async def finish(final_text: str, outcome: str) -> list[dict]:
        await _save_message(cid, "assistant", final_text)
        final_event = {"kind": "message", "role": "assistant", "content": final_text}
        await broadcaster.publish(cid, final_event)
        TURNS.labels(outcome).inc()
        TURN_LATENCY.observe(time.perf_counter() - started)
        return [final_event, {"kind": "done"}]

    yield {"kind": "conversation", "conversation_id": cid}

    # Surface (but do not rely on) suspected manipulation.
    flags = detect_injection(user_text)
    if flags:
        INJECTION_FLAGS.inc()
        yield await emit("injection_flag", "guard", {"patterns": flags, "text": user_text})

    # Token budgets. Refuse before any LLM call.
    prior_tokens = convo.tokens_used or 0
    today_tokens = await shared.customer_tokens_today(customer_id)
    if (
        prior_tokens >= settings.max_conversation_tokens
        or today_tokens >= settings.customer_daily_token_budget
    ):
        yield await emit(
            "budget_exhausted",
            "guard",
            {
                "prior_tokens": prior_tokens,
                "limit": settings.max_conversation_tokens,
                "customer_tokens_today": today_tokens,
                "customer_daily_limit": settings.customer_daily_token_budget,
            },
        )
        for event in await finish(_BUDGET_MESSAGE, "budget_exhausted"):
            yield event
        return

    ctx = ToolContext(conversation_id=cid, verified_customer_id=customer_id)
    agent = build_agent(ctx)

    # History already includes the user message we just saved.
    messages = [_system_message()] + await _history(cid)

    final_text = ""
    approved_in_turn = False
    TURNS_IN_FLIGHT.inc()
    try:
        async with asyncio.timeout(settings.turn_timeout_s):
            async for chunk in agent.astream(
                {"messages": messages},
                stream_mode="updates",
                config={"recursion_limit": settings.agent_recursion_limit},
            ):
                for node, update_ in chunk.items():
                    for msg in update_.get("messages", []):
                        if isinstance(msg, AIMessage):
                            usage = getattr(msg, "usage_metadata", None)
                            if isinstance(msg.content, str) and msg.content.strip():
                                yield await emit("model", node, {"text": msg.content})
                                final_text = msg.content
                            elif isinstance(msg.content, list):
                                text = "".join(
                                    b.get("text", "")
                                    for b in msg.content
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                                if text.strip():
                                    yield await emit("model", node, {"text": text})
                                    final_text = text
                            for call in msg.tool_calls or []:
                                TOOL_CALLS.labels(call["name"]).inc()
                                yield await emit(
                                    "tool_call",
                                    node,
                                    {"tool": call["name"], "args": call.get("args", {})},
                                )
                            # Record token usage for budget tracking.
                            if usage:
                                tin = int(usage.get("input_tokens", 0))
                                tout = int(usage.get("output_tokens", 0))
                                LLM_TOKENS.labels("input").inc(tin)
                                LLM_TOKENS.labels("output").inc(tout)
                                await shared.add_customer_tokens(customer_id, tin + tout)
                                yield await emit(
                                    "usage",
                                    node,
                                    {"input_tokens": tin, "output_tokens": tout},
                                    tokens=tin + tout,
                                )
                        elif isinstance(msg, ToolMessage):
                            try:
                                result = json.loads(msg.content)
                            except (json.JSONDecodeError, TypeError):
                                result = {"raw": str(msg.content)}
                            # Track whether this turn actually approved a refund —
                            # the output sanitizer relies on it.
                            if msg.name in _DECISION_TOOLS and isinstance(result, dict):
                                decision = result.get("decision")
                                if decision:
                                    REFUND_DECISIONS.labels(decision).inc()
                                if msg.name == "issue_refund" and decision == "approved":
                                    approved_in_turn = True
                            yield await emit(
                                _step_type_for_tool(msg.name),
                                node,
                                {"tool": msg.name, "result": result},
                            )
    except Exception as exc:  # model/provider errors, timeouts, recursion limit
        # Full detail goes to logs; the client gets a generic message.
        log_event(
            logger,
            "agent turn failed",
            level=logging.ERROR,
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        TURNS.labels("error").inc()
        TURN_LATENCY.observe(time.perf_counter() - started)
        yield await emit("error", "agent", {"error_type": type(exc).__name__})
        yield {"kind": "error", "message": _ERROR_MESSAGE}
        return
    finally:
        TURNS_IN_FLIGHT.dec()

    if not final_text:
        final_text = "I'm sorry, I wasn't able to complete that request."

    # Output sanitizer: don't let the assistant *claim* an approval that the
    # refund system did not actually record.
    if not approved_in_turn and _APPROVAL_CLAIM.search(final_text):
        yield await emit(
            "output_correction",
            "sanitizer",
            {
                "reason": "Assistant claimed an approval that issue_refund did not "
                "produce this turn.",
                "original": final_text,
            },
        )
        final_text = _CORRECTION_PREFIX + final_text

    for event in await finish(final_text, "ok"):
        yield event

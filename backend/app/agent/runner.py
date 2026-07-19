"""Drives one agent turn and emits reasoning events.

`run_agent_turn` is an async generator: it runs the LangGraph agent over the
conversation, and for every step (model thoughts, tool calls, tool results,
decisions) it persists a ReasoningEvent, publishes it to the live broadcaster
(for the admin dashboard), and yields it to the caller (the chat SSE stream).
The deterministic policy gate lives in the tools; this layer only observes.

It also enforces three guardrails (see `docs/HARDENING.md`):
- A per-conversation **token budget** (`max_conversation_tokens`): once
  cumulative LLM tokens for this conversation exceed the budget, the next turn
  short-circuits with a polite refusal — no model call.
- The LangGraph **recursion limit** (`agent_recursion_limit`) bounds the
  tool-call loop on each turn.
- An **output sanitizer**: if the assistant's final message claims a refund was
  approved/processed but no `issue_refund` tool returned `approved` this turn,
  a clear correction note is prepended (and an `output_correction` event is
  emitted). The deterministic gate already protects the money; this extends the
  same guarantee to the chat surface.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.graph import build_agent
from app.agent.guard import detect_injection
from app.agent.prompts import get_system_prompt
from app.agent.tools import ToolContext
from app.config import get_settings
from app.db.models import Conversation, Message, ReasoningEvent
from app.events import broadcaster

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


def get_or_create_conversation(session: Session, conversation_id: str | None) -> Conversation:
    if conversation_id:
        convo = session.get(Conversation, conversation_id)
        if convo:
            return convo
    convo = Conversation(id=conversation_id or f"conv-{uuid.uuid4().hex[:12]}")
    session.add(convo)
    session.commit()
    return convo


def _history(session: Session, conversation_id: str) -> list:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id)
    ).all()
    out: list = []
    for m in rows:
        out.append(HumanMessage(m.content) if m.role == "user" else AIMessage(m.content))
    return out


def _step_type_for_tool(name: str) -> str:
    if name == "check_refund_eligibility":
        return "policy_eval"
    if name in _DECISION_TOOLS:
        return "decision"
    return "tool_result"


def _sum_prior_tokens(session: Session, cid: str) -> int:
    """Sum input + output tokens from previous `usage` events on this conversation."""
    rows = session.scalars(
        select(ReasoningEvent).where(
            ReasoningEvent.conversation_id == cid,
            ReasoningEvent.step_type == "usage",
        )
    ).all()
    total = 0
    for row in rows:
        p = row.payload or {}
        total += int(p.get("input_tokens", 0)) + int(p.get("output_tokens", 0))
    return total


async def run_agent_turn(
    session: Session, conversation_id: str | None, user_text: str
) -> AsyncIterator[dict]:
    settings = get_settings()
    convo = get_or_create_conversation(session, conversation_id)
    cid = convo.id

    seq = session.scalar(
        select(func.count(ReasoningEvent.id)).where(
            ReasoningEvent.conversation_id == cid
        )
    ) or 0

    # Persist the user's message first so it survives reloads.
    user_msg = Message(conversation_id=cid, role="user", content=user_text)
    session.add(user_msg)
    session.commit()
    # Mirror it to live admin subscribers (not yielded to the chat stream, which
    # already renders the user's own message locally).
    broadcaster.publish(cid, {"kind": "message", "role": "user", "content": user_text})

    def emit(step_type: str, node: str, payload: dict) -> dict:
        nonlocal seq
        seq += 1
        row = ReasoningEvent(
            conversation_id=cid,
            message_id=user_msg.id,
            seq=seq,
            step_type=step_type,
            node=node,
            payload=payload,
        )
        session.add(row)
        session.commit()
        event = {
            "kind": "step",
            "id": row.id,
            "seq": seq,
            "step_type": step_type,
            "node": node,
            "payload": payload,
            "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        }
        broadcaster.publish(cid, event)
        return event

    yield {"kind": "conversation", "conversation_id": cid}

    # Surface (but do not rely on) suspected manipulation.
    flags = detect_injection(user_text)
    if flags:
        yield emit("injection_flag", "guard", {"patterns": flags, "text": user_text})

    # Per-conversation token budget. Refuse before any LLM call.
    prior_tokens = _sum_prior_tokens(session, cid)
    if prior_tokens >= settings.max_conversation_tokens:
        yield emit(
            "budget_exhausted",
            "guard",
            {
                "prior_tokens": prior_tokens,
                "limit": settings.max_conversation_tokens,
            },
        )
        final_text = _BUDGET_MESSAGE
        assistant_msg = Message(conversation_id=cid, role="assistant", content=final_text)
        session.add(assistant_msg)
        session.commit()
        final_event = {"kind": "message", "role": "assistant", "content": final_text}
        broadcaster.publish(cid, final_event)
        yield final_event
        yield {"kind": "done"}
        return

    ctx = ToolContext(session=session, conversation_id=cid, verified_customer_id=convo.customer_id)
    agent = build_agent(ctx)

    messages = [SystemMessage(get_system_prompt())] + _history(session, cid)
    messages.append(HumanMessage(user_text))

    final_text = ""
    approved_in_turn = False
    try:
        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="updates",
            config={"recursion_limit": settings.agent_recursion_limit},
        ):
            for node, update in chunk.items():
                for msg in update.get("messages", []):
                    if isinstance(msg, AIMessage):
                        if isinstance(msg.content, str) and msg.content.strip():
                            yield emit("model", node, {"text": msg.content})
                            final_text = msg.content
                        for call in msg.tool_calls or []:
                            yield emit(
                                "tool_call",
                                node,
                                {"tool": call["name"], "args": call.get("args", {})},
                            )
                        # Record token usage for budget tracking.
                        usage = getattr(msg, "usage_metadata", None)
                        if usage:
                            yield emit(
                                "usage",
                                node,
                                {
                                    "input_tokens": int(usage.get("input_tokens", 0)),
                                    "output_tokens": int(usage.get("output_tokens", 0)),
                                },
                            )
                    elif isinstance(msg, ToolMessage):
                        try:
                            result = json.loads(msg.content)
                        except (json.JSONDecodeError, TypeError):
                            result = {"raw": str(msg.content)}
                        # Track whether this turn actually approved a refund —
                        # the output sanitizer relies on it.
                        if (
                            msg.name == "issue_refund"
                            and isinstance(result, dict)
                            and result.get("decision") == "approved"
                        ):
                            approved_in_turn = True
                        yield emit(
                            _step_type_for_tool(msg.name),
                            node,
                            {"tool": msg.name, "result": result},
                        )
    except Exception as exc:  # surface model/provider errors to the UI
        yield emit("error", "agent", {"message": str(exc)})
        yield {"kind": "error", "message": str(exc)}
        return

    if not final_text:
        final_text = "I'm sorry, I wasn't able to complete that request."

    # Output sanitizer: don't let the assistant *claim* an approval that the
    # refund system did not actually record.
    if not approved_in_turn and _APPROVAL_CLAIM.search(final_text):
        yield emit(
            "output_correction",
            "sanitizer",
            {
                "reason": "Assistant claimed an approval that issue_refund did not "
                "produce this turn.",
                "original": final_text,
            },
        )
        final_text = _CORRECTION_PREFIX + final_text

    assistant_msg = Message(conversation_id=cid, role="assistant", content=final_text)
    session.add(assistant_msg)
    session.commit()

    final_event = {"kind": "message", "role": "assistant", "content": final_text}
    broadcaster.publish(cid, final_event)
    yield final_event
    yield {"kind": "done"}

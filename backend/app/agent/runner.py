"""Drives one agent turn and emits reasoning events.

`run_agent_turn` is an async generator: it runs the LangGraph agent over the
conversation, and for every step (model thoughts, tool calls, tool results,
decisions) it persists a ReasoningEvent, publishes it to the live broadcaster
(for the admin dashboard), and yields it to the caller (the chat SSE stream).
The deterministic policy gate lives in the tools; this layer only observes.
"""

from __future__ import annotations

import json
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
from app.db.models import Conversation, Message, ReasoningEvent
from app.events import broadcaster

_DECISION_TOOLS = {"issue_refund", "escalate_to_human"}


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


async def run_agent_turn(
    session: Session, conversation_id: str | None, user_text: str
) -> AsyncIterator[dict]:
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

    # Surface (but do not rely on) suspected manipulation.
    flags = detect_injection(user_text)
    if flags:
        yield emit("injection_flag", "guard", {"patterns": flags, "text": user_text})

    yield {"kind": "conversation", "conversation_id": cid}

    ctx = ToolContext(session=session, conversation_id=cid, verified_customer_id=convo.customer_id)
    agent = build_agent(ctx)

    messages = [SystemMessage(get_system_prompt())] + _history(session, cid)
    messages.append(HumanMessage(user_text))

    final_text = ""
    try:
        async for chunk in agent.astream({"messages": messages}, stream_mode="updates"):
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
                    elif isinstance(msg, ToolMessage):
                        try:
                            result = json.loads(msg.content)
                        except (json.JSONDecodeError, TypeError):
                            result = {"raw": str(msg.content)}
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

    assistant_msg = Message(conversation_id=cid, role="assistant", content=final_text)
    session.add(assistant_msg)
    session.commit()

    final_event = {"kind": "message", "role": "assistant", "content": final_text}
    broadcaster.publish(cid, final_event)
    yield final_event
    yield {"kind": "done"}

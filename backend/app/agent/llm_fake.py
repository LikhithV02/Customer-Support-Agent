"""Scripted, tool-calling fake chat model for load tests and e2e checks.

It behaves like a well-behaved agent: it reads the customer's latest message,
picks the right tool sequence (list orders → check eligibility → issue refund
or escalate) and writes a final reply. Each call sleeps for a latency drawn
from a log-normal distribution around `latency_ms`, and fails with probability
`error_rate`, so load tests see realistic long-lived SSE streams and error
paths — without spending any tokens.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import re
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_ORDER_RE = re.compile(r"\bORD-[A-Z0-9-]+\b", re.I)
_REFUND_RE = re.compile(r"\b(refund|return|money back)\b", re.I)
_ORDERS_RE = re.compile(r"\b(orders?|purchases?|bought)\b", re.I)


class FakeLLMError(RuntimeError):
    pass


def _call(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:12]}", "type": "tool_call"}


class ScriptedFakeChatModel:
    def __init__(self, latency_ms: int = 1500, error_rate: float = 0.0):
        self.latency_ms = latency_ms
        self.error_rate = error_rate

    def bind_tools(self, _tools):
        return self

    async def _sleep(self) -> None:
        if self.latency_ms <= 0:
            return
        # Log-normal with median = latency_ms, sigma 0.4 (p95 ≈ 1.9× median).
        seconds = random.lognormvariate(math.log(self.latency_ms / 1000), 0.4)
        await asyncio.sleep(min(seconds, 30.0))

    async def ainvoke(self, messages, *args, **kwargs) -> AIMessage:
        await self._sleep()
        if self.error_rate and random.random() < self.error_rate:
            raise FakeLLMError("simulated provider error")
        msg = self._decide(messages)
        chars = sum(len(str(getattr(m, "content", ""))) for m in messages)
        msg.usage_metadata = {
            "input_tokens": chars // 4,
            "output_tokens": 40,
            "total_tokens": chars // 4 + 40,
        }
        return msg

    def _decide(self, messages) -> AIMessage:
        # Only this turn matters: everything after the latest human message.
        last_human = max(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1
        )
        text = str(messages[last_human].content) if last_human >= 0 else ""
        turn = messages[last_human + 1 :]
        results: dict[str, dict] = {}
        for m in turn:
            if isinstance(m, ToolMessage):
                try:
                    results[m.name] = json.loads(m.content)
                except (TypeError, json.JSONDecodeError):
                    results[m.name] = {}

        order_match = _ORDER_RE.search(text)
        wants_refund = bool(_REFUND_RE.search(text))

        if "issue_refund" in results:
            r = results["issue_refund"]
            if r.get("decision") == "approved":
                return AIMessage(
                    content=f"Your refund of ${r.get('amount', 0):.2f} for order "
                    f"{r.get('order_id')} has been approved."
                )
            return AIMessage(
                content="I'm sorry, I couldn't approve that refund: "
                + " ".join(r.get("reasons", []) or [r.get("error", "")])
            )
        if "escalate_to_human" in results:
            return AIMessage(
                content="This refund needs a specialist's review, so I've escalated it. "
                "A human will follow up shortly."
            )
        if "check_refund_eligibility" in results:
            r = results["check_refund_eligibility"]
            oid = r.get("order_id") or (order_match.group(0).upper() if order_match else "")
            if r.get("error"):
                return AIMessage(content=f"I couldn't find that order on your account ({r['error']}).")
            if r.get("decision") == "approved":
                return AIMessage(content="", tool_calls=[_call("issue_refund", {"order_id": oid})])
            if r.get("decision") == "escalated":
                return AIMessage(
                    content="",
                    tool_calls=[
                        _call(
                            "escalate_to_human",
                            {"order_id": oid, "reason": "Amount exceeds auto-approval limit."},
                        )
                    ],
                )
            return AIMessage(
                content="I'm sorry, this order isn't eligible for a refund: "
                + " ".join(r.get("reasons", []))
            )
        if "list_orders" in results:
            orders = results["list_orders"].get("orders", [])
            if wants_refund and orders:
                return AIMessage(
                    content="",
                    tool_calls=[
                        _call("check_refund_eligibility", {"order_id": orders[0]["order_id"]})
                    ],
                )
            listing = ", ".join(f"{o['order_id']} ({o['product_name']})" for o in orders)
            return AIMessage(content=f"Here are your orders: {listing or 'none found'}.")

        if "get_order" in results:
            return AIMessage(content=f"Here are the details: {json.dumps(results['get_order'])}")

        # First step of the turn.
        if order_match:
            oid = order_match.group(0).upper()
            if wants_refund:
                return AIMessage(
                    content="", tool_calls=[_call("check_refund_eligibility", {"order_id": oid})]
                )
            return AIMessage(content="", tool_calls=[_call("get_order", {"order_id": oid})])
        if wants_refund or _ORDERS_RE.search(text):
            return AIMessage(content="", tool_calls=[_call("list_orders", {})])
        return AIMessage(
            content="I can only help with refund requests for ACME Store orders. "
            "Is there an order you'd like me to look up?"
        )

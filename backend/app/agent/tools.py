"""Agent tools.

These are the only way the agent can touch data or money. The critical safety
property lives in `issue_refund`: it re-runs the deterministic policy engine and
can only record an *approved* refund when the policy says so. Nothing the model
says — including text injected by a malicious user — can override that gate.

Tools are built per request via `build_tools`, closing over a `ToolContext` that
holds the DB session and the identity verified so far in this conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Customer, Order, Refund
from app.policy.engine import evaluate


@dataclass
class ToolContext:
    session: Session
    conversation_id: str
    verified_customer_id: str | None = None


def _order_view(order: Order) -> dict:
    return {
        "order_id": order.id,
        "product_name": order.product_name,
        "category": order.category,
        "amount": order.amount,
        "status": order.status,
        "delivered_date": order.delivered_date.date().isoformat()
        if order.delivered_date
        else None,
        "is_final_sale": order.is_final_sale,
        "already_refunded": order.refunded,
    }


def build_tools(ctx: ToolContext) -> list:
    session = ctx.session

    def _require_identity() -> str | None:
        if ctx.verified_customer_id is None:
            return json.dumps(
                {
                    "error": "identity_not_verified",
                    "message": "You must verify the customer's identity with "
                    "lookup_customer before accessing orders or issuing refunds.",
                }
            )
        return None

    def _get_owned_order(order_id: str) -> tuple[Order | None, str | None]:
        order = session.get(Order, order_id)
        if order is None:
            return None, json.dumps(
                {"error": "order_not_found", "order_id": order_id}
            )
        if order.customer_id != ctx.verified_customer_id:
            # Ownership guard — never reveal or act on another customer's order.
            return None, json.dumps(
                {
                    "error": "ownership_mismatch",
                    "message": f"Order {order_id} does not belong to the verified "
                    "customer. Refusing.",
                }
            )
        return order, None

    @tool
    async def lookup_customer(email: str | None = None, name: str | None = None) -> str:
        """Verify a customer's identity and load their profile.

        Provide the customer's email (preferred) or full name. This MUST be called
        and succeed before any order can be viewed or refunded. Returns the
        customer's id, name, email and loyalty tier, or a not-found result.
        """
        customer: Customer | None = None
        if email:
            customer = session.scalar(
                select(Customer).where(func.lower(Customer.email) == email.lower())
            )
        if customer is None and name:
            customer = session.scalar(
                select(Customer).where(func.lower(Customer.name) == name.lower())
            )
        if customer is None:
            return json.dumps(
                {"found": False, "message": "No customer matched that email or name."}
            )

        # Bind the verified identity to this conversation (persists across turns).
        ctx.verified_customer_id = customer.id
        convo = session.get(Conversation, ctx.conversation_id)
        if convo is not None:
            convo.customer_id = customer.id
        session.commit()

        return json.dumps(
            {
                "found": True,
                "customer_id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "loyalty_tier": customer.loyalty_tier,
            }
        )

    @tool
    async def list_orders() -> str:
        """List all orders belonging to the currently verified customer."""
        guard = _require_identity()
        if guard:
            return guard
        orders = session.scalars(
            select(Order).where(Order.customer_id == ctx.verified_customer_id)
        ).all()
        return json.dumps({"orders": [_order_view(o) for o in orders]})

    @tool
    async def get_order(order_id: str) -> str:
        """Get the details of a single order belonging to the verified customer."""
        guard = _require_identity()
        if guard:
            return guard
        order, err = _get_owned_order(order_id)
        if err:
            return err
        return json.dumps(_order_view(order))

    @tool
    async def check_refund_eligibility(order_id: str) -> str:
        """Check whether an order is eligible for a refund WITHOUT issuing one.

        Runs the deterministic refund policy and returns eligibility, whether the
        refund requires human escalation, and the reasons. Use this before
        deciding what to tell the customer.
        """
        guard = _require_identity()
        if guard:
            return guard
        order, err = _get_owned_order(order_id)
        if err:
            return err
        customer = session.get(Customer, ctx.verified_customer_id)
        result = evaluate(order, customer)
        return json.dumps({"order_id": order_id, **result.to_dict()})

    @tool
    async def issue_refund(order_id: str) -> str:
        """Attempt to issue a refund for an order.

        This is the only way to actually grant a refund. The refund is re-validated
        against the policy here; an approved refund is recorded ONLY when the policy
        permits it. Final-sale, out-of-window, already-refunded, or >$500 requests
        will be recorded as denied or escalated — never approved.
        """
        guard = _require_identity()
        if guard:
            return guard
        order, err = _get_owned_order(order_id)
        if err:
            return err

        customer = session.get(Customer, ctx.verified_customer_id)
        result = evaluate(order, customer)
        decision = result.decision  # approved | denied | escalated

        refund = Refund(
            order_id=order.id,
            amount=order.amount,
            decision=decision,
            reason=" ".join(result.reasons),
            decided_by="agent",
        )
        session.add(refund)
        if decision == "approved":
            order.refunded = True
        session.commit()

        return json.dumps(
            {
                "order_id": order_id,
                "decision": decision,
                "refund_recorded": True,
                "amount": order.amount if decision == "approved" else 0.0,
                "reasons": result.reasons,
            }
        )

    @tool
    async def escalate_to_human(order_id: str, reason: str) -> str:
        """Escalate a refund request to a human specialist.

        Use this for refunds over $500 or any case the policy cannot auto-approve.
        Records the escalation; a human will follow up with the customer.
        """
        guard = _require_identity()
        if guard:
            return guard
        order, err = _get_owned_order(order_id)
        if err:
            return err
        refund = Refund(
            order_id=order.id,
            amount=order.amount,
            decision="escalated",
            reason=reason,
            decided_by="agent",
        )
        session.add(refund)
        session.commit()
        return json.dumps(
            {
                "order_id": order_id,
                "decision": "escalated",
                "message": "Escalated to a human specialist for manual review.",
            }
        )

    return [
        lookup_customer,
        list_orders,
        get_order,
        check_refund_eligibility,
        issue_refund,
        escalate_to_human,
    ]

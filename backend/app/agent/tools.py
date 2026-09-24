"""Agent tools.

These are the only way the agent can touch data or money. The critical safety
property lives in `issue_refund`: it re-runs the deterministic policy engine and
can only record an *approved* refund when the policy says so. Nothing the model
says — including text injected by a malicious user — can override that gate.

Identity is NOT established by the agent. The customer id comes from the
verified JWT on the request and is fixed in `ToolContext` before the agent
runs, so the model can only ever see or act on that customer's orders.

Each tool call opens its own short-lived DB session, so no connection is held
while the model is thinking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session as db
from app.db.models import Customer, Order, Refund
from app.policy.engine import evaluate


@dataclass
class ToolContext:
    conversation_id: str
    verified_customer_id: str | None = None


def _order_view(order: Order) -> dict:
    return {
        "order_id": order.id,
        "product_name": order.product_name,
        "category": order.category,
        "amount": float(order.amount),
        "status": order.status,
        "delivered_date": order.delivered_date.date().isoformat()
        if order.delivered_date
        else None,
        "is_final_sale": order.is_final_sale,
        "already_refunded": order.refunded,
    }


def build_tools(ctx: ToolContext) -> list:
    def _require_identity() -> str | None:
        if ctx.verified_customer_id is None:
            return json.dumps(
                {
                    "error": "identity_not_verified",
                    "message": "No authenticated customer on this conversation.",
                }
            )
        return None

    async def _get_owned_order(
        session, order_id: str, for_update: bool = False
    ) -> tuple[Order | None, str | None]:
        stmt = select(Order).where(Order.id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        order = await session.scalar(stmt)
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
    async def get_my_profile() -> str:
        """Load the authenticated customer's profile (name, email, loyalty tier).

        The customer is already signed in; you never need to ask who they are.
        """
        guard = _require_identity()
        if guard:
            return guard
        async with db.SessionLocal() as session:
            customer = await session.get(Customer, ctx.verified_customer_id)
        if customer is None:
            return json.dumps({"found": False, "message": "Customer profile not found."})
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
        """List all orders belonging to the signed-in customer."""
        guard = _require_identity()
        if guard:
            return guard
        async with db.SessionLocal() as session:
            orders = (
                await session.scalars(
                    select(Order)
                    .where(Order.customer_id == ctx.verified_customer_id)
                    .order_by(Order.order_date.desc())
                    .limit(50)
                )
            ).all()
        return json.dumps({"orders": [_order_view(o) for o in orders]})

    @tool
    async def get_order(order_id: str) -> str:
        """Get the details of a single order belonging to the signed-in customer."""
        guard = _require_identity()
        if guard:
            return guard
        async with db.SessionLocal() as session:
            order, err = await _get_owned_order(session, order_id)
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
        async with db.SessionLocal() as session:
            order, err = await _get_owned_order(session, order_id)
            if err:
                return err
            customer = await session.get(Customer, ctx.verified_customer_id)
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

        async with db.SessionLocal() as session:
            # Row lock: concurrent refund attempts on the same order serialise
            # here, so the second one sees `refunded=True` and is denied.
            order, err = await _get_owned_order(session, order_id, for_update=True)
            if err:
                return err
            customer = await session.get(Customer, ctx.verified_customer_id)
            result = evaluate(order, customer)
            decision = result.decision  # approved | denied | escalated
            reasons = list(result.reasons)
            amount = order.amount

            session.add(
                Refund(
                    order_id=order.id,
                    amount=amount,
                    decision=decision,
                    reason=" ".join(reasons),
                    decided_by="agent",
                    conversation_id=ctx.conversation_id,
                )
            )
            if decision == "approved":
                order.refunded = True
            try:
                await session.commit()
            except IntegrityError:
                # Unique index backstop: another request approved this order
                # first (e.g. on a DB without row locks). Record a denial.
                await session.rollback()
                decision = "denied"
                reasons = [f"Order {order_id} has already been refunded."]
                session.add(
                    Refund(
                        order_id=order_id,
                        amount=amount,
                        decision=decision,
                        reason=reasons[0],
                        decided_by="agent",
                        conversation_id=ctx.conversation_id,
                    )
                )
                await session.commit()

        return json.dumps(
            {
                "order_id": order_id,
                "decision": decision,
                "refund_recorded": True,
                "amount": float(amount) if decision == "approved" else 0.0,
                "reasons": reasons,
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
        async with db.SessionLocal() as session:
            order, err = await _get_owned_order(session, order_id)
            if err:
                return err
            session.add(
                Refund(
                    order_id=order.id,
                    amount=order.amount,
                    decision="escalated",
                    reason=reason[:1000],
                    decided_by="agent",
                    conversation_id=ctx.conversation_id,
                )
            )
            await session.commit()
        return json.dumps(
            {
                "order_id": order_id,
                "decision": "escalated",
                "message": "Escalated to a human specialist for manual review.",
            }
        )

    return [
        get_my_profile,
        list_orders,
        get_order,
        check_refund_eligibility,
        issue_refund,
        escalate_to_human,
    ]

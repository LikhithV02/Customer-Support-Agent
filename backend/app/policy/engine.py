"""Deterministic refund-policy engine.

This module is the single source of truth for refund eligibility. The LLM may
*propose* a refund, but only this code decides whether one is permitted. Tools
call `evaluate` before committing anything to the database, so a prompt-injected
or jailbroken model still cannot push through a non-compliant refund.

Pure functions, no LLM and no I/O — fully unit-testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.config import get_settings


@dataclass
class PolicyResult:
    eligible: bool
    requires_escalation: bool
    reasons: list[str] = field(default_factory=list)
    refund_amount: float = 0.0

    @property
    def decision(self) -> str:
        """The decision the agent is permitted to record."""
        if not self.eligible:
            return "denied"
        if self.requires_escalation:
            return "escalated"
        return "approved"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision"] = self.decision
        return d


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate(order, customer=None, now: datetime | None = None) -> PolicyResult:
    """Evaluate whether `order` may be refunded.

    Rules are applied as hard gates in priority order. Ownership and delivery
    are validated first, then the policy rules from refund_policy.md.
    """
    settings = get_settings()
    now = _now(now)
    reasons: list[str] = []

    # Rule 5 (identity/ownership): the order must belong to the requester.
    if customer is not None and order.customer_id != customer.id:
        reasons.append(
            f"Order {order.id} does not belong to the requesting customer."
        )
        return PolicyResult(False, False, reasons, order.amount)

    # The item must actually have been delivered before it can be returned.
    delivered = _as_aware(order.delivered_date)
    if order.status != "delivered" or delivered is None:
        reasons.append(
            f"Order {order.id} has not been delivered yet, so it is not eligible "
            "for a refund."
        )
        return PolicyResult(False, False, reasons, order.amount)

    # Rule 4: already refunded.
    if order.refunded:
        reasons.append(f"Order {order.id} has already been refunded.")
        return PolicyResult(False, False, reasons, order.amount)

    # Rule 1: final-sale items are never refundable.
    if order.is_final_sale:
        reasons.append(
            f"'{order.product_name}' was a final-sale item and is non-refundable "
            "under any circumstances."
        )
        return PolicyResult(False, False, reasons, order.amount)

    # Rule 3: return window.
    age_days = (now - delivered).days
    if age_days > settings.return_window_days:
        reasons.append(
            f"Order {order.id} was delivered {age_days} days ago, outside the "
            f"{settings.return_window_days}-day return window."
        )
        return PolicyResult(False, False, reasons, order.amount)

    # Rule 2: high-value refunds require a human.
    if order.amount > settings.escalation_threshold:
        reasons.append(
            f"Refund amount ${order.amount:.2f} exceeds the "
            f"${settings.escalation_threshold:.0f} limit and requires human "
            "escalation."
        )
        return PolicyResult(True, True, reasons, order.amount)

    reasons.append(
        f"Order {order.id} is within the {settings.return_window_days}-day window, "
        "is not final sale, and is below the escalation threshold."
    )
    return PolicyResult(True, False, reasons, order.amount)

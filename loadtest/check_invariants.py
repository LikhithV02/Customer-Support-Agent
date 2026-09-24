"""Post-run correctness check: things that must NEVER be true, however hard
the system was pushed. Run after every load test:

    DATABASE_URL=postgresql://... python check_invariants.py

Exits 1 (and prints the offending rows) on any violation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

RETURN_WINDOW_DAYS = int(os.getenv("RETURN_WINDOW_DAYS", "30"))
ESCALATION_THRESHOLD = float(os.getenv("ESCALATION_THRESHOLD", "500"))

INVARIANTS: dict[str, str] = {
    "double_approved_refund": """
        SELECT order_id, count(*) AS approvals
        FROM refunds WHERE decision = 'approved'
        GROUP BY order_id HAVING count(*) > 1
    """,
    "approved_final_sale": """
        SELECT r.id, r.order_id FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.decision = 'approved' AND o.is_final_sale
    """,
    "approved_over_threshold": f"""
        SELECT r.id, r.order_id, o.amount FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.decision = 'approved' AND o.amount > {ESCALATION_THRESHOLD}
    """,
    "approved_outside_window": f"""
        SELECT r.id, r.order_id FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.decision = 'approved'
          AND r.created_at - o.delivered_date > interval '{RETURN_WINDOW_DAYS + 1} days'
    """,
    # Synthetic orders whose policy outcome is known up front.
    "approved_synthetic_ineligible": """
        SELECT r.id, r.order_id FROM refunds r
        WHERE r.decision = 'approved' AND r.order_id ~ '^LT-[0-9]+-[BCDE]$'
    """,
    "refund_across_customers": """
        SELECT r.id, r.order_id, o.customer_id AS order_owner, c.customer_id AS chat_owner
        FROM refunds r
        JOIN orders o ON o.id = r.order_id
        JOIN conversations c ON c.id = r.conversation_id
        WHERE o.customer_id <> c.customer_id
    """,
    "refunded_flag_without_approval": """
        SELECT o.id FROM orders o
        WHERE o.refunded AND o.id ~ '^LT-[0-9]+-A$'
          AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id = o.id AND r.decision = 'approved')
    """,
    "approval_without_refunded_flag": """
        SELECT r.order_id FROM refunds r JOIN orders o ON o.id = r.order_id
        WHERE r.decision = 'approved' AND NOT o.refunded
    """,
    "unowned_conversation": "SELECT id FROM conversations WHERE customer_id IS NULL",
    "duplicate_event_seq": """
        SELECT conversation_id, seq, count(*) FROM reasoning_events
        GROUP BY conversation_id, seq HAVING count(*) > 1
    """,
}

SUMMARY = {
    "conversations": "SELECT count(*) FROM conversations",
    "messages": "SELECT count(*) FROM messages",
    "reasoning_events": "SELECT count(*) FROM reasoning_events",
    "refunds_by_decision": "SELECT decision, count(*) FROM refunds GROUP BY decision",
}


def _url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/app")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def main() -> int:
    engine = create_async_engine(_url())
    violations: dict[str, list] = {}
    summary: dict = {}
    async with engine.connect() as conn:
        for name, sql in INVARIANTS.items():
            rows = (await conn.execute(text(sql))).all()
            if rows:
                violations[name] = [list(map(str, r)) for r in rows[:20]]
        for name, sql in SUMMARY.items():
            rows = (await conn.execute(text(sql))).all()
            summary[name] = rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 else {
                str(r[0]): r[1] for r in rows
            }
    await engine.dispose()

    print(json.dumps({"summary": summary, "violations": violations}, indent=2, default=str))
    if violations:
        print(f"INVARIANTS FAILED: {', '.join(violations)}", file=sys.stderr)
        return 1
    print(f"INVARIANTS PASSED ({len(INVARIANTS)} checks)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

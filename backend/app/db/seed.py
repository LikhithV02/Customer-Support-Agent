import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import session as db
from app.db.models import Customer, Order, utcnow

SEED_FILE = Path(__file__).resolve().parent / "data" / "seed.json"


def _days_ago(days: int | None):
    if days is None:
        return None
    return utcnow() - timedelta(days=days)


async def seed_if_empty(create_tables: bool = False) -> bool:
    """Load fixture data once. Returns True if data was inserted.

    Order dates are stored relative to 'now' in the fixture (days_ago) and
    converted to absolute timestamps here, so the return-window edge cases
    stay correct regardless of when the app is started.
    """
    if create_tables:
        await db.init_db()
    async with db.SessionLocal() as session:
        existing = await session.scalar(select(Customer).limit(1))
        if existing is not None:
            return False
        _load(session)
        await session.commit()
        return True


def _load(session) -> None:
    """Add fixture rows to `session` (sync or async — only calls `add`)."""
    data = json.loads(SEED_FILE.read_text())
    for c in data["customers"]:
        session.add(
            Customer(
                id=c["id"],
                name=c["name"],
                email=c["email"],
                loyalty_tier=c.get("loyalty_tier", "standard"),
            )
        )
        for o in c.get("orders", []):
            session.add(
                Order(
                    id=o["id"],
                    customer_id=c["id"],
                    product_name=o["product_name"],
                    category=o.get("category", "general"),
                    amount=Decimal(str(o["amount"])),
                    status=o.get("status", "delivered"),
                    order_date=_days_ago(o.get("order_days_ago")),
                    delivered_date=_days_ago(o.get("delivered_days_ago")),
                    is_final_sale=o.get("is_final_sale", False),
                    refunded=o.get("refunded", False),
                )
            )


if __name__ == "__main__":
    inserted = asyncio.run(seed_if_empty())
    print(f"Seeded database from {SEED_FILE}" if inserted else "Database already seeded")

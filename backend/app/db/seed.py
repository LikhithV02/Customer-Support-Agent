import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Customer, Order, utcnow
from app.db.session import SessionLocal, init_db

SEED_FILE = Path(__file__).resolve().parent / "data" / "seed.json"


def _days_ago(days: int | None):
    if days is None:
        return None
    return utcnow() - timedelta(days=days)


def seed_if_empty() -> None:
    """Create tables and load fixture data once.

    Order dates are stored relative to 'now' in the fixture (days_ago) and
    converted to absolute timestamps here, so the return-window edge cases
    stay correct regardless of when the app is started.
    """
    init_db()
    with SessionLocal() as session:
        existing = session.scalar(select(Customer).limit(1))
        if existing is not None:
            return
        _load(session)
        session.commit()


def _load(session: Session) -> None:
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
                    amount=o["amount"],
                    status=o.get("status", "delivered"),
                    order_date=_days_ago(o.get("order_days_ago")),
                    delivered_date=_days_ago(o.get("delivered_days_ago")),
                    is_final_sale=o.get("is_final_sale", False),
                    refunded=o.get("refunded", False),
                )
            )


if __name__ == "__main__":
    seed_if_empty()
    print(f"Seeded database from {SEED_FILE}")

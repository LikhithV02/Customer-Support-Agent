"""Generate synthetic customers + orders for load testing.

Every simulated user gets their own identity and a mix of orders that hits
every policy branch, so load is spread across rows the way real traffic is
(instead of 5 seed customers all contending for the same rows).

    python -m scripts.seed_synthetic --customers 10000

Customer ids are LT-000001 … and each has these orders:
    LT-000001-A  refundable ($20–$400, delivered 1–20 days ago)
    LT-000001-B  final sale
    LT-000001-C  over $500 → escalation
    LT-000001-D  outside the return window
    LT-000001-E  already refunded
Idempotent: existing LT- customers are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db import session as db
from app.db.models import Customer, Order, utcnow

KINDS = "ABCDE"


def customer_id(i: int) -> str:
    return f"LT-{i:06d}"


def _orders(cid: str, rng: random.Random) -> list[Order]:
    now = utcnow()

    def mk(kind, amount, delivered_days, final=False, refunded=False, name="Widget"):
        return Order(
            id=f"{cid}-{kind}",
            customer_id=cid,
            product_name=name,
            category="general",
            amount=Decimal(str(amount)),
            status="delivered",
            order_date=now - timedelta(days=delivered_days + 3),
            delivered_date=now - timedelta(days=delivered_days),
            is_final_sale=final,
            refunded=refunded,
        )

    return [
        mk("A", round(rng.uniform(20, 400), 2), rng.randint(1, 20), name="Bluetooth Speaker"),
        mk("B", round(rng.uniform(10, 80), 2), rng.randint(1, 20), final=True, name="Clearance Hoodie"),
        mk("C", round(rng.uniform(600, 2000), 2), rng.randint(1, 20), name="Laptop"),
        mk("D", round(rng.uniform(20, 300), 2), rng.randint(40, 90), name="Desk Lamp"),
        mk("E", round(rng.uniform(20, 300), 2), rng.randint(1, 20), refunded=True, name="Keyboard"),
    ]


async def generate(n: int, batch: int = 1000, seed: int = 42) -> int:
    rng = random.Random(seed)
    async with db.SessionLocal() as session:
        existing = await session.scalar(
            select(func.count(Customer.id)).where(Customer.id.like("LT-%"))
        )
    created = 0
    for start in range(existing + 1, n + 1, batch):
        async with db.SessionLocal() as session:
            for i in range(start, min(start + batch, n + 1)):
                cid = customer_id(i)
                session.add(
                    Customer(id=cid, name=f"Load Tester {i}", email=f"lt{i}@load.test")
                )
                session.add_all(_orders(cid, rng))
                created += 1
            await session.commit()
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=10_000)
    args = parser.parse_args()
    created = asyncio.run(generate(args.customers))
    print(f"seed_synthetic: created {created} customers ({args.customers} total requested)")


if __name__ == "__main__":
    main()

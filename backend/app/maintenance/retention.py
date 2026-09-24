"""Data-retention job: delete conversations older than RETENTION_DAYS.

Chat transcripts contain personal data, so they shouldn't be kept forever.
Runs as a Kubernetes CronJob (`deploy/k8s/base/retention-cronjob.yaml`) or
manually: `python -m app.maintenance.retention [--dry-run]`.

Deletes in batches so a large backlog never holds long locks. Refund records
are kept (they're financial records) — only their conversation link is left
dangling by design.

`--demo-hours N` additionally removes public-demo sandboxes (customers with
the `DM-` prefix, see `app/demo.py`) older than N hours, including their
orders and refunds: those are synthetic, not financial records.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import session as db
from app.db.models import Conversation, Customer, Message, Order, ReasoningEvent, Refund
from app.demo import DEMO_PREFIX

BATCH = 500


async def purge(days: int, dry_run: bool = False) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0
    while True:
        async with db.SessionLocal() as session:
            ids = (
                await session.scalars(
                    select(Conversation.id).where(Conversation.created_at < cutoff).limit(BATCH)
                )
            ).all()
            if not ids:
                break
            total += len(ids)
            if dry_run:
                break
            await session.execute(delete(ReasoningEvent).where(ReasoningEvent.conversation_id.in_(ids)))
            await session.execute(delete(Message).where(Message.conversation_id.in_(ids)))
            await session.execute(delete(Conversation).where(Conversation.id.in_(ids)))
            await session.commit()
    return total


async def purge_demo(hours: int, dry_run: bool = False) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    total = 0
    while True:
        async with db.SessionLocal() as session:
            cids = (
                await session.scalars(
                    select(Customer.id)
                    .where(Customer.id.like(f"{DEMO_PREFIX}%"), Customer.created_at < cutoff)
                    .limit(BATCH)
                )
            ).all()
            if not cids:
                break
            total += len(cids)
            if dry_run:
                break
            convs = select(Conversation.id).where(Conversation.customer_id.in_(cids))
            orders = select(Order.id).where(Order.customer_id.in_(cids))
            await session.execute(delete(ReasoningEvent).where(ReasoningEvent.conversation_id.in_(convs)))
            await session.execute(delete(Message).where(Message.conversation_id.in_(convs)))
            await session.execute(delete(Refund).where(Refund.order_id.in_(orders)))
            await session.execute(delete(Conversation).where(Conversation.customer_id.in_(cids)))
            await session.execute(delete(Order).where(Order.customer_id.in_(cids)))
            await session.execute(delete(Customer).where(Customer.id.in_(cids)))
            await session.commit()
    return total


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=settings.retention_days)
    parser.add_argument(
        "--demo-hours",
        type=int,
        default=settings.demo_data_ttl_hours if settings.is_demo else 0,
        help="also purge demo sandboxes older than this (0 = skip)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def run() -> tuple[int, int]:
        demo = await purge_demo(args.demo_hours, args.dry_run) if args.demo_hours else 0
        convs = await purge(args.days, args.dry_run)
        await db.dispose()
        return convs, demo

    convs, demo = asyncio.run(run())
    verb = "would delete" if args.dry_run else "deleted"
    print(f"retention: {verb} {convs} conversations older than {args.days} days")
    if args.demo_hours:
        print(f"retention: {verb} {demo} demo sandboxes older than {args.demo_hours} hours")


if __name__ == "__main__":
    main()

"""Data-retention job: delete conversations older than RETENTION_DAYS.

Chat transcripts contain personal data, so they shouldn't be kept forever.
Runs as a Kubernetes CronJob (`deploy/k8s/base/retention-cronjob.yaml`) or
manually: `python -m app.maintenance.retention [--dry-run]`.

Deletes in batches so a large backlog never holds long locks. Refund records
are kept (they're financial records) — only their conversation link is left
dangling by design.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import session as db
from app.db.models import Conversation, Message, ReasoningEvent

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=get_settings().retention_days)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    n = asyncio.run(purge(args.days, args.dry_run))
    verb = "would delete" if args.dry_run else "deleted"
    print(f"retention: {verb} {n} conversations older than {args.days} days")


if __name__ == "__main__":
    main()

"""Triage what people tried on the public demo, and turn it into eval cases.

Reads `conversation_archive` (sandboxes the retention job already purged) and,
with `--live`, snapshots demo conversations that are still in the live tables.

    python -m app.maintenance.attacks list [--days 7] [--flagged] [--breach] [--live]
    python -m app.maintenance.attacks show <conversation-id>
    python -m app.maintenance.attacks export <conversation-id> [--case-id ID] [--write]
    python -m app.maintenance.attacks scan        # breach check over live sandboxes

Point it at the demo database with `--demo-db`, which reads DEMO_DATABASE_URL
from the repo-root `.env` (or set DATABASE_URL yourself). Read-only, except
`export --write`, which appends to `evals/cases/found_in_demo.yaml`.

The fix loop: `list --flagged` → `show` → `export --write` → run the evals
(`python -m evals.run`) → fix until the new case passes → it guards every PR.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlalchemy import select

from app.config import _async_db_url
from app.db import session as db
from app.db.models import Conversation, ConversationArchive
from app.demo import DEMO_PREFIX
from app.maintenance.archive import snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
FOUND_CASES = REPO_ROOT / "backend" / "evals" / "cases" / "found_in_demo.yaml"
_ORDER_ID = re.compile(r"\b(DM-\d{10})-([A-Z])\b", re.IGNORECASE)


def _use_demo_db() -> None:
    from dotenv import dotenv_values

    url = dotenv_values(REPO_ROOT / ".env").get("DEMO_DATABASE_URL")
    if not url:
        sys.exit("DEMO_DATABASE_URL is not set in the repo-root .env")
    db.configure(db.make_engine(_async_db_url(url)))


async def _archived(days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with db.SessionLocal() as s:
        rows = (
            await s.scalars(
                select(ConversationArchive)
                .where(ConversationArchive.started_at >= since)
                .order_by(ConversationArchive.started_at)
            )
        ).all()
    return [
        {c.name: getattr(r, c.name) for c in ConversationArchive.__table__.columns} for r in rows
    ]


async def _live(days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with db.SessionLocal() as s:
        convs = (
            await s.scalars(
                select(Conversation)
                .where(
                    Conversation.customer_id.like(f"{DEMO_PREFIX}%"),
                    Conversation.created_at >= since,
                )
                .order_by(Conversation.created_at)
            )
        ).all()
        return [await snapshot(s, c) for c in convs]


async def _one(conversation_id: str) -> dict | None:
    async with db.SessionLocal() as s:
        row = await s.get(ConversationArchive, conversation_id)
        if row:
            return {c.name: getattr(row, c.name) for c in ConversationArchive.__table__.columns}
        conv = await s.get(Conversation, conversation_id)
        return await snapshot(s, conv) if conv else None


def _first_user_message(rec: dict) -> str:
    for m in rec["transcript"].get("messages", []):
        if m["role"] == "user":
            return " ".join(m["content"].split())
    return ""


def _decisions(rec: dict) -> str:
    return " ".join(
        f"{d['order_id'].rsplit('-', 1)[-1]}:{d['decision']}" for d in rec["decisions"]
    ) or "-"


def _print_list(records: list[dict]) -> None:
    if not records:
        print("no conversations match")
        return
    for r in records:
        started = r["started_at"]
        when = started.strftime("%m-%d %H:%M") if isinstance(started, datetime) else str(started)
        marks = ",".join(b["kind"] for b in r["breaches"]) or ""
        print(
            f"{when}  {r['conversation_id']}  turns={r['turns']:<2} "
            f"[{_decisions(r)}] {','.join(r['flags']) or '-'}"
            + (f"  BREACH:{marks}" if marks else "")
        )
        print(f"    “{_first_user_message(r)[:110]}”")
    print(
        f"\n{len(records)} conversations, "
        f"{sum(1 for r in records if r['flags'])} flagged, "
        f"{sum(1 for r in records if r['breach'])} with a breach"
    )


def _event_line(e: dict) -> str:
    p = e.get("payload") or {}
    kind = e["step_type"]
    if kind == "tool_call":
        args = ", ".join(f"{k}={v!r}" for k, v in (p.get("args") or {}).items())
        return f"tool_call   {p.get('tool')}({args})"
    if kind in ("policy_eval", "decision"):
        r = p.get("result") or {}
        return f"{kind:<11} {p.get('tool')} → {r.get('decision')}  {'; '.join(r.get('reasons', []))}"
    if kind == "tool_result":
        r = p.get("result") or {}
        return f"tool_result {p.get('tool')}" + (f"  error={r.get('error')}" if r.get("error") else "")
    if kind == "injection_flag":
        return f"INJECTION   {p.get('patterns')}"
    if kind == "output_correction":
        return f"CORRECTED   {p.get('reason')}"
    if kind == "trace":
        return f"trace       {p.get('url') or p.get('trace_id')}"
    if kind == "usage":
        return f"usage       in={p.get('input_tokens')} out={p.get('output_tokens')} {p.get('model')}"
    if kind == "model":
        return "model       " + " ".join(str(p.get("text", "")).split())[:120]
    return f"{kind:<11} {str(p)[:120]}"


def _print_one(rec: dict) -> None:
    print(f"conversation {rec['conversation_id']}  customer {rec['customer_id']}")
    print(f"started {rec['started_at']}  turns {rec['turns']}  tokens {rec['tokens_used']}")
    print(f"flags: {', '.join(rec['flags']) or '-'}")
    for b in rec["breaches"]:
        print(f"BREACH {b['kind']}: {b['detail']}")
    print("\norders:")
    for o in rec["transcript"].get("orders", []):
        print(f"  {o['id']}  {o['scenario']:<16} ${o['amount']:<8} {o['product']}")
    print("\ndecisions:", _decisions(rec))
    timeline = [(m["at"] or "", 0, m) for m in rec["transcript"].get("messages", [])] + [
        (e["at"] or "", 1, e) for e in rec["transcript"].get("events", [])
    ]
    print()
    for _, is_event, item in sorted(timeline, key=lambda t: (t[0], t[1])):
        if is_event:
            print(f"      · {_event_line(item)}")
        else:
            label = "USER " if item["role"] == "user" else "AGENT"
            print(f"\n{label}  {item['content']}")
    if rec.get("opik_trace_ids"):
        print(f"\nopik traces: {', '.join(t for t in rec['opik_trace_ids'] if t)}")


def to_case(rec: dict, case_id: str | None = None) -> dict:
    """An eval case (evals/cases format) replaying this conversation's user turns.

    The sandbox's own order ids become their branch placeholders ({A}..{E});
    any other sandbox's order id becomes {X}, the harness's foreign order.
    """
    own = (rec["customer_id"] or "").upper()
    targets: set[str] = set()

    def rewrite(text: str) -> str:
        text = text.replace("{", "{{").replace("}", "}}")

        def sub(m: re.Match) -> str:
            key = m.group(2).upper() if m.group(1).upper() == own else "X"
            targets.add(key)
            return "{" + key + "}"

        return _ORDER_ID.sub(sub, text)

    turns = [rewrite(m["content"]) for m in rec["transcript"]["messages"] if m["role"] == "user"]
    for d in rec["decisions"]:  # orders it acted on without the id being typed
        key = d["order_id"].rsplit("-", 1)[-1].upper()
        if d["order_id"].upper().startswith(own) and key in "ABCDE":
            targets.add(key)
    started = rec["started_at"]
    day = started.strftime("%Y-%m-%d") if isinstance(started, datetime) else str(started)[:10]
    case: dict = {"id": case_id or "demo-" + rec["conversation_id"].removeprefix("conv-")[:8]}
    case.update({"turns": turns} if len(turns) > 1 else {"text": turns[0] if turns else ""})
    case["targets"] = sorted(targets)
    case["live_only"] = True
    case["note"] = (
        f"Found on the public demo {day} (conversation {rec['conversation_id']}). "
        f"Flags: {', '.join(rec['flags']) or 'none'}. "
        f"Breaches: {', '.join(b['kind'] for b in rec['breaches']) or 'none'}."
    )
    return case


def _write_case(case: dict) -> None:
    existing = yaml.safe_load(FOUND_CASES.read_text()) if FOUND_CASES.exists() else None
    if any(c["id"] == case["id"] for c in existing or []):
        sys.exit(f"{case['id']} is already in {FOUND_CASES.name}; pass --case-id")
    header = (
        "# Attacks found on the public demo, exported by `python -m app.maintenance.attacks\n"
        "# export --write`. Live-model cases: they replay what a real visitor typed.\n"
    )
    body = yaml.safe_dump([case], sort_keys=False, allow_unicode=True, width=100)
    with FOUND_CASES.open("a") as fh:
        if not existing:
            fh.write(header)
        fh.write(body)
    print(f"appended {case['id']} to {FOUND_CASES.relative_to(REPO_ROOT)}")


async def main_async(args: argparse.Namespace) -> int:
    try:
        if args.cmd in ("list", "scan"):
            records = [] if args.cmd == "scan" else await _archived(args.days)
            if args.cmd == "scan" or args.live:
                seen = {r["conversation_id"] for r in records}
                records += [r for r in await _live(args.days) if r["conversation_id"] not in seen]
            if args.cmd == "scan" or args.breach:
                records = [r for r in records if r["breach"]]
            elif args.flagged:
                records = [r for r in records if r["flags"] or r["breach"]]
            _print_list(records)
            return 1 if args.cmd == "scan" and records else 0
        rec = await _one(args.conversation_id)
        if rec is None:
            print(f"no archived or live conversation {args.conversation_id}", file=sys.stderr)
            return 1
        if args.cmd == "show":
            _print_one(rec)
        else:
            case = to_case(rec, args.case_id)
            if args.write:
                _write_case(case)
            else:
                print(yaml.safe_dump([case], sort_keys=False, allow_unicode=True, width=100))
        return 0
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.maintenance.attacks")
    parser.add_argument("--demo-db", action="store_true", help="use DEMO_DATABASE_URL from .env")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="archived (and optionally live) demo conversations")
    ls.add_argument("--days", type=int, default=7)
    ls.add_argument("--flagged", action="store_true", help="only flagged or breached")
    ls.add_argument("--breach", action="store_true", help="only ground-truth breaches")
    ls.add_argument("--live", action="store_true", help="include sandboxes not yet purged")
    sc = sub.add_parser("scan", help="breach check over live sandboxes; exits 1 on a breach")
    sc.add_argument("--days", type=int, default=2)
    show = sub.add_parser("show", help="full transcript and reasoning trace")
    show.add_argument("conversation_id")
    ex = sub.add_parser("export", help="print (or --write) an eval case for this conversation")
    ex.add_argument("conversation_id")
    ex.add_argument("--case-id")
    ex.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.demo_db:
        _use_demo_db()
    elif not os.getenv("DATABASE_URL"):
        print("note: DATABASE_URL is not set; using the local default database", file=sys.stderr)
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

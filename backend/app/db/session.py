"""Async database engine and session factory.

Sessions are short-lived: open one per unit of work (`async with
SessionLocal() as s:`) and never hold one across an LLM call, so a pod's
connection pool is sized by DB work, not by the number of open chat streams.

`SessionLocal` is looked up at call time (`db.SessionLocal()`) so tests can
swap in an isolated engine.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base


def make_engine(url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    url = url or settings.async_database_url
    if url.startswith("sqlite"):
        # SQLite file path may live under a directory that doesn't exist yet.
        if ":///" in url and ":memory:" not in url:
            Path(url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url, connect_args={"timeout": 30})

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine: AsyncEngine = make_engine()
SessionLocal = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


def configure(new_engine: AsyncEngine) -> None:
    """Point the app at a different engine (used by tests and scripts)."""
    global engine, SessionLocal
    engine = new_engine
    SessionLocal = async_sessionmaker(new_engine, autoflush=False, expire_on_commit=False)


async def init_db() -> None:
    """Create tables directly. Dev/tests only — production uses Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose() -> None:
    await engine.dispose()

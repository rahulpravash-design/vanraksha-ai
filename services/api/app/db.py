"""Database engine, session lifecycle, and the declarative base."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from .config import get_settings

settings = get_settings()

_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}

if settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    if ":memory:" in settings.database_url:
        # Keep one connection alive so an in-memory test database survives
        # between requests inside a single test.
        _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs.pop("pool_pre_ping", None)
elif os.getenv("VERCEL"):
    # Serverless. Each invocation may run in a fresh process, so a pooled
    # connection is never reused -- it just holds a PostgreSQL slot open that
    # nothing will claim again, and enough concurrent invocations exhaust the
    # server's connection limit. NullPool opens and closes per session, which
    # is the right trade when the process itself is short-lived.
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    """SQLite does not enforce foreign keys unless asked, which silently allows
    orphaned rows. Turn it on, and use WAL so reads do not block the writer."""
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    if ":memory:" not in settings.database_url:
        cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

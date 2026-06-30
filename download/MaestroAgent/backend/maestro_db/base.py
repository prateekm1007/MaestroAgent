"""
SQLAlchemy 2.0 database foundation — engine factory, Base class, session management.

This is the single entry point for all database access in Maestro. Every
store (checkpoint_store, prediction_lifecycle, learning, auth, etc.) uses
get_engine() and get_session() from this module.

Design decisions:
  - SYNCHRONOUS SQLAlchemy only (create_engine, NOT create_async_engine).
    The OEM state management uses threading.RLock and synchronous resolution.
    Async would break the learning loop.
  - Works with both SQLite (dev) and PostgreSQL (production).
  - DATABASE_URL is parsed with make_url(), NEVER Path().
  - Connection pooling: pool_size=20, max_overflow=10, pool_pre_ping=True
    for PostgreSQL. SQLite uses the default (no pool — in-memory or file).
  - Fail-closed: in production without DATABASE_URL, refuses to start.
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass


# ─── Engine management ─────────────────────────────────────────────────────

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_database_url() -> str:
    """Get the database URL from the environment.

    Resolution order:
      1. DATABASE_URL env var (must be a proper SQLAlchemy URL)
      2. SQLite default (dev mode only)

    In production (MAESTRO_ENV=production), DATABASE_URL must be set.
    If it's not set, raise RuntimeError — never auto-generate a file path.
    """
    url = os.environ.get("DATABASE_URL", "")
    is_production = os.environ.get("MAESTRO_ENV", "development") == "production"

    if url:
        # Normalize: if it starts with "file:", convert to SQLite URL
        if url.startswith("file:"):
            path = url.replace("file:", "")
            url = f"sqlite:///{path}"
        return url

    # No DATABASE_URL set
    if is_production:
        raise RuntimeError(
            "[db] FATAL: DATABASE_URL is not set and MAESTRO_ENV=production. "
            "Set DATABASE_URL to a PostgreSQL connection string, e.g. "
            "postgresql://user:pass@host:5432/maestro"
        )

    # Dev default: SQLite file
    return "sqlite:///maestro.db"


def get_engine() -> Engine:
    """Get the singleton SQLAlchemy engine.

    Creates the engine on first call. Uses connection pooling for PostgreSQL,
    default settings for SQLite.
    """
    global _engine
    if _engine is not None:
        return _engine

    url = get_database_url()
    parsed = make_url(url)
    is_sqlite = parsed.drivername.startswith("sqlite")

    if is_sqlite:
        # SQLite: no connection pool, check_same_thread for multi-threaded access
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL: connection pool with pre-ping
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

    logger.info("Database engine created: %s (dialect=%s)", url, parsed.drivername)
    return _engine


def get_session() -> Session:
    """Get a new SQLAlchemy session.

    Usage:
        with get_session() as session:
            session.execute(...)
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for a transactional session.

    Automatically commits on success, rolls back on exception.

    Usage:
        with session_scope() as session:
            session.add(model)
            # auto-commit on exit
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_path_for_file_db(db_name: str) -> str:
    """Get a file path for a named SQLite database (dev mode convenience).

    In PostgreSQL mode, this returns the main DATABASE_URL — all data
    lives in one database with different schemas/tables.

    In SQLite mode, this returns a file path in the same directory as
    the main database, for backward compatibility with the existing
    multi-file SQLite setup.

    This replaces the old pattern:
        str(Path(os.environ.get("DATABASE_URL", "file:maestro.db")
                .replace("file:", "")).parent / "learning.db")
    which was broken for PostgreSQL.
    """
    url = os.environ.get("DATABASE_URL", "")
    if url and not url.startswith("file:") and "sqlite" not in url:
        # PostgreSQL: all data in one database
        return url

    # SQLite mode: derive path from the main DB
    if url.startswith("file:"):
        main_path = url.replace("file:", "")
    elif url.startswith("sqlite:///"):
        main_path = url.replace("sqlite:///", "")
    else:
        main_path = "maestro.db"

    from pathlib import Path
    return str(Path(main_path).parent / db_name)


def close_engine() -> None:
    """Close the engine on shutdown."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None

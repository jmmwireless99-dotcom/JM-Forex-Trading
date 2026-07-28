"""Database engine / session helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def database_url() -> str:
    return (get_settings().database_url or "").strip()


def db_enabled() -> bool:
    return bool(database_url())


def get_engine() -> Engine | None:
    global _engine, _SessionLocal
    url = database_url()
    if not url:
        return None
    if _engine is None:
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session] | None:
    if get_engine() is None:
        return None
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database not configured (set JM_DATABASE_URL)")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_db() -> dict:
    """Return health snapshot; never raises to callers."""
    if not db_enabled():
        return {"configured": False, "ok": False, "error": "JM_DATABASE_URL not set"}
    try:
        engine = get_engine()
        assert engine is not None
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"configured": True, "ok": True, "error": None}
    except Exception as exc:  # noqa: BLE001 — surface connection errors to API
        return {"configured": True, "ok": False, "error": str(exc)}


def reset_db_state() -> None:
    """Test helper — dispose engine so next call rebuilds from settings."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None

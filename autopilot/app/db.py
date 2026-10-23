"""Database session management.

Postgres in production (Railway). A local SQLite file is used automatically
when DATABASE_URL is absent, so the demo and the test suite run with zero
setup. Both dialects are exercised by the test suite.
"""
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def _normalized_url() -> str:
    url = settings.database_url or os.getenv("DATABASE_URL")
    if not url:
        return "sqlite:///./autopilot.db"
    # Railway still hands out the legacy postgres:// scheme on some services.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = _normalized_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Alembic owns real migrations; this keeps boot simple."""
    from . import models  # noqa: F401  (register mappers)

    models.Base.metadata.create_all(bind=engine)

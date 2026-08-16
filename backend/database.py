from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Handle Railway's postgres:// vs postgresql:// prefix
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine only if DATABASE_URL is configured.
# App can still boot and serve /health even if the database is missing/unreachable.
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None

def get_db():
    """Dependency to get database session"""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL environment variable not set")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

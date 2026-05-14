from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")

# Railway provides postgres:// URLs; SQLAlchemy 2.x requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    Path("data").mkdir(exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import Base
    Base.metadata.create_all(bind=engine)
    _dedup_jobs()


def _dedup_jobs() -> None:
    """Remove duplicate jobs that share the same linkedin_job_id (keep lowest id)."""
    from sqlalchemy import text
    with SessionLocal() as db:
        result = db.execute(text("""
            DELETE FROM jobs
            WHERE linkedin_job_id IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id) FROM jobs
                  WHERE linkedin_job_id IS NOT NULL
                  GROUP BY linkedin_job_id
              )
        """))
        if result.rowcount:
            db.commit()
            from loguru import logger
            logger.info(f"Startup dedup: removed {result.rowcount} duplicate job(s)")

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
    _add_missing_columns()
    _normalize_locations()
    _normalize_departments()
    _dedup_jobs()


def _add_missing_columns() -> None:
    """Add new columns that create_all won't add to existing tables."""
    from sqlalchemy import text
    with SessionLocal() as db:
        for stmt in [
            "ALTER TABLE jobs ADD COLUMN is_reposted BOOLEAN NOT NULL DEFAULT 0",
        ]:
            try:
                db.execute(text(stmt))
                db.commit()
            except Exception:
                pass  # column already exists


def _normalize_locations() -> None:
    """Retroactively normalize all location strings already in the database."""
    from app.models import Job
    from app.scraper.normalizer import normalize_location
    from loguru import logger
    from sqlalchemy import select
    with SessionLocal() as db:
        jobs = db.execute(select(Job).where(Job.location.isnot(None))).scalars().all()
        updated = 0
        for job in jobs:
            normalized = normalize_location(job.location)
            if normalized and normalized != job.location:
                job.location = normalized
                updated += 1
        if updated:
            db.commit()
            logger.info(f"Location normalization: updated {updated} job(s)")


def _normalize_departments() -> None:
    """Map all existing department strings to one of the three canonical groups."""
    from app.models import Job
    from app.scraper.normalizer import normalize_department
    from loguru import logger
    from sqlalchemy import select
    with SessionLocal() as db:
        jobs = db.execute(select(Job).where(Job.department.isnot(None))).scalars().all()
        updated = 0
        for job in jobs:
            normalized = normalize_department(job.department)
            if normalized and normalized != job.department:
                job.department = normalized
                updated += 1
        if updated:
            db.commit()
            logger.info(f"Department normalization: updated {updated} job(s)")


def _dedup_jobs() -> None:
    """Remove duplicate jobs — by linkedin_job_id first, then by normalized title+company."""
    from sqlalchemy import text
    from loguru import logger
    with SessionLocal() as db:
        # Pass 1: same linkedin_job_id
        r1 = db.execute(text("""
            DELETE FROM jobs
            WHERE linkedin_job_id IS NOT NULL
              AND id NOT IN (
                  SELECT MIN(id) FROM jobs
                  WHERE linkedin_job_id IS NOT NULL
                  GROUP BY linkedin_job_id
              )
        """))
        # Pass 2: same normalized title + company (catches different IDs for same posting)
        r2 = db.execute(text("""
            DELETE FROM jobs
            WHERE id NOT IN (
                SELECT MIN(id) FROM jobs
                GROUP BY LOWER(TRIM(COALESCE(title, ''))),
                         LOWER(TRIM(COALESCE(company_name, '')))
            )
        """))
        removed = (r1.rowcount or 0) + (r2.rowcount or 0)
        if removed:
            db.commit()
            logger.info(f"Startup dedup: removed {removed} duplicate job(s)")

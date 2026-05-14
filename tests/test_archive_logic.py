"""Tests for archive/missing logic."""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Job, ScrapeRun, JobStatus, RunStatus
from app.persistence.archive_manager import ArchiveManager


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_job(db, key, status=JobStatus.active, missing_count=0):
    run = ScrapeRun(status=RunStatus.success, started_at=datetime.utcnow())
    db.add(run)
    db.flush()

    job = Job(
        canonical_job_key=key,
        status=status,
        missing_count=missing_count,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        latest_scrape_run_id=run.id,
    )
    db.add(job)
    db.commit()
    return job, run.id


class TestArchiveManager:
    def test_seen_job_not_archived(self, db):
        job, run_id = make_job(db, "linkedin:1001")
        manager = ArchiveManager(db)
        manager.threshold = 3

        archived = manager.process_missing(run_id, ["linkedin:1001"])
        db.refresh(job)

        assert job.status == JobStatus.active
        assert job.missing_count == 0
        assert archived == 0

    def test_unseen_job_increments_missing(self, db):
        job, run_id = make_job(db, "linkedin:2001")
        manager = ArchiveManager(db)
        manager.threshold = 3

        manager.process_missing(run_id, [])  # Job not seen
        db.refresh(job)

        assert job.status == JobStatus.missing
        assert job.missing_count == 1

    def test_job_archived_after_threshold(self, db):
        job, run_id = make_job(db, "linkedin:3001", missing_count=2)
        manager = ArchiveManager(db)
        manager.threshold = 3

        archived = manager.process_missing(run_id, [])
        db.refresh(job)

        assert job.status == JobStatus.archived
        assert job.archived_at is not None
        assert archived == 1

    def test_job_not_archived_below_threshold(self, db):
        job, run_id = make_job(db, "linkedin:4001", missing_count=1)
        manager = ArchiveManager(db)
        manager.threshold = 3

        manager.process_missing(run_id, [])
        db.refresh(job)

        assert job.status == JobStatus.missing
        assert job.archived_at is None

    def test_archived_job_ignored(self, db):
        job, run_id = make_job(db, "linkedin:5001", status=JobStatus.archived, missing_count=5)
        manager = ArchiveManager(db)

        archived_before = job.archived_at
        manager.process_missing(run_id, [])
        db.refresh(job)

        # Already archived — should not be double-archived
        assert job.status == JobStatus.archived

    def test_multiple_jobs_mixed(self, db):
        job1, _ = make_job(db, "linkedin:6001")  # seen
        job2, run_id = make_job(db, "linkedin:6002")  # not seen, threshold=2, count=1
        job2.missing_count = 1
        db.commit()

        manager = ArchiveManager(db)
        manager.threshold = 2

        archived = manager.process_missing(run_id, ["linkedin:6001"])
        db.refresh(job1)
        db.refresh(job2)

        assert job1.status == JobStatus.active  # Not touched by archive manager
        assert job2.status == JobStatus.archived
        assert archived == 1

    def test_threshold_configurable(self, db):
        job, run_id = make_job(db, "linkedin:7001", missing_count=4)
        manager = ArchiveManager(db)
        manager.threshold = 5  # Needs 5 misses

        manager.process_missing(run_id, [])
        db.refresh(job)

        # missing_count is now 5 = threshold, so archived
        assert job.status == JobStatus.archived

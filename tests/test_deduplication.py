"""Tests for idempotent job persistence (no duplicates on re-run)."""
import pytest
from datetime import datetime
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, JobStatus
from app.persistence.job_store import JobStore
from app.classifier.ev_classifier import ClassificationResult
from app.models import EVLabel


MOCK_POSITIVE = {
    "clusters": {},
    "location_boost": [],
}
MOCK_NEGATIVE = {
    "clusters": {},
    "excluded_title_patterns": [],
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_clf():
    return ClassificationResult(
        ev_score=70,
        ev_confidence=0.7,
        ev_label=EVLabel.core_ev,
        reasoning=["+70 test"],
    )


def make_raw(key="linkedin:TEST123", **overrides):
    base = {
        "source": "linkedin",
        "linkedin_job_id": "TEST123",
        "canonical_job_key": key,
        "title": "Vehicle Dynamics Engineer",
        "company": "Xiaomi",
        "location": "Munich",
        "department": "EV Engineering",
        "employment_type": "Full-time",
        "seniority_level": "Mid-Senior",
        "job_url": "https://www.linkedin.com/jobs/view/TEST123/",
        "canonical_url": "https://www.linkedin.com/jobs/view/TEST123/",
        "description": "Test description",
        "posted_time": "2 days ago",
        "posted_date_normalized": datetime.utcnow(),
        "raw_applicant_text": "47 applicants",
        "applicant_count_exact": 47,
        "applicant_count_min": 47,
        "applicant_count_quality": "exact",
    }
    base.update(overrides)
    return base


class TestJobStoreDeduplication:
    def test_first_insert(self, db):
        # Create a dummy run
        from app.models import ScrapeRun, RunStatus
        run = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run)
        db.commit()

        store = JobStore(db)
        result = store.upsert_job(make_raw(), make_clf(), run.id)

        assert result["action"] == "inserted"
        assert result["canonical_key"] == "linkedin:TEST123"

    def test_second_insert_is_update_not_duplicate(self, db):
        from app.models import ScrapeRun, RunStatus, Job
        from sqlalchemy import select

        run = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run)
        db.commit()

        store = JobStore(db)
        store.upsert_job(make_raw(), make_clf(), run.id)

        # Second run
        run2 = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run2)
        db.commit()

        result2 = store.upsert_job(make_raw(), make_clf(), run2.id)
        assert result2["action"] in ("updated", "unchanged")

        # Only one job should exist
        count = db.execute(select(Job).where(Job.canonical_job_key == "linkedin:TEST123")).scalars().all()
        assert len(count) == 1

    def test_idempotent_multiple_runs(self, db):
        from app.models import ScrapeRun, RunStatus, Job
        from sqlalchemy import select

        store = JobStore(db)
        for i in range(5):
            run = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
            db.add(run)
            db.commit()
            store.upsert_job(make_raw(), make_clf(), run.id)

        all_jobs = db.execute(select(Job)).scalars().all()
        assert len(all_jobs) == 1

    def test_different_canonical_keys_create_separate_jobs(self, db):
        from app.models import ScrapeRun, RunStatus, Job
        from sqlalchemy import select

        run = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run)
        db.commit()

        store = JobStore(db)
        store.upsert_job(make_raw("linkedin:AAA"), make_clf(), run.id)
        store.upsert_job(make_raw("linkedin:BBB"), make_clf(), run.id)

        all_jobs = db.execute(select(Job)).scalars().all()
        assert len(all_jobs) == 2

    def test_field_update_on_second_run(self, db):
        from app.models import ScrapeRun, RunStatus, Job
        from sqlalchemy import select

        run = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run)
        db.commit()
        store = JobStore(db)
        store.upsert_job(make_raw(location="Berlin"), make_clf(), run.id)

        run2 = ScrapeRun(status=RunStatus.running, started_at=datetime.utcnow())
        db.add(run2)
        db.commit()
        store.upsert_job(make_raw(location="Munich"), make_clf(), run2.id)

        job = db.execute(select(Job)).scalar_one()
        assert job.location == "Munich"

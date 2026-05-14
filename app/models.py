import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Enum as SAEnum


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    active = "active"
    missing = "missing"
    archived = "archived"


class EVLabel(str, enum.Enum):
    core_ev = "core_ev"
    likely_ev = "likely_ev"
    maybe_ev = "maybe_ev"
    non_ev = "non_ev"


class ApplicantQuality(str, enum.Enum):
    exact = "exact"
    lower_bound = "lower_bound"
    unavailable = "unavailable"


class ChangeType(str, enum.Enum):
    insert = "insert"
    update = "update"
    status_change = "status_change"
    reactivation = "reactivation"
    archive = "archive"


class RunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"
    partial = "partial"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, default="linkedin")
    linkedin_job_id = Column(String(50), nullable=True)
    canonical_job_key = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    title = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    employment_type = Column(String(100), nullable=True)
    seniority_level = Column(String(100), nullable=True)
    job_url = Column(Text, nullable=True)
    canonical_url = Column(Text, nullable=True)
    description_text = Column(Text, nullable=True)
    posted_text_raw = Column(String(255), nullable=True)
    posted_date_normalized = Column(DateTime, nullable=True)
    is_reposted = Column(Boolean, nullable=False, default=False)
    status = Column(SAEnum(JobStatus), nullable=False, default=JobStatus.active)
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)
    missing_count = Column(Integer, nullable=False, default=0)
    latest_scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id"), nullable=True)

    ev_classification = relationship(
        "JobEVClassification", back_populates="job", uselist=False,
        cascade="all, delete-orphan"
    )
    applicant_history = relationship(
        "ApplicantHistory", back_populates="job",
        order_by="ApplicantHistory.observed_at",
        cascade="all, delete-orphan"
    )
    run_presence = relationship(
        "JobRunPresence", back_populates="job",
        cascade="all, delete-orphan"
    )
    change_log = relationship(
        "JobChangeLog", back_populates="job",
        order_by="desc(JobChangeLog.changed_at)",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("canonical_job_key", name="uq_jobs_canonical_key"),
        Index("ix_jobs_linkedin_id", "linkedin_job_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_first_seen", "first_seen_at"),
    )


class JobEVClassification(Base):
    __tablename__ = "job_ev_classification"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    ev_score = Column(Integer, nullable=False, default=0)
    ev_confidence = Column(Float, nullable=False, default=0.0)
    ev_label = Column(SAEnum(EVLabel), nullable=False, default=EVLabel.non_ev)
    reasoning_json = Column(JSON, nullable=False, default=list)
    classifier_version = Column(String(20), nullable=False, default="1.0")
    classified_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    job = relationship("Job", back_populates="ev_classification")

    __table_args__ = (
        Index("ix_ev_label", "ev_label"),
        Index("ix_ev_score", "ev_score"),
    )


class ApplicantHistory(Base):
    __tablename__ = "applicant_history"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id"), nullable=True)
    observed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    raw_applicant_text = Column(String(255), nullable=True)
    applicant_count_exact = Column(Integer, nullable=True)
    applicant_count_min = Column(Integer, nullable=True)
    applicant_count_quality = Column(
        SAEnum(ApplicantQuality), nullable=False, default=ApplicantQuality.unavailable
    )

    job = relationship("Job", back_populates="applicant_history")

    __table_args__ = (
        Index("ix_applicant_job_time", "job_id", "observed_at"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(100), nullable=True)
    source_url = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(SAEnum(RunStatus), nullable=False, default=RunStatus.running)
    jobs_seen_count = Column(Integer, nullable=False, default=0)
    jobs_inserted_count = Column(Integer, nullable=False, default=0)
    jobs_updated_count = Column(Integer, nullable=False, default=0)
    jobs_archived_count = Column(Integer, nullable=False, default=0)
    errors_count = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=True)

    job_presence = relationship("JobRunPresence", back_populates="run")

    __table_args__ = (
        Index("ix_scrape_runs_started", "started_at"),
    )


class JobRunPresence(Base):
    __tablename__ = "job_run_presence"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id"), nullable=False)
    was_seen = Column(Boolean, nullable=False, default=True)
    seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    job = relationship("Job", back_populates="run_presence")
    run = relationship("ScrapeRun", back_populates="job_presence")

    __table_args__ = (
        UniqueConstraint("job_id", "scrape_run_id", name="uq_presence_job_run"),
        Index("ix_presence_run", "scrape_run_id"),
    )


class HiddenJob(Base):
    """Jobs permanently dismissed by the user from the EV dashboard."""
    __tablename__ = "hidden_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    hidden_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reason = Column(String(255), nullable=True)

    job = relationship("Job")


class JobChangeLog(Base):
    __tablename__ = "job_change_log"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    changed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    change_type = Column(SAEnum(ChangeType), nullable=False)

    job = relationship("Job", back_populates="change_log")

    __table_args__ = (
        Index("ix_changelog_job", "job_id"),
        Index("ix_changelog_time", "changed_at"),
    )

"""
Idempotent job persistence layer.
Handles insert-or-update semantics with change tracking.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import (
    Job, JobEVClassification, ApplicantHistory,
    JobRunPresence, JobChangeLog, JobStatus, ChangeType, ApplicantQuality
)
from app.classifier.ev_classifier import ClassificationResult
from app.scraper.normalizer import classify_department, normalize_location


class JobStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_job(
        self,
        raw: Dict[str, Any],
        classification: ClassificationResult,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Insert new job or update existing one.
        Returns dict with keys: action (inserted|updated), canonical_key, job_id.
        """
        key = raw.get("canonical_job_key")
        if not key:
            logger.warning("Job missing canonical_job_key, skipping")
            return {"action": "skipped", "canonical_key": None, "job_id": None}

        existing = self.db.execute(
            select(Job).where(Job.canonical_job_key == key)
        ).scalar_one_or_none()

        now = datetime.utcnow()
        if existing is None:
            job = self._insert_job(raw, classification, run_id, now)
            self._log_change(job.id, ChangeType.insert, "status", None, "active", now)
            return {"action": "inserted", "canonical_key": key, "job_id": job.id}
        else:
            action = self._update_job(existing, raw, classification, run_id, now)
            return {"action": action, "canonical_key": key, "job_id": existing.id}

    def _insert_job(
        self,
        raw: Dict[str, Any],
        clf: ClassificationResult,
        run_id: int,
        now: datetime,
    ) -> Job:
        job = Job(
            source=raw.get("source", "linkedin"),
            linkedin_job_id=raw.get("linkedin_job_id"),
            canonical_job_key=raw["canonical_job_key"],
            company_name=raw.get("company"),
            title=raw.get("title"),
            location=normalize_location(raw.get("location")),
            department=classify_department(raw.get("title"), raw.get("department")),
            employment_type=raw.get("employment_type"),
            seniority_level=raw.get("seniority_level"),
            job_url=raw.get("job_url"),
            canonical_url=raw.get("canonical_url"),
            description_text=raw.get("description"),
            posted_text_raw=raw.get("posted_time"),
            posted_date_normalized=raw.get("posted_date_normalized"),
            is_reposted=bool(raw.get("is_reposted", False)),
            status=JobStatus.active,
            first_seen_at=now,
            last_seen_at=now,
            missing_count=0,
            latest_scrape_run_id=run_id,
        )
        self.db.add(job)
        self.db.flush()

        # EV classification
        ev = JobEVClassification(
            job_id=job.id,
            ev_score=clf.ev_score,
            ev_confidence=clf.ev_confidence,
            ev_label=clf.ev_label,
            reasoning_json=clf.reasoning,
            classifier_version=clf.classifier_version,
            classified_at=now,
        )
        self.db.add(ev)

        # Applicant history
        self._record_applicant(job.id, raw, run_id, now)

        # Run presence
        self.db.add(JobRunPresence(job_id=job.id, scrape_run_id=run_id, was_seen=True, seen_at=now))

        self.db.commit()
        logger.debug(f"Inserted job: {job.title} [{job.canonical_job_key}]")
        return job

    def _update_job(
        self,
        job: Job,
        raw: Dict[str, Any],
        clf: ClassificationResult,
        run_id: int,
        now: datetime,
    ) -> str:
        changed = False

        # Track field changes for auditable fields
        trackable = {
            "title": raw.get("title"),
            "location": normalize_location(raw.get("location")),
            "employment_type": raw.get("employment_type"),
            "seniority_level": raw.get("seniority_level"),
            "department": classify_department(raw.get("title"), raw.get("department")),
        }
        for field, new_val in trackable.items():
            old_val = getattr(job, field)
            if new_val and new_val != old_val:
                self._log_change(job.id, ChangeType.update, field, old_val, new_val, now)
                setattr(job, field, new_val)
                changed = True

        # Mark as reposted once detected (sticky — never reset to False)
        if raw.get("is_reposted") and not job.is_reposted:
            job.is_reposted = True
            changed = True

        # Enrich description if we now have it
        if raw.get("description") and not job.description_text:
            job.description_text = raw["description"]
            changed = True

        # Reactivation
        was_archived = job.status in (JobStatus.archived, JobStatus.missing)

        job.last_seen_at = now
        job.missing_count = 0
        job.latest_scrape_run_id = run_id

        if was_archived:
            old_status = job.status.value
            job.status = JobStatus.active
            job.archived_at = None
            self._log_change(job.id, ChangeType.reactivation, "status", old_status, "active", now)
            changed = True
        elif job.status != JobStatus.active:
            job.status = JobStatus.active
            changed = True

        # Update classification if score changed meaningfully
        if job.ev_classification:
            if abs(job.ev_classification.ev_score - clf.ev_score) >= 5:
                job.ev_classification.ev_score = clf.ev_score
                job.ev_classification.ev_confidence = clf.ev_confidence
                job.ev_classification.ev_label = clf.ev_label
                job.ev_classification.reasoning_json = clf.reasoning
                job.ev_classification.classified_at = now
        else:
            ev = JobEVClassification(
                job_id=job.id,
                ev_score=clf.ev_score,
                ev_confidence=clf.ev_confidence,
                ev_label=clf.ev_label,
                reasoning_json=clf.reasoning,
                classifier_version=clf.classifier_version,
                classified_at=now,
            )
            self.db.add(ev)

        # Record applicant data point
        self._record_applicant(job.id, raw, run_id, now)

        # Run presence
        existing_presence = self.db.execute(
            select(JobRunPresence).where(
                JobRunPresence.job_id == job.id,
                JobRunPresence.scrape_run_id == run_id,
            )
        ).scalar_one_or_none()
        if not existing_presence:
            self.db.add(JobRunPresence(job_id=job.id, scrape_run_id=run_id, was_seen=True, seen_at=now))

        self.db.commit()
        return "updated" if changed else "unchanged"

    def _record_applicant(
        self,
        job_id: int,
        raw: Dict[str, Any],
        run_id: int,
        now: datetime,
    ) -> None:
        raw_text = raw.get("raw_applicant_text")
        exact = raw.get("applicant_count_exact")
        minimum = raw.get("applicant_count_min")
        quality_str = raw.get("applicant_count_quality", "unavailable")

        # Don't write an "unavailable" record if we already have data for this run
        if quality_str == "unavailable" and not raw_text:
            return

        try:
            quality = ApplicantQuality(quality_str)
        except ValueError:
            quality = ApplicantQuality.unavailable

        record = ApplicantHistory(
            job_id=job_id,
            scrape_run_id=run_id,
            observed_at=now,
            raw_applicant_text=raw_text,
            applicant_count_exact=exact,
            applicant_count_min=minimum,
            applicant_count_quality=quality,
        )
        self.db.add(record)

    def _log_change(
        self,
        job_id: int,
        change_type: ChangeType,
        field: Optional[str],
        old_val: Any,
        new_val: Any,
        now: datetime,
    ) -> None:
        entry = JobChangeLog(
            job_id=job_id,
            changed_at=now,
            field_name=field,
            old_value=str(old_val) if old_val is not None else None,
            new_value=str(new_val) if new_val is not None else None,
            change_type=change_type,
        )
        self.db.add(entry)

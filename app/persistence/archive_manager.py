"""
Archive manager: implements missing-count logic and archiving thresholds.

Algorithm per run:
  - All active/missing jobs NOT seen in the current run → missing_count += 1
  - If missing_count >= threshold → status = archived, archived_at = now
  - If a job IS seen in the run → missing_count = 0, status = active (handled by JobStore)
"""
import os
from datetime import datetime, timedelta
from typing import Collection, Optional
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Job, JobChangeLog, JobRunPresence, JobStatus, ChangeType

ARCHIVE_THRESHOLD = int(os.getenv("ARCHIVE_MISSING_THRESHOLD", "5"))


class ArchiveManager:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.threshold = ARCHIVE_THRESHOLD

    def process_missing(
        self,
        run_id: int,
        seen_canonical_keys: Collection[str],
    ) -> int:
        """
        After a scrape run completes, mark unseen active/missing jobs.
        Returns count of newly archived jobs.
        """
        seen_set = set(seen_canonical_keys)
        now = datetime.utcnow()
        archived_count = 0

        # Load all non-archived jobs
        active_jobs = self.db.execute(
            select(Job).where(Job.status.in_([JobStatus.active, JobStatus.missing]))
        ).scalars().all()

        for job in active_jobs:
            if job.canonical_job_key in seen_set:
                continue  # Was seen — JobStore already reset missing_count

            # Job was NOT seen in this run
            job.missing_count += 1

            if job.missing_count >= self.threshold:
                old_status = job.status.value
                job.status = JobStatus.archived
                job.archived_at = now
                archived_count += 1

                self.db.add(JobChangeLog(
                    job_id=job.id,
                    changed_at=now,
                    field_name="status",
                    old_value=old_status,
                    new_value="archived",
                    change_type=ChangeType.archive,
                ))
                logger.debug(
                    f"Archived job {job.id} [{job.title}] "
                    f"after {job.missing_count} missing runs"
                )
            elif job.missing_count >= 2:
                # Only surface as "missing" after 2 consecutive absences —
                # single-run blips (LinkedIn pagination noise) stay silently active.
                old_status = job.status.value
                job.status = JobStatus.missing
                if old_status != "missing":
                    self.db.add(JobChangeLog(
                        job_id=job.id,
                        changed_at=now,
                        field_name="status",
                        old_value=old_status,
                        new_value="missing",
                        change_type=ChangeType.status_change,
                    ))
            # missing_count == 1: stay active, don't emit a signal yet

            # Record absence in run presence
            existing = self.db.execute(
                select(JobRunPresence).where(
                    JobRunPresence.job_id == job.id,
                    JobRunPresence.scrape_run_id == run_id,
                )
            ).scalar_one_or_none()
            if not existing:
                self.db.add(JobRunPresence(
                    job_id=job.id,
                    scrape_run_id=run_id,
                    was_seen=False,
                    seen_at=now,
                ))

        self.db.commit()
        logger.info(f"Archive pass: {archived_count} jobs archived this run")
        return archived_count

    def validate_archived_jobs(
        self,
        scraper,
        max_age_days: Optional[int] = 60,
    ) -> int:
        """
        For archived jobs, check if they still exist on LinkedIn.
        Reactivates any that return HTTP 200 from the guest detail API.
        Returns count of reactivated jobs.

        max_age_days: only check jobs archived within this many days.
                      Pass None to validate all archived jobs.
        """
        query = select(Job).where(Job.status == JobStatus.archived)
        if max_age_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            query = query.where(Job.archived_at >= cutoff)

        archived_jobs = self.db.execute(query).scalars().all()
        if not archived_jobs:
            return 0

        logger.info(f"Validating {len(archived_jobs)} archived jobs against LinkedIn…")
        reactivated = 0
        now = datetime.utcnow()

        for job in archived_jobs:
            if not job.linkedin_job_id:
                continue
            try:
                still_live = scraper.job_exists(job.linkedin_job_id)
            except Exception as e:
                logger.warning(f"Validation failed for job {job.id}: {e}")
                continue

            if still_live:
                old_status = job.status.value
                job.status = JobStatus.active
                job.archived_at = None
                job.missing_count = 0
                job.last_seen_at = now
                self.db.add(JobChangeLog(
                    job_id=job.id,
                    changed_at=now,
                    field_name="status",
                    old_value=old_status,
                    new_value="active",
                    change_type=ChangeType.reactivation,
                ))
                reactivated += 1
                logger.debug(f"Reactivated job {job.id} [{job.title}] — still live on LinkedIn")

        if reactivated:
            self.db.commit()
        logger.info(f"Archive validation: {reactivated}/{len(archived_jobs)} reactivated")
        return reactivated

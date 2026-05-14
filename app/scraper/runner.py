"""
Scrape run orchestrator.
Coordinates scraping, classification, persistence, and archiving for a single run.
"""
from datetime import datetime
from typing import List, Optional
from loguru import logger
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.scraper.linkedin import LinkedInScraper
from app.scraper import log_buffer
from app.classifier.ev_classifier import EVClassifier
from app.persistence.job_store import JobStore
from app.persistence.archive_manager import ArchiveManager
from app.models import ScrapeRun, RunStatus
from app.config_loader import load_sources


def _log(run_id: int, level: str, msg: str) -> None:
    getattr(logger, level.lower(), logger.info)(msg)
    log_buffer.append(run_id, level, msg)


class ScrapeRunner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.store = JobStore(db)
        self.archive = ArchiveManager(db)
        self.classifier = EVClassifier()

    def run(
        self,
        source_names: Optional[List[str]] = None,
        enrich_details: bool = True,
        existing_run_id: Optional[int] = None,
    ) -> ScrapeRun:
        sources = load_sources()
        if source_names:
            sources = [s for s in sources if s["name"] in source_names]
        else:
            sources = [s for s in sources if s.get("enabled", True)]

        if existing_run_id:
            run = self.db.execute(
                sa_select(ScrapeRun).where(ScrapeRun.id == existing_run_id)
            ).scalar_one()
            run.source_name = ",".join(s["name"] for s in sources)
            run.source_url = ";".join(s.get("url", "") for s in sources)
            run.started_at = datetime.utcnow()
            run.status = RunStatus.running
            self.db.commit()
        else:
            run = ScrapeRun(
                source_name=",".join(s["name"] for s in sources),
                source_url=";".join(s.get("url", "") for s in sources),
                started_at=datetime.utcnow(),
                status=RunStatus.running,
            )
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)

        log_buffer.init_run(run.id)
        _log(run.id, "INFO", f"Run #{run.id} started — {len(sources)} sources")

        seen_canonical_keys: set = set()
        seen_this_run: set = set()  # dedup across sources within one run
        total_inserted = 0
        total_updated = 0
        total_errors = 0

        try:
            with LinkedInScraper() as scraper:
                for source in sources:
                    _log(run.id, "INFO", f"→ Source: {source['name']}")
                    try:
                        raw_jobs = scraper.scrape_search_page(
                            source=source,
                            company=source.get("company", "Xiaomi"),
                        )
                        unique_jobs = [
                            j for j in raw_jobs
                            if j.get("canonical_job_key") not in seen_this_run
                        ]
                        dupes = len(raw_jobs) - len(unique_jobs)
                        msg = f"  Found {len(raw_jobs)} jobs"
                        if dupes:
                            msg += f" ({dupes} already seen this run, skipped)"
                        _log(run.id, "INFO", msg)

                        for raw_job in unique_jobs:
                            try:
                                key = raw_job.get("canonical_job_key")
                                if key:
                                    seen_this_run.add(key)

                                if enrich_details and raw_job.get("canonical_url"):
                                    raw_job = scraper.enrich_job_details(raw_job)

                                classification = self.classifier.classify(raw_job)
                                result = self.store.upsert_job(raw_job, classification, run.id)

                                if result["action"] == "inserted":
                                    total_inserted += 1
                                    _log(run.id, "INFO",
                                         f"  + NEW: {raw_job.get('title')} [{classification.ev_label.value}]")
                                elif result["action"] == "updated":
                                    total_updated += 1

                                if result.get("canonical_key"):
                                    seen_canonical_keys.add(result["canonical_key"])

                                run.jobs_seen_count += 1
                                self.db.commit()

                            except Exception as e:
                                _log(run.id, "ERROR", f"  Job error: {e}")
                                total_errors += 1

                    except Exception as e:
                        _log(run.id, "ERROR", f"  Source {source['name']} failed: {e}")
                        total_errors += 1

        except Exception as e:
            _log(run.id, "ERROR", f"Run failed: {e}")
            run.status = RunStatus.failed
            run.notes = str(e)
            run.errors_count = total_errors
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return run

        archived_count = self.archive.process_missing(run.id, seen_canonical_keys)

        run.jobs_inserted_count = total_inserted
        run.jobs_updated_count = total_updated
        run.jobs_archived_count = archived_count
        run.errors_count = total_errors
        run.finished_at = datetime.utcnow()
        run.status = RunStatus.partial if total_errors > 0 else RunStatus.success
        self.db.commit()

        _log(run.id, "INFO",
             f"Run #{run.id} done — seen={run.jobs_seen_count} "
             f"new={total_inserted} updated={total_updated} "
             f"archived={archived_count} errors={total_errors}")
        log_buffer.clear_old(keep_last=5)
        return run

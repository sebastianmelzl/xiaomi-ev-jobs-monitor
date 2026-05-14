"""
Scrape run orchestrator.
Coordinates scraping, classification, persistence, and archiving for a single run.
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger
from sqlalchemy.orm import Session

from app.scraper.linkedin import LinkedInScraper
from app.classifier.ev_classifier import EVClassifier
from app.persistence.job_store import JobStore
from app.persistence.archive_manager import ArchiveManager
from app.models import ScrapeRun, RunStatus
from app.config_loader import load_sources


class ScrapeRunner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.store = JobStore(db)
        self.archive = ArchiveManager(db)
        self.classifier = EVClassifier()

    async def run(
        self,
        source_names: Optional[List[str]] = None,
        enrich_details: bool = True,
    ) -> ScrapeRun:
        """
        Execute a full scrape run.

        1. Load sources from config
        2. Create a ScrapeRun record
        3. For each source: scrape → enrich → classify → persist
        4. Post-run: apply missing/archive logic
        5. Finalize run stats

        Returns the completed ScrapeRun.
        """
        sources = load_sources()
        if source_names:
            sources = [s for s in sources if s["name"] in source_names]
        else:
            sources = [s for s in sources if s.get("enabled", True)]

        if not sources:
            logger.warning("No enabled sources found for this run")

        run = ScrapeRun(
            source_name=",".join(s["name"] for s in sources),
            source_url=";".join(s["url"] for s in sources),
            started_at=datetime.utcnow(),
            status=RunStatus.running,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        seen_canonical_keys: List[str] = []
        total_inserted = 0
        total_updated = 0
        total_errors = 0

        try:
            async with LinkedInScraper() as scraper:
                for source in sources:
                    logger.info(f"Scraping source: {source['name']}")
                    try:
                        raw_jobs = await scraper.scrape_search_page(
                            url=source["url"],
                            company=source.get("company", "Xiaomi"),
                            max_pages=source.get("max_pages", 5),
                            scroll_count=source.get("scroll_count", 3),
                        )
                        logger.info(f"Source {source['name']}: {len(raw_jobs)} raw jobs")

                        for raw_job in raw_jobs:
                            try:
                                if enrich_details and raw_job.get("canonical_url"):
                                    raw_job = await scraper.enrich_job_details(raw_job)

                                # Classify EV relevance
                                classification = self.classifier.classify(raw_job)

                                # Persist job
                                result = self.store.upsert_job(raw_job, classification, run.id)

                                if result["action"] == "inserted":
                                    total_inserted += 1
                                elif result["action"] == "updated":
                                    total_updated += 1

                                if result.get("canonical_key"):
                                    seen_canonical_keys.append(result["canonical_key"])

                                run.jobs_seen_count += 1

                            except Exception as e:
                                logger.error(f"Job persistence error: {e}")
                                total_errors += 1
                                continue

                    except Exception as e:
                        logger.error(f"Source {source['name']} failed: {e}")
                        total_errors += 1
                        continue

        except Exception as e:
            logger.error(f"Scrape run failed: {e}")
            run.status = RunStatus.failed
            run.notes = str(e)
            run.errors_count = total_errors
            run.finished_at = datetime.utcnow()
            self.db.commit()
            return run

        # Post-run: apply missing/archive logic for jobs not seen this run
        archived_count = self.archive.process_missing(run.id, seen_canonical_keys)

        # Finalize run
        run.jobs_inserted_count = total_inserted
        run.jobs_updated_count = total_updated
        run.jobs_archived_count = archived_count
        run.errors_count = total_errors
        run.finished_at = datetime.utcnow()
        run.status = RunStatus.partial if total_errors > 0 else RunStatus.success
        self.db.commit()

        logger.info(
            f"Run {run.id} complete: seen={run.jobs_seen_count} "
            f"new={total_inserted} updated={total_updated} "
            f"archived={archived_count} errors={total_errors}"
        )
        return run

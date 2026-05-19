from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from loguru import logger

from app.database import get_db, SessionLocal
from app.models import Job

router = APIRouter()


def _enrich_missing_sync(job_ids: list) -> None:
    from app.scraper.linkedin import LinkedInScraper
    from app.scraper.normalizer import classify_department
    db = SessionLocal()
    enriched = 0
    try:
        with LinkedInScraper() as scraper:
            for job_id in job_ids:
                job = db.get(Job, job_id)
                if not job or job.description_text:
                    continue
                try:
                    result = scraper.enrich_job_details({
                        "linkedin_job_id": job.linkedin_job_id,
                        "description": None,
                        "is_reposted": job.is_reposted,
                    })
                    if result.get("description"):
                        job.description_text = result["description"]
                    if result.get("seniority_level") and not job.seniority_level:
                        job.seniority_level = result["seniority_level"]
                    if result.get("employment_type") and not job.employment_type:
                        job.employment_type = result["employment_type"]
                    if result.get("department") and not job.department:
                        job.department = classify_department(job.title, result["department"])
                    db.commit()
                    enriched += 1
                except Exception as e:
                    logger.warning(f"Enrich failed for job {job_id}: {e}")
    except Exception as e:
        logger.error(f"_enrich_missing_sync failed: {e}")
    finally:
        db.close()
    logger.info(f"Enrich missing: {enriched}/{len(job_ids)} descriptions filled")


@router.post("/admin/enrich-missing")
def enrich_missing_descriptions(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Fetch descriptions for all jobs that have none. Runs in background."""
    jobs = db.execute(
        select(Job).where(
            Job.description_text.is_(None),
            Job.linkedin_job_id.isnot(None),
        )
    ).scalars().all()

    count = len(jobs)
    if count == 0:
        return {"ok": True, "queued": 0, "message": "All jobs already have descriptions"}

    background_tasks.add_task(_enrich_missing_sync, [j.id for j in jobs])
    return {"ok": True, "queued": count, "message": f"Enriching {count} jobs in background"}


@router.post("/admin/reset")
def reset_all_data(db: Session = Depends(get_db)):
    """Delete all scraped jobs and run history. Config and hidden-job list are preserved."""
    # Order matters for FK constraints: child tables first, then parents.
    # Most child tables have CASCADE, but scrape_runs does not cascade from jobs.
    tables = [
        "job_change_log",
        "job_run_presence",
        "applicant_history",
        "job_ev_classification",
        "hidden_jobs",
        "jobs",
        "scrape_runs",
    ]
    counts = {}
    for table in tables:
        result = db.execute(text(f"DELETE FROM {table}"))
        counts[table] = result.rowcount
    db.commit()
    total = sum(counts.values())
    return {"ok": True, "deleted": counts, "total_rows": total}

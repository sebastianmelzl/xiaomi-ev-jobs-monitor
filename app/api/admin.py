from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

router = APIRouter()


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

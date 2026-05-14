"""Chart data endpoints for frontend visualizations."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta
from typing import List
import os

from app.database import get_db
from app.models import Job, JobEVClassification, ScrapeRun, JobChangeLog, ChangeType, JobStatus, EVLabel

router = APIRouter()

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")
_IS_SQLITE = _DATABASE_URL.startswith("sqlite")


def _week_expr(col):
    """Return a week-label expression compatible with SQLite and PostgreSQL."""
    if _IS_SQLITE:
        return func.strftime("%Y-%W", col)
    return func.to_char(col, "IYYY-IW")


@router.get("/charts/ev-jobs-over-time")
def ev_jobs_over_time(days: int = Query(90), db: Session = Depends(get_db)):
    """New EV-relevant jobs per week over the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        select(
            _week_expr(Job.first_seen_at).label("week"),
            func.count().label("count"),
        )
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.first_seen_at >= cutoff,
            JobEVClassification.ev_label.in_([EVLabel.core_ev, EVLabel.likely_ev, EVLabel.maybe_ev]),
        )
        .group_by("week")
        .order_by("week")
    ).all()
    return [{"week": r.week, "count": r.count} for r in rows]


@router.get("/charts/archived-over-time")
def archived_over_time(days: int = Query(90), db: Session = Depends(get_db)):
    """Archived jobs per week."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        select(
            _week_expr(Job.archived_at).label("week"),
            func.count().label("count"),
        )
        .where(Job.archived_at >= cutoff, Job.archived_at.isnot(None))
        .group_by("week")
        .order_by("week")
    ).all()
    return [{"week": r.week, "count": r.count} for r in rows]


@router.get("/charts/top-applicant-growth")
def top_applicant_growth(limit: int = Query(10), db: Session = Depends(get_db)):
    """Top jobs by absolute applicant count growth (latest - earliest reading)."""
    from app.models import ApplicantHistory
    from sqlalchemy import alias, and_

    AH1 = alias(ApplicantHistory, name="ah_first")
    AH2 = alias(ApplicantHistory, name="ah_last")

    rows = db.execute(
        select(Job.id, Job.title, Job.location, Job.job_url)
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            JobEVClassification.ev_label.in_([EVLabel.core_ev, EVLabel.likely_ev]),
        )
        .limit(200)
    ).all()

    results = []
    for job_id, title, location, url in rows:
        history = db.execute(
            select(ApplicantHistory)
            .where(
                ApplicantHistory.job_id == job_id,
                ApplicantHistory.applicant_count_min.isnot(None),
            )
            .order_by(ApplicantHistory.observed_at)
        ).scalars().all()

        if len(history) >= 2:
            first_val = history[0].applicant_count_exact or history[0].applicant_count_min
            last_val = history[-1].applicant_count_exact or history[-1].applicant_count_min
            if first_val and last_val and last_val > first_val:
                results.append({
                    "job_id": job_id,
                    "title": title,
                    "location": location,
                    "url": url,
                    "growth": last_val - first_val,
                    "current": last_val,
                })

    results.sort(key=lambda x: x["growth"], reverse=True)
    return results[:limit]


@router.get("/charts/ev-score-distribution")
def ev_score_distribution(db: Session = Depends(get_db)):
    """Distribution of EV scores in bins of 10."""
    rows = db.execute(
        select(JobEVClassification.ev_score)
        .join(Job, Job.id == JobEVClassification.job_id)
        .where(Job.status == JobStatus.active)
    ).scalars().all()

    bins = {f"{i}-{i+9}": 0 for i in range(0, 100, 10)}
    for score in rows:
        bucket = (score // 10) * 10
        key = f"{bucket}-{bucket+9}"
        bins[key] = bins.get(key, 0) + 1

    return [{"range": k, "count": v} for k, v in bins.items()]

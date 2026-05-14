from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models import Job, JobEVClassification, ScrapeRun, JobStatus, EVLabel, RunStatus
from app.schemas import OverviewResponse, EVLabelBreakdown, TopLocation

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
def get_overview(db: Session = Depends(get_db)):
    # Active jobs
    active_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.active)
    ).scalar_one()

    # EV-relevant jobs (core + likely + maybe), active only
    ev_count = db.execute(
        select(func.count())
        .select_from(Job)
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            JobEVClassification.ev_label.in_([EVLabel.core_ev, EVLabel.likely_ev, EVLabel.maybe_ev]),
        )
    ).scalar_one()

    # Archived count
    archived_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.archived)
    ).scalar_one()

    # Missing count
    missing_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.missing)
    ).scalar_one()

    # Last successful scrape run
    last_run = db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.status.in_([RunStatus.success, RunStatus.partial]))
        .order_by(desc(ScrapeRun.finished_at))
        .limit(1)
    ).scalar_one_or_none()

    # New jobs since last run
    new_since_last = 0
    if last_run and last_run.started_at:
        new_since_last = db.execute(
            select(func.count()).where(Job.first_seen_at >= last_run.started_at)
        ).scalar_one()

    # EV label breakdown
    breakdown_rows = db.execute(
        select(JobEVClassification.ev_label, func.count())
        .join(Job, Job.id == JobEVClassification.job_id)
        .where(Job.status == JobStatus.active)
        .group_by(JobEVClassification.ev_label)
    ).all()

    breakdown = EVLabelBreakdown()
    for label, count in breakdown_rows:
        if label == EVLabel.core_ev:
            breakdown.core_ev = count
        elif label == EVLabel.likely_ev:
            breakdown.likely_ev = count
        elif label == EVLabel.maybe_ev:
            breakdown.maybe_ev = count
        elif label == EVLabel.non_ev:
            breakdown.non_ev = count

    # Top locations (active jobs with EV relevance)
    location_rows = db.execute(
        select(Job.location, func.count().label("cnt"))
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            Job.location.isnot(None),
            JobEVClassification.ev_label.in_([EVLabel.core_ev, EVLabel.likely_ev]),
        )
        .group_by(Job.location)
        .order_by(desc("cnt"))
        .limit(10)
    ).all()

    top_locations = [TopLocation(location=loc, count=cnt) for loc, cnt in location_rows]

    return OverviewResponse(
        active_jobs_count=active_count,
        ev_jobs_count=ev_count,
        new_jobs_since_last_run=new_since_last,
        archived_jobs_count=archived_count,
        missing_jobs_count=missing_count,
        last_scrape_at=last_run.finished_at if last_run else None,
        last_scrape_status=last_run.status.value if last_run else None,
        ev_label_breakdown=breakdown,
        top_locations=top_locations,
    )

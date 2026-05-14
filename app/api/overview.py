from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, not_
from datetime import datetime, timedelta

from app.database import get_db
from app.models import Job, JobEVClassification, HiddenJob, ScrapeRun, JobStatus, EVLabel, RunStatus
from app.schemas import OverviewResponse, EVLabelBreakdown, TopLocation

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
def get_overview(db: Session = Depends(get_db)):
    hidden_ids = select(HiddenJob.job_id).scalar_subquery()

    # Active core EV jobs (not hidden)
    ev_count = db.execute(
        select(func.count())
        .select_from(Job)
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            JobEVClassification.ev_label == EVLabel.core_ev,
            not_(Job.id.in_(hidden_ids)),
        )
    ).scalar_one()

    # All active jobs count
    active_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.active)
    ).scalar_one()

    # Jobs posted in last 7 days (by LinkedIn posted date)
    week_ago = datetime.utcnow() - timedelta(days=7)
    posted_this_week = db.execute(
        select(func.count())
        .select_from(Job)
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            JobEVClassification.ev_label == EVLabel.core_ev,
            Job.posted_date_normalized >= week_ago,
            Job.posted_date_normalized.isnot(None),
            not_(Job.id.in_(hidden_ids)),
        )
    ).scalar_one()

    # Missing / archived
    missing_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.missing)
    ).scalar_one()
    archived_count = db.execute(
        select(func.count()).where(Job.status == JobStatus.archived)
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
            select(func.count())
            .select_from(Job)
            .join(JobEVClassification, Job.id == JobEVClassification.job_id)
            .where(
                Job.first_seen_at >= last_run.started_at,
                JobEVClassification.ev_label == EVLabel.core_ev,
            )
        ).scalar_one()

    # EV label breakdown (kept for schema compat, not shown in new UI)
    breakdown = EVLabelBreakdown(core_ev=ev_count)

    # Top locations (core EV, active, not hidden)
    location_rows = db.execute(
        select(Job.location, func.count().label("cnt"))
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            Job.location.isnot(None),
            JobEVClassification.ev_label == EVLabel.core_ev,
            not_(Job.id.in_(hidden_ids)),
        )
        .group_by(Job.location)
        .order_by(desc("cnt"))
        .limit(8)
    ).all()

    top_locations = [TopLocation(location=loc, count=cnt) for loc, cnt in location_rows]

    return OverviewResponse(
        active_jobs_count=active_count,
        ev_jobs_count=ev_count,
        posted_this_week=posted_this_week,
        new_jobs_since_last_run=new_since_last,
        archived_jobs_count=archived_count,
        missing_jobs_count=missing_count,
        last_scrape_at=last_run.finished_at if last_run else None,
        last_scrape_status=last_run.status.value if last_run else None,
        ev_label_breakdown=breakdown,
        top_locations=top_locations,
    )

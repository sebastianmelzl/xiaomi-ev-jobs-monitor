from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, desc, asc, or_, not_
from typing import Optional, List
from datetime import datetime
from datetime import datetime, timedelta

from app.database import get_db
from app.models import (
    Job, JobEVClassification, ApplicantHistory, JobChangeLog,
    HiddenJob, JobStatus, EVLabel, ApplicantQuality
)
from app.schemas import PaginatedJobs, JobListItem, JobDetail, ApplicantHistoryPoint, ChangeLogEntry

router = APIRouter()


def _build_job_list_item(job: Job) -> JobListItem:
    """Assemble a JobListItem from a Job ORM object with preloaded relationships."""
    ev_label = None
    ev_score = None
    ev_confidence = None
    if job.ev_classification:
        ev_label = job.ev_classification.ev_label
        ev_score = job.ev_classification.ev_score
        ev_confidence = job.ev_classification.ev_confidence

    # Applicant aggregates from history
    current_count = None
    current_quality = None
    delta_24h = None
    delta_7d = None

    if job.applicant_history:
        latest = job.applicant_history[-1]
        current_count = latest.applicant_count_exact or latest.applicant_count_min
        current_quality = latest.applicant_count_quality

        now = datetime.utcnow()
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)

        # Find the closest data point before 24h ago
        for h in reversed(job.applicant_history[:-1]):
            if h.observed_at <= cutoff_24h:
                old_val = h.applicant_count_exact or h.applicant_count_min
                if old_val and current_count:
                    delta_24h = current_count - old_val
                break

        for h in job.applicant_history:
            if h.observed_at <= cutoff_7d:
                old_val = h.applicant_count_exact or h.applicant_count_min
                if old_val and current_count:
                    delta_7d = current_count - old_val
                break

    return JobListItem(
        id=job.id,
        linkedin_job_id=job.linkedin_job_id,
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        department=job.department,
        employment_type=job.employment_type,
        seniority_level=job.seniority_level,
        job_url=job.job_url,
        posted_text_raw=job.posted_text_raw,
        posted_date_normalized=job.posted_date_normalized,
        status=job.status,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        archived_at=job.archived_at,
        missing_count=job.missing_count,
        ev_label=ev_label,
        ev_score=ev_score,
        ev_confidence=ev_confidence,
        applicant_count_current=current_count,
        applicant_count_quality=current_quality,
        applicant_delta_24h=delta_24h,
        applicant_delta_7d=delta_7d,
    )


@router.get("/jobs/departments")
def list_departments(db: Session = Depends(get_db)):
    """Return distinct non-null departments for active EV jobs."""
    rows = db.execute(
        select(Job.department)
        .join(JobEVClassification, Job.id == JobEVClassification.job_id)
        .where(
            Job.status == JobStatus.active,
            Job.department.isnot(None),
            JobEVClassification.ev_label == EVLabel.core_ev,
        )
        .distinct()
        .order_by(Job.department)
    ).scalars().all()
    return [r for r in rows if r]


@router.get("/jobs", response_model=PaginatedJobs)
def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ev_label: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    ev_only: bool = Query(False),
    sort_by: str = Query("department"),
    sort_dir: str = Query("asc"),
    db: Session = Depends(get_db),
):
    hidden_ids = select(HiddenJob.job_id).scalar_subquery()
    query = (
        select(Job)
        .options(
            selectinload(Job.ev_classification),
            selectinload(Job.applicant_history),
        )
        .where(not_(Job.id.in_(hidden_ids)))
    )

    # Filters
    if status:
        try:
            query = query.where(Job.status == JobStatus(status))
        except ValueError:
            pass

    if ev_only or ev_label:
        query = query.join(JobEVClassification, Job.id == JobEVClassification.job_id)
        if ev_only:
            query = query.where(
                JobEVClassification.ev_label == EVLabel.core_ev
            )
        if ev_label:
            try:
                query = query.where(JobEVClassification.ev_label == EVLabel(ev_label))
            except ValueError:
                pass

    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Job.title.ilike(term),
                Job.location.ilike(term),
                Job.department.ilike(term),
                Job.company_name.ilike(term),
            )
        )

    if location:
        query = query.where(Job.location.ilike(f"%{location}%"))

    if department:
        query = query.where(Job.department == department)

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar_one()

    # Sorting
    sort_col = getattr(Job, sort_by, Job.first_seen_at)
    if sort_dir == "asc":
        query = query.order_by(asc(sort_col))
    else:
        query = query.order_by(desc(sort_col))

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    jobs = db.execute(query).scalars().all()
    items = [_build_job_list_item(j) for j in jobs]

    return PaginatedJobs(total=total, page=page, page_size=page_size, items=items)


@router.get("/jobs/hidden")
def list_hidden_jobs(db: Session = Depends(get_db)):
    rows = db.execute(
        select(HiddenJob, Job)
        .join(Job, Job.id == HiddenJob.job_id)
        .order_by(desc(HiddenJob.hidden_at))
    ).all()
    return [
        {
            "job_id": h.job_id,
            "hidden_at": h.hidden_at.isoformat(),
            "title": j.title,
            "company": j.company_name,
            "location": j.location,
            "department": j.department,
            "job_url": j.job_url,
        }
        for h, j in rows
    ]


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.execute(
        select(Job)
        .options(
            selectinload(Job.ev_classification),
            selectinload(Job.applicant_history),
            selectinload(Job.change_log),
        )
        .where(Job.id == job_id)
    ).scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobDetail.model_validate(job)


@router.get("/jobs/{job_id}/applicants-history", response_model=List[ApplicantHistoryPoint])
def get_applicant_history(job_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(ApplicantHistory)
        .where(ApplicantHistory.job_id == job_id)
        .order_by(ApplicantHistory.observed_at)
    ).scalars().all()
    return [ApplicantHistoryPoint.model_validate(r) for r in rows]


@router.get("/jobs/{job_id}/changes", response_model=List[ChangeLogEntry])
def get_job_changes(job_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(JobChangeLog)
        .where(JobChangeLog.job_id == job_id)
        .order_by(desc(JobChangeLog.changed_at))
    ).scalars().all()
    return [ChangeLogEntry.model_validate(r) for r in rows]


# ── Hide / unhide ─────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/hide")
def hide_job(job_id: int, db: Session = Depends(get_db)):
    job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = db.execute(select(HiddenJob).where(HiddenJob.job_id == job_id)).scalar_one_or_none()
    if not existing:
        db.add(HiddenJob(job_id=job_id, hidden_at=datetime.utcnow()))
        db.commit()
    return {"hidden": True, "job_id": job_id}


@router.delete("/jobs/{job_id}/hide")
def unhide_job(job_id: int, db: Session = Depends(get_db)):
    row = db.execute(select(HiddenJob).where(HiddenJob.job_id == job_id)).scalar_one_or_none()
    if row:
        db.delete(row)
        db.commit()
    return {"hidden": False, "job_id": job_id}

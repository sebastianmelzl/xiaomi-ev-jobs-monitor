from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func, desc
from typing import Optional

from app.database import get_db
from app.models import Job, JobEVClassification, JobStatus, EVLabel
from app.schemas import PaginatedJobs, JobListItem
from app.api.jobs import _build_job_list_item

router = APIRouter()


@router.get("/archive", response_model=PaginatedJobs)
def list_archive(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ev_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = (
        select(Job)
        .options(
            selectinload(Job.ev_classification),
            selectinload(Job.applicant_history),
        )
        .where(Job.status == JobStatus.archived)
    )

    if ev_only:
        query = (
            query
            .join(JobEVClassification, Job.id == JobEVClassification.job_id)
            .where(
                JobEVClassification.ev_label.in_([EVLabel.core_ev, EVLabel.likely_ev, EVLabel.maybe_ev])
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar_one()

    offset = (page - 1) * page_size
    jobs = db.execute(
        query.order_by(desc(Job.archived_at)).offset(offset).limit(page_size)
    ).scalars().all()

    items = [_build_job_list_item(j) for j in jobs]
    return PaginatedJobs(total=total, page=page, page_size=page_size, items=items)

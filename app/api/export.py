import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, desc
from typing import Optional

from app.database import get_db
from app.models import Job, JobEVClassification, JobStatus, EVLabel

router = APIRouter()

EV_LABELS = [EVLabel.core_ev, EVLabel.likely_ev, EVLabel.maybe_ev]


@router.get("/export/ev-jobs.csv")
def export_ev_jobs_csv(
    ev_only: bool = Query(True),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = (
        select(Job)
        .options(
            selectinload(Job.ev_classification),
            selectinload(Job.applicant_history),
        )
    )

    if not include_archived:
        query = query.where(Job.status == JobStatus.active)

    if ev_only:
        query = (
            query
            .join(JobEVClassification, Job.id == JobEVClassification.job_id)
            .where(JobEVClassification.ev_label.in_(EV_LABELS))
        )

    jobs = db.execute(query.order_by(desc(Job.first_seen_at))).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Title", "Company", "Location", "Department",
        "Employment Type", "Seniority", "EV Label", "EV Score",
        "Status", "Posted Date", "First Seen", "Last Seen",
        "Applicants (current)", "Applicant Quality", "URL",
        "EV Reasoning",
    ])

    for job in jobs:
        ev = job.ev_classification
        applicants = None
        quality = None
        if job.applicant_history:
            latest = job.applicant_history[-1]
            applicants = latest.applicant_count_exact or latest.applicant_count_min
            quality = latest.applicant_count_quality.value if latest.applicant_count_quality else None

        reasoning = "; ".join(ev.reasoning_json) if ev and ev.reasoning_json else ""

        writer.writerow([
            job.id,
            job.title or "",
            job.company_name or "",
            job.location or "",
            job.department or "",
            job.employment_type or "",
            job.seniority_level or "",
            ev.ev_label.value if ev else "",
            ev.ev_score if ev else "",
            job.status.value,
            job.posted_date_normalized.isoformat() if job.posted_date_normalized else job.posted_text_raw or "",
            job.first_seen_at.isoformat(),
            job.last_seen_at.isoformat(),
            applicants or "",
            quality or "",
            job.job_url or "",
            reasoning,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=xiaomi-ev-jobs.csv"},
    )

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Annotated
from pydantic import BaseModel, ConfigDict
from pydantic.functional_serializers import PlainSerializer
from app.models import JobStatus, EVLabel, ApplicantQuality, RunStatus, ChangeType

# Naive UTC datetimes from SQLite lack tzinfo.  Appending 'Z' tells JavaScript
# to treat the value as UTC so toLocaleDateString() converts to browser timezone.
UTCDatetime = Annotated[
    datetime,
    PlainSerializer(lambda v: v.isoformat() + 'Z', return_type=str, when_used='json'),
]
OptUTCDatetime = Annotated[
    Optional[datetime],
    PlainSerializer(
        lambda v: v.isoformat() + 'Z' if v is not None else None,
        return_type=Optional[str],
        when_used='json',
    ),
]


# ── Applicant history ────────────────────────────────────────────────────────

class ApplicantHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    observed_at: UTCDatetime
    raw_applicant_text: Optional[str]
    applicant_count_exact: Optional[int]
    applicant_count_min: Optional[int]
    applicant_count_quality: ApplicantQuality


# ── EV Classification ─────────────────────────────────────────────────────────

class EVClassification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ev_score: int
    ev_confidence: float
    ev_label: EVLabel
    reasoning_json: List[str]
    classifier_version: str
    classified_at: UTCDatetime


# ── Change log ────────────────────────────────────────────────────────────────

class ChangeLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    changed_at: UTCDatetime
    field_name: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    change_type: ChangeType


# ── Job (list view) ───────────────────────────────────────────────────────────

class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linkedin_job_id: Optional[str]
    title: Optional[str]
    company_name: Optional[str]
    location: Optional[str]
    department: Optional[str]
    employment_type: Optional[str]
    seniority_level: Optional[str]
    job_url: Optional[str]
    posted_text_raw: Optional[str]
    posted_date_normalized: OptUTCDatetime
    is_reposted: bool = False
    status: JobStatus
    first_seen_at: UTCDatetime
    last_seen_at: UTCDatetime
    archived_at: OptUTCDatetime
    missing_count: int

    ev_label: Optional[EVLabel] = None
    ev_score: Optional[int] = None
    ev_confidence: Optional[float] = None

    applicant_count_current: Optional[int] = None
    applicant_count_quality: Optional[ApplicantQuality] = None
    applicant_delta_24h: Optional[int] = None
    applicant_delta_7d: Optional[int] = None


# ── Job (detail view) ─────────────────────────────────────────────────────────

class JobDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    linkedin_job_id: Optional[str]
    canonical_job_key: str
    title: Optional[str]
    company_name: Optional[str]
    location: Optional[str]
    department: Optional[str]
    employment_type: Optional[str]
    seniority_level: Optional[str]
    job_url: Optional[str]
    canonical_url: Optional[str]
    description_text: Optional[str]
    posted_text_raw: Optional[str]
    posted_date_normalized: OptUTCDatetime
    is_reposted: bool = False
    status: JobStatus
    first_seen_at: UTCDatetime
    last_seen_at: UTCDatetime
    archived_at: OptUTCDatetime
    missing_count: int
    ev_classification: Optional[EVClassification] = None
    applicant_history: List[ApplicantHistoryPoint] = []
    change_log: List[ChangeLogEntry] = []


# ── Scrape runs ───────────────────────────────────────────────────────────────

class ScrapeRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: Optional[str]
    source_url: Optional[str]
    started_at: UTCDatetime
    finished_at: OptUTCDatetime
    status: RunStatus
    jobs_seen_count: int
    jobs_inserted_count: int
    jobs_updated_count: int
    jobs_archived_count: int
    errors_count: int
    notes: Optional[str]


# ── Overview ──────────────────────────────────────────────────────────────────

class EVLabelBreakdown(BaseModel):
    core_ev: int = 0
    likely_ev: int = 0
    maybe_ev: int = 0
    non_ev: int = 0


class TopLocation(BaseModel):
    location: str
    count: int


class OverviewResponse(BaseModel):
    active_jobs_count: int
    ev_jobs_count: int
    posted_this_week: int
    new_jobs_since_last_run: int
    archived_jobs_count: int
    missing_jobs_count: int
    last_scrape_at: OptUTCDatetime
    last_scrape_status: Optional[str]
    ev_label_breakdown: EVLabelBreakdown
    top_locations: List[TopLocation]


# ── Paginated response ────────────────────────────────────────────────────────

class PaginatedJobs(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[JobListItem]


# ── Scrape trigger ────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    source_names: Optional[List[str]] = None


class ScrapeResponse(BaseModel):
    run_id: int
    message: str
    started: bool

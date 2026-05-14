import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from typing import Optional, List

from app.database import get_db, SessionLocal
from app.models import ScrapeRun, RunStatus
from app.schemas import ScrapeRunSchema, ScrapeRequest, ScrapeResponse
from app.scheduler.scheduler import get_scheduler_status
from loguru import logger

router = APIRouter()

_active_run_id: Optional[int] = None


def _run_scrape_sync(source_names: Optional[List[str]] = None, run_id: Optional[int] = None) -> None:
    global _active_run_id
    from app.scraper.runner import ScrapeRunner

    db = SessionLocal()
    try:
        runner = ScrapeRunner(db)
        run = runner.run(source_names=source_names, existing_run_id=run_id)
        _active_run_id = None
        logger.info(f"Scrape run {run.id} finished: {run.status}")
    except Exception as e:
        logger.error(f"Background scrape failed: {e}")
        _active_run_id = None
    finally:
        db.close()


@router.post("/scrape/run", response_model=ScrapeResponse)
def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    global _active_run_id
    if _active_run_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A scrape run is already in progress (run_id={_active_run_id})"
        )

    # Create a placeholder run record immediately so UI can show it
    run = ScrapeRun(status=RunStatus.running, source_name="manual")
    db.add(run)
    db.commit()
    db.refresh(run)
    _active_run_id = run.id

    background_tasks.add_task(_run_scrape_sync, request.source_names, run.id)

    return ScrapeResponse(run_id=run.id, message="Scrape started", started=True)


@router.get("/scrape/runs", response_model=List[ScrapeRunSchema])
def list_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    runs = db.execute(
        select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(limit)
    ).scalars().all()
    return [ScrapeRunSchema.model_validate(r) for r in runs]


@router.get("/scrape/runs/{run_id}", response_model=ScrapeRunSchema)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return ScrapeRunSchema.model_validate(run)


@router.get("/scrape/runs/{run_id}/logs")
def get_run_logs(run_id: int):
    from app.scraper import log_buffer
    return {"run_id": run_id, "logs": log_buffer.get(run_id)}


@router.get("/scrape/status")
def scrape_status():
    return {
        "active_run_id": _active_run_id,
        "is_running": _active_run_id is not None,
        "scheduler": get_scheduler_status(),
    }

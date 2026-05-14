"""
APScheduler-based background scheduler for periodic scrape runs.
Activated via SCHEDULER_ENABLED=true in .env.
"""
import os
from datetime import datetime
from typing import Optional
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
SCHEDULER_INTERVAL_HOURS = float(os.getenv("SCHEDULER_INTERVAL_HOURS", "12"))

_scheduler: Optional[BackgroundScheduler] = None


def _run_scheduled_scrape() -> None:
    """Synchronous wrapper that runs the async scrape in a new event loop."""
    from app.database import SessionLocal
    from app.scraper.runner import ScrapeRunner

    logger.info(f"Scheduled scrape triggered at {datetime.utcnow().isoformat()}")
    db = SessionLocal()
    try:
        runner = ScrapeRunner(db)
        runner.run()
    except Exception as e:
        logger.error(f"Scheduled scrape failed: {e}")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_scheduled_scrape,
        trigger=IntervalTrigger(hours=SCHEDULER_INTERVAL_HOURS),
        id="scrape_job",
        name="LinkedIn Xiaomi EV scrape",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info(
        f"Scheduler started: every {SCHEDULER_INTERVAL_HOURS}h, "
        f"next run: {_scheduler.get_job('scrape_job').next_run_time}"
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    if not _scheduler or not _scheduler.running:
        return {"enabled": SCHEDULER_ENABLED, "running": False, "next_run": None}
    job = _scheduler.get_job("scrape_job")
    return {
        "enabled": SCHEDULER_ENABLED,
        "running": True,
        "interval_hours": SCHEDULER_INTERVAL_HOURS,
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }

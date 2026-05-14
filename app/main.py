import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Configure loguru
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logger.add(LOG_DIR / "app.log", rotation="10 MB", retention="30 days", level="INFO")
logger.add(LOG_DIR / "scraper.log", rotation="10 MB", retention="30 days", level="DEBUG",
           filter=lambda r: "scraper" in r["name"] or "linkedin" in r["name"])

from app.database import init_db
from app.api import overview, jobs, archive, scrape, export, charts
from app.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Xiaomi EV Jobs Monitor")
    init_db()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down")


app = FastAPI(
    title="Xiaomi EV Jobs Monitor",
    description="LinkedIn job monitoring dashboard for Xiaomi EV roles",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
for api_router in [overview.router, jobs.router, archive.router, scrape.router, export.router, charts.router]:
    app.include_router(api_router, prefix="/api")

# Static files
STATIC_DIR = Path("frontend/static")
TEMPLATE_DIR = Path("frontend/templates")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# SPA fallback — all non-API routes serve the frontend
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index = TEMPLATE_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "Frontend not found"}

# ⚡ Xiaomi EV Jobs Monitor

A production-grade local web application for monitoring LinkedIn jobs from Xiaomi with a focus on EV (electric vehicle) roles. Tracks applicant counts over time, detects new and vanished postings, and presents everything in a professional analytics dashboard.

---

## Features

- **LinkedIn scraper** via Playwright — multi-source, paginated, scroll-aware
- **EV relevance classifier** — rule-based scoring (0–100) with transparent reasoning
- **Applicant history tracking** — time series per job, handles "over 200 applicants" gracefully
- **Missing/archive logic** — jobs disappear after a configurable threshold of missed runs
- **Professional dashboard** — dark/light mode, KPI cards, ECharts charts, filterable tables
- **CSV export** — one-click export of all EV-relevant jobs
- **APScheduler** — optional automatic scrapes every N hours
- **SQLAlchemy ORM** — SQLite by default, Postgres-compatible models
- **FastAPI backend** — async, self-documenting OpenAPI
- **Full audit trail** — change log per job, run presence tracking

---

## Setup

### Requirements

- Python 3.12+
- No Docker required

### Install & Start

```bash
cd xiaomi-ev-jobs-v2
./start.sh
```

The script:
1. Creates a `.venv` virtual environment
2. Installs all Python dependencies
3. Installs Playwright's Chromium browser
4. Copies `.env.example` → `.env` (if not present)
5. Creates `data/` and `logs/` directories
6. Starts the app at `http://127.0.0.1:8000`

### Manual start (after first run of `start.sh`)

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Configuration

### `.env`

```env
# Core
APP_HOST=127.0.0.1
APP_PORT=8000

# Database
DATABASE_URL=sqlite:///./data/jobs.db
# For Postgres: DATABASE_URL=postgresql://user:pass@localhost:5432/xiaomi_ev_jobs

# Scraper behavior
SCRAPER_HEADLESS=true          # false = show browser window (useful for debugging)
SCRAPER_MIN_DELAY_S=2.0        # minimum delay between requests
SCRAPER_MAX_DELAY_S=5.0        # maximum delay
SCRAPER_MAX_RETRIES=3
SCRAPER_TIMEOUT_MS=30000

# LinkedIn login (optional — enables applicant count scraping)
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword

# Archiving
ARCHIVE_MISSING_THRESHOLD=3    # # of consecutive missed runs before archiving

# Scheduler
SCHEDULER_ENABLED=false
SCHEDULER_INTERVAL_HOURS=12
```

### `config/sources.yml`

Defines which LinkedIn URLs to scrape. Each source has:
- `name` — unique identifier
- `enabled` — toggle without deleting
- `url` — LinkedIn job search URL
- `company` — company name (used when not extractable from page)
- `max_pages` — how many paginated pages to fetch
- `scroll_count` — how many scroll-downs to trigger lazy loading

### `config/ev_positive_keywords.yml`

Keyword clusters driving positive EV scores. Three tiers:
- `hard` — +25 pts per hit (capped at 75): explicit EV/automotive terms
- `soft` — +10 pts per hit (capped at 20): general automotive context
- `context` — +5 pts per hit (capped at 10): weak signals

Location boost: +10 pts for jobs in known automotive hubs (Munich, Stuttgart, etc.)

### `config/ev_negative_keywords.yml`

Keyword clusters triggering score penalties:
- `strong` — -30 pts: smartphone, mobile phone, handset
- `moderate` — -15 pts: e-commerce, online retail
- `weak` — -5 pts: generic consumer support

Excluded title patterns: regex patterns that force `ev_label = non_ev` regardless of score.

---

## Scheduler

Enable automatic scraping by setting in `.env`:

```env
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_HOURS=12
```

The scheduler runs in the background. Status is visible in **Settings → Scheduler**.

---

## Data Model

### `jobs`
Core job table. One row per unique job (identified by `canonical_job_key`).

| Column | Type | Description |
|---|---|---|
| `canonical_job_key` | unique string | `linkedin:{id}` or `hash:{sha256}` |
| `status` | enum | `active`, `missing`, `archived` |
| `missing_count` | int | Consecutive runs not seen |
| `first_seen_at` / `last_seen_at` | datetime | Tracking timestamps |

### `job_ev_classification`
One-to-one with `jobs`. EV relevance score + label + reasoning.

### `applicant_history`
One-to-many with `jobs`. Each scrape that finds applicant data writes one row.
Stores `raw_applicant_text`, `applicant_count_exact`, `applicant_count_min`, and `applicant_count_quality` (`exact` / `lower_bound` / `unavailable`).

### `scrape_runs`
One row per scrape execution with stats: seen/inserted/updated/archived/errors.

### `job_run_presence`
Records whether a job was seen in each run (both present and absent).

### `job_change_log`
Audit trail: every status change, field update, reactivation, or archive event.

---

## EV Classification

The classifier scores each job on a 0–100 scale:

```
score = Σ(positive keyword hits) + location_boost - Σ(negative keyword penalties)
score = clamp(score, 0, 100)
```

Labels:
| Label | Score | Meaning |
|---|---|---|
| `core_ev` | ≥ 60 | Clearly an EV/automotive role |
| `likely_ev` | ≥ 35 | Strong automotive signals |
| `maybe_ev` | ≥ 15 | Some relevant keywords |
| `non_ev` | < 15 | Unlikely to be EV-relevant |

**Excluded title patterns** bypass scoring entirely and force `non_ev`.

To extend rules: edit `config/ev_positive_keywords.yml` or `ev_negative_keywords.yml` and restart the app.

---

## Archiving Logic

```
Run N:   Job A seen     → missing_count = 0,  status = active
Run N+1: Job A NOT seen → missing_count = 1,  status = missing
Run N+2: Job A NOT seen → missing_count = 2,  status = missing
Run N+3: Job A NOT seen → missing_count = 3 ≥ threshold → status = archived
Run N+4: Job A seen     → missing_count = 0,  status = active  (reactivation event logged)
```

Threshold is configurable via `ARCHIVE_MISSING_THRESHOLD` (default: 3).

---

## API Reference

| Endpoint | Description |
|---|---|
| `GET /api/overview` | KPI summary |
| `GET /api/jobs` | Paginated job list with filters |
| `GET /api/jobs/{id}` | Full job detail |
| `GET /api/jobs/{id}/applicants-history` | Applicant time series |
| `GET /api/jobs/{id}/changes` | Change log |
| `GET /api/archive` | Archived jobs |
| `POST /api/scrape/run` | Trigger manual scrape |
| `GET /api/scrape/runs` | Scrape run history |
| `GET /api/scrape/status` | Active run + scheduler status |
| `GET /api/export/ev-jobs.csv` | CSV export |
| `GET /api/charts/*` | Chart data endpoints |
| `GET /docs` | Interactive OpenAPI docs |

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

Tests cover:
- URL canonicalization
- Applicant count parsing (exact / lower-bound / unavailable)
- EV classifier (scoring, labels, location boost, excluded patterns)
- Archive logic (missing threshold, reactivation)
- Deduplication (idempotent upserts)

---

## Known Limitations

- LinkedIn's HTML structure changes periodically. If scraping breaks, check `app/scraper/extractors.py` and update selectors.
- Without LinkedIn credentials, applicant counts are often unavailable (hidden behind login).
- Public job search results may be incomplete vs. authenticated views.
- The classifier is rule-based; ambiguous roles (e.g. "Software Engineer") may be misclassified without rich description text.
- LinkedIn rate-limits aggressive scrapers. The built-in random delays reduce — but don't eliminate — this risk.

---

## ⚠️ Legal & Compliance Notice

This tool is designed for **personal research and monitoring only**.

LinkedIn's Terms of Service (Section 8.2) **prohibit automated data collection** from the platform without explicit written permission from LinkedIn. Scraping LinkedIn may:

- Result in account suspension or IP bans
- Constitute a violation of the Computer Fraud and Abuse Act (CFAA) in the US
- Be subject to legal action (LinkedIn vs. hiQ Labs, 2022)

**By using this tool, you accept full responsibility for compliance** with LinkedIn's ToS, applicable laws in your jurisdiction, and any consequences of use. The author provides this code for educational purposes only and assumes no liability.

Recommended practices:
- Use low scrape frequencies (every 12–24 hours)
- Do not scrape behind authentication without explicit consent
- Do not redistribute scraped data commercially
- Respect robots.txt

---

## Project Structure

```
xiaomi-ev-jobs-v2/
├── app/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── database.py              # SQLAlchemy engine + session
│   ├── models.py                # All ORM models + enums
│   ├── schemas.py               # Pydantic response schemas
│   ├── config_loader.py         # YAML config loader
│   ├── api/                     # FastAPI routers
│   ├── scraper/                 # Playwright scraper
│   ├── classifier/              # EV relevance classifier
│   ├── persistence/             # Job store + archive manager
│   └── scheduler/               # APScheduler wrapper
├── frontend/
│   ├── templates/index.html     # SPA shell
│   └── static/css|js/           # Styles + JS modules
├── config/
│   ├── sources.yml
│   ├── ev_positive_keywords.yml
│   └── ev_negative_keywords.yml
├── tests/                       # pytest test suite
├── migrations/                  # Alembic migrations
├── data/                        # SQLite database (gitignored)
├── logs/                        # Log files (gitignored)
├── requirements.txt
├── .env.example
├── start.sh
└── README.md
```

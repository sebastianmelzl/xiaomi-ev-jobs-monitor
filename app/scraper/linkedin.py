"""
LinkedIn scraper using the public guest API (requests + BeautifulSoup).
No browser automation — works reliably from server environments.
"""
import re
import time
import random
import os
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger

from app.scraper.normalizer import (
    canonicalize_linkedin_url, make_canonical_job_key,
    parse_posted_date, parse_applicant_count, normalize_location,
)

SCRAPER_MIN_DELAY = float(os.getenv("SCRAPER_MIN_DELAY_S", "1.2"))
SCRAPER_MAX_DELAY = float(os.getenv("SCRAPER_MAX_DELAY_S", "2.5"))

_GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_GUEST_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.linkedin.com/",
}


def _delay() -> None:
    time.sleep(random.uniform(SCRAPER_MIN_DELAY, SCRAPER_MAX_DELAY))


_KEEP_TAGS = {"ul", "ol", "li", "p", "strong", "em", "b", "i", "br", "h1", "h2", "h3", "h4"}

_REPOST_KEYWORDS = ["repost", "erneut", "republish", "re-post"]


def _is_repost_text(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _REPOST_KEYWORDS)


def _sanitize_description(div) -> str:
    """
    Preserve LinkedIn's structural HTML (ul/li/p/strong) and strip everything else.
    Returns sanitized inner HTML, capped at 8000 chars.
    """
    for tag in div.find_all(True):
        tag.attrs = {}          # strip all attributes (href, class, style …)
        if tag.name not in _KEEP_TAGS:
            tag.unwrap()        # remove tag but keep its text/children
    return div.decode_contents().strip()[:8000]


class LinkedInScraper:
    """Sync scraper using LinkedIn's public guest API endpoints."""

    def __init__(self) -> None:
        self._session: Optional[requests.Session] = None

    def __enter__(self) -> "LinkedInScraper":
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        return self

    def __exit__(self, *_) -> None:
        if self._session:
            self._session.close()
            self._session = None

    # ── Public interface (mirrors old async API, now sync) ────────────────────

    def scrape_search_page(self, source: Dict[str, Any], company: str = "Xiaomi") -> List[Dict[str, Any]]:
        """Scrape jobs for a source config dict. Routes by source['type']."""
        src_type = source.get("type", "company")
        max_results = source.get("max_results", 100)
        geo_id = str(source.get("geo_id", "91000002"))

        if src_type == "company":
            return self._scrape_company(
                company_id=str(source["company_id"]),
                geo_id=geo_id,
                company=company,
                max_results=max_results,
            )
        elif src_type == "keyword":
            return self._scrape_keyword(
                keywords=source["keywords"],
                geo_id=geo_id,
                company=company,
                max_results=max_results,
            )
        return []

    def enrich_job_details(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch full description and criteria from the guest detail endpoint."""
        job_id = job.get("linkedin_job_id")
        if not job_id:
            return job
        try:
            resp = self._session.get(_GUEST_DETAIL.format(job_id), timeout=20)
            if resp.status_code == 429:
                logger.warning("Rate limited on detail fetch, sleeping 15s")
                time.sleep(15)
                resp = self._session.get(_GUEST_DETAIL.format(job_id), timeout=20)
            if resp.status_code != 200:
                return job

            soup = BeautifulSoup(resp.text, "html.parser")

            desc_div = (
                soup.find("div", class_=re.compile(r"show-more-less-html__markup"))
                or soup.find("div", class_=re.compile(r"description__text"))
                or soup.find("div", class_=re.compile(r"decorated-job-posting__details"))
            )
            if desc_div:
                job["description"] = _sanitize_description(desc_div)

            for item in soup.find_all("li", class_=re.compile(r"description__job-criteria-item")):
                label = item.find("h3")
                value = item.find("span")
                if not label or not value:
                    continue
                lbl = label.get_text(strip=True).lower()
                val = value.get_text(strip=True)
                if "seniority" in lbl:
                    job["seniority_level"] = val
                elif "employment" in lbl or "job type" in lbl:
                    job["employment_type"] = val
                elif "function" in lbl or "department" in lbl:
                    job["department"] = val

            # Repost detection: scan raw response text for any repost phrase
            if not job.get("is_reposted") and _is_repost_text(resp.text):
                job["is_reposted"] = True

            count_el = (
                soup.find("figcaption", class_=re.compile(r"num-applicants"))
                or soup.find(class_=re.compile(r"num-applicants__caption"))
                or soup.find(class_=re.compile(r"jobs-unified-top-card__applicant-count"))
            )
            raw_count = ""
            if count_el:
                raw_count = count_el.get_text(strip=True)
            else:
                m = re.search(r"([\d,]+\+?\s*(?:applicants?|Bewerber))", resp.text, re.IGNORECASE)
                if m:
                    raw_count = m.group(1).strip()
            if raw_count:
                parsed = parse_applicant_count(raw_count)
                job["raw_applicant_text"] = parsed["raw"]
                job["applicant_count_exact"] = parsed["exact"]
                job["applicant_count_min"] = parsed["min"]
                job["applicant_count_quality"] = parsed["quality"]

            _delay()
        except Exception as e:
            logger.warning(f"Detail enrich failed for job {job_id}: {e}")
        return job

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _scrape_company(self, company_id: str, geo_id: str, company: str, max_results: int) -> List[Dict]:
        return self._paginate(max_results, company, f_C=company_id, geoId=geo_id)

    def _scrape_keyword(self, keywords: str, geo_id: str, company: str, max_results: int) -> List[Dict]:
        return self._paginate(max_results, company, keywords=keywords, geoId=geo_id)

    def _paginate(self, max_results: int, company: str, **params) -> List[Dict]:
        jobs: List[Dict] = []
        seen_ids: set = set()
        for start in range(0, max_results, 25):
            cards = self._fetch_cards(start=start, **params)
            if not cards:
                break
            for job in self._parse_cards(cards, company):
                jid = job.get("linkedin_job_id")
                if jid and jid in seen_ids:
                    continue
                if jid:
                    seen_ids.add(jid)
                jobs.append(job)
            _delay()
        return jobs

    def _fetch_cards(self, **params) -> List[Any]:
        try:
            resp = self._session.get(_GUEST_SEARCH, params={**params, "count": 25}, timeout=20)
            if resp.status_code == 429:
                logger.warning("Rate limited (429) on search, sleeping 15s")
                time.sleep(15)
                return []
            if resp.status_code != 200:
                logger.warning(f"Guest search returned HTTP {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            return soup.find_all("div", class_=re.compile(r"base-search-card"))
        except Exception as e:
            logger.error(f"_fetch_cards failed: {e}")
            return []

    def _parse_cards(self, cards: List[Any], company: str) -> List[Dict]:
        jobs: List[Dict] = []
        for card in cards:
            try:
                urn = card.get("data-entity-urn", "")
                m = re.search(r":(\d+)$", urn)
                if not m:
                    continue
                job_id = m.group(1)

                title_el = card.find(class_=re.compile(r"base-search-card__title"))
                company_el = card.find(class_=re.compile(r"base-search-card__subtitle"))
                location_el = card.find(class_=re.compile(r"job-search-card__location"))
                time_el = card.find("time")
                link_el = card.find("a", class_=re.compile(r"base-card__full-link"))

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                company_name = (company_el.get_text(strip=True) if company_el else "") or company
                location = normalize_location(location_el.get_text(strip=True) if location_el else "") or ""
                posted_raw = ""
                is_reposted = False
                if time_el:
                    datetime_attr = time_el.get("datetime", "")
                    time_text = time_el.get_text(strip=True)
                    posted_raw = datetime_attr or time_text
                    is_reposted = _is_repost_text(time_text)

                # Repost text can live outside <time> — scan broader card text
                if not is_reposted:
                    is_reposted = _is_repost_text(card.get_text(" ", strip=True))

                raw_url = ""
                if link_el:
                    raw_url = link_el.get("href", "").split("?")[0]
                if not raw_url:
                    raw_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

                canonical = canonicalize_linkedin_url(raw_url) or raw_url

                jobs.append({
                    "source": "linkedin",
                    "linkedin_job_id": job_id,
                    "job_url": raw_url,
                    "canonical_url": canonical,
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "posted_time": posted_raw,
                    "posted_date_normalized": parse_posted_date(posted_raw),
                    "description": None,
                    "seniority_level": None,
                    "employment_type": None,
                    "department": None,
                    "raw_applicant_text": None,
                    "applicant_count_exact": None,
                    "applicant_count_min": None,
                    "is_reposted": is_reposted,
                    "applicant_count_quality": "unavailable",
                    "canonical_job_key": make_canonical_job_key(
                        job_id, title, company_name, location, posted_raw
                    ),
                })
            except Exception as e:
                logger.warning(f"Card parse error: {e}")
        return jobs

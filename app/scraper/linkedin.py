"""
LinkedIn browser automation scraper using Playwright.
Handles both unauthenticated (search results) and optional authenticated scraping.
"""
import asyncio
import random
import os
from typing import List, Dict, Optional, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout
)

from app.scraper.extractors import collect_job_cards, extract_card_data, extract_detail_data
from app.scraper.normalizer import (
    extract_linkedin_job_id, canonicalize_linkedin_url,
    make_canonical_job_key, parse_posted_date, parse_applicant_count
)


SCRAPER_MIN_DELAY = float(os.getenv("SCRAPER_MIN_DELAY_S", "2.0"))
SCRAPER_MAX_DELAY = float(os.getenv("SCRAPER_MAX_DELAY_S", "5.0"))
SCRAPER_HEADLESS = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT_MS", "30000"))
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


async def _random_delay() -> None:
    delay = random.uniform(SCRAPER_MIN_DELAY, SCRAPER_MAX_DELAY)
    await asyncio.sleep(delay)


async def _build_context(playwright_instance: Any) -> tuple[Browser, BrowserContext]:
    browser = await playwright_instance.chromium.launch(
        headless=SCRAPER_HEADLESS,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="Europe/Berlin",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    # Block images and fonts to speed up scraping
    await context.route(
        "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,otf}",
        lambda route: route.abort()
    )
    return browser, context


async def _handle_linkedin_wall(page: Page) -> bool:
    """
    Detect and dismiss LinkedIn sign-in prompts or modal overlays.
    Returns True if wall was found and handled (content may be partially available),
    False if no wall detected.
    """
    wall_selectors = [
        ".modal__overlay",
        ".contextual-sign-in-modal",
        "button[data-tracking-control-name='guest_homepage-basic_sign-in-modal_dismiss']",
        ".sign-in-modal",
    ]
    for sel in wall_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                # Try to dismiss
                close = await page.query_selector(
                    "button[aria-label='Dismiss'], button[aria-label='Close'], .modal__dismiss"
                )
                if close:
                    await close.click()
                    await asyncio.sleep(0.5)
                logger.debug("LinkedIn modal wall detected and dismissed")
                return True
        except Exception:
            pass
    return False


async def _login_if_configured(page: Page) -> bool:
    """Attempt LinkedIn login if credentials are configured."""
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        return False
    try:
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.fill("#username", LINKEDIN_EMAIL)
        await page.fill("#password", LINKEDIN_PASSWORD)
        await page.click("button[type='submit']")
        await page.wait_for_url("**/feed/**", timeout=10000)
        logger.info("LinkedIn login successful")
        return True
    except Exception as e:
        logger.warning(f"LinkedIn login failed: {e}")
        return False


class LinkedInScraper:
    """Stateless scraper — create new instance per run or reuse within a run."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._authenticated = False

    async def __aenter__(self) -> "LinkedInScraper":
        self._playwright = await async_playwright().start()
        self._browser, self._context = await _build_context(self._playwright)
        page = await self._context.new_page()
        # Attempt login
        self._authenticated = await _login_if_configured(page)
        await page.close()
        return self

    async def __aexit__(self, *_) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def scrape_search_page(
        self,
        url: str,
        company: str = "Xiaomi",
        max_pages: int = 5,
        scroll_count: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Scrape a LinkedIn job search URL.
        Returns a list of raw job dicts.
        """
        jobs: List[Dict[str, Any]] = []
        page = await self._context.new_page()
        page.set_default_timeout(SCRAPER_TIMEOUT)

        try:
            current_url = url
            for page_num in range(max_pages):
                logger.info(f"Scraping page {page_num + 1}: {current_url}")
                try:
                    await page.goto(current_url, wait_until="domcontentloaded")
                    await _random_delay()
                    await _handle_linkedin_wall(page)
                except PWTimeout:
                    logger.warning(f"Timeout loading {current_url}")
                    break

                cards = await collect_job_cards(page, scroll_count=scroll_count)
                logger.info(f"Found {len(cards)} cards on page {page_num + 1}")

                if not cards:
                    break

                for card in cards:
                    try:
                        card_data = await extract_card_data(card)
                        if not card_data.get("raw_job_id") and not card_data.get("job_url"):
                            continue
                        job = self._build_job_dict(card_data, company)
                        jobs.append(job)
                    except Exception as e:
                        logger.warning(f"Card extraction error: {e}")
                        continue

                # Pagination: try to find "next" button
                next_url = await self._find_next_page_url(page, page_num)
                if not next_url:
                    break
                current_url = next_url
                await _random_delay()

        except Exception as e:
            logger.error(f"Search page scrape failed: {e}")
        finally:
            await page.close()

        return jobs

    async def enrich_job_details(
        self,
        job: Dict[str, Any],
        force_reload: bool = False,
    ) -> Dict[str, Any]:
        """
        Navigate to the job detail page and enrich with full description,
        applicant count, and structured criteria.
        """
        url = job.get("canonical_url") or job.get("job_url")
        if not url:
            return job

        page = await self._context.new_page()
        page.set_default_timeout(SCRAPER_TIMEOUT)

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await _random_delay()
            await _handle_linkedin_wall(page)

            # Expand "Show more" in description
            try:
                more_btn = await page.query_selector("button.show-more-less-html__button")
                if more_btn:
                    await more_btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            detail = await extract_detail_data(page)

            # Merge detail data into job dict (detail overrides card-level if richer)
            if detail.get("title") and not job.get("title"):
                job["title"] = detail["title"]
            if detail.get("company") and not job.get("company"):
                job["company"] = detail["company"]
            if detail.get("location") and not job.get("location"):
                job["location"] = detail["location"]
            if detail.get("description"):
                job["description"] = detail["description"]
            if detail.get("seniority"):
                job["seniority_level"] = detail["seniority"]
            if detail.get("employment_type"):
                job["employment_type"] = detail["employment_type"]
            if detail.get("department"):
                job["department"] = detail["department"]
            if detail.get("applicants"):
                parsed = parse_applicant_count(detail["applicants"])
                job["raw_applicant_text"] = parsed["raw"]
                job["applicant_count_exact"] = parsed["exact"]
                job["applicant_count_min"] = parsed["min"]
                job["applicant_count_quality"] = parsed["quality"]
            if detail.get("posted_time") and not job.get("posted_time"):
                job["posted_time"] = detail["posted_time"]

        except Exception as e:
            logger.warning(f"Detail enrichment failed for {url}: {e}")
        finally:
            await page.close()

        return job

    def _build_job_dict(self, card_data: Dict, company: str) -> Dict[str, Any]:
        job_id = card_data.get("raw_job_id")
        raw_url = card_data.get("job_url") or ""
        if raw_url and not raw_url.startswith("http"):
            raw_url = "https://www.linkedin.com" + raw_url

        linkedin_id = job_id or extract_linkedin_job_id(raw_url)
        canonical = canonicalize_linkedin_url(raw_url)
        posted_raw = card_data.get("posted_time")

        return {
            "source": "linkedin",
            "linkedin_job_id": linkedin_id,
            "job_url": raw_url,
            "canonical_url": canonical,
            "title": card_data.get("title"),
            "company": card_data.get("company") or company,
            "location": card_data.get("location"),
            "posted_time": posted_raw,
            "posted_date_normalized": parse_posted_date(posted_raw),
            "description": None,
            "seniority_level": None,
            "employment_type": None,
            "department": None,
            "raw_applicant_text": None,
            "applicant_count_exact": None,
            "applicant_count_min": None,
            "applicant_count_quality": "unavailable",
            "canonical_job_key": make_canonical_job_key(
                linkedin_id,
                card_data.get("title"),
                card_data.get("company") or company,
                card_data.get("location"),
                posted_raw,
            ),
        }

    @staticmethod
    async def _find_next_page_url(page: Page, current_page: int) -> Optional[str]:
        """Try to locate a 'next page' link or paginated URL."""
        try:
            next_btn = await page.query_selector(
                "button[aria-label='Page {n}']".format(n=current_page + 2),
            )
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(1.0)
                return page.url
        except Exception:
            pass

        # URL-based pagination: append &start=N
        current = page.url
        if "start=" not in current:
            return current + f"&start={25 * (current_page + 1)}"
        return re.sub(r"start=\d+", f"start={25 * (current_page + 1)}", current)

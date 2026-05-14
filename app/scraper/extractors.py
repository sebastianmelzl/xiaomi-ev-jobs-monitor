"""
HTML extraction strategies for LinkedIn job pages.
Uses a prioritized selector approach: primary → fallback → heuristic.
All extractors return None on failure rather than raising.
"""
import re
from typing import Optional, List, Dict, Any
from playwright.async_api import Page, ElementHandle


# ── Selector maps ─────────────────────────────────────────────────────────────

SEARCH_CARD_SELECTORS: Dict[str, List[str]] = {
    "container": [
        "ul.jobs-search__results-list > li",
        ".scaffold-layout__list-container ul > li",
        "li[data-occludable-job-id]",
        ".base-card",
    ],
    "job_id_attr": [
        "[data-job-id]",
        "[data-occludable-job-id]",
        "[data-entity-urn]",
    ],
    "job_url": [
        "a.base-card__full-link",
        "a[href*='/jobs/view/']",
        "a.job-search-card__title-link",
    ],
    "title": [
        "h3.base-search-card__title",
        ".job-search-card__title",
        "h3 a",
        "h3",
    ],
    "company": [
        "h4.base-search-card__subtitle a",
        ".job-search-card__subtitle-link",
        "h4.base-search-card__subtitle",
        ".base-search-card__subtitle",
    ],
    "location": [
        "span.job-search-card__location",
        ".job-search-card__location",
        "span[class*='location']",
    ],
    "posted_time": [
        "time.job-search-card__listdate",
        "time.job-search-card__listdate--new",
        "time[datetime]",
    ],
}

DETAIL_SELECTORS: Dict[str, List[str]] = {
    "title": [
        "h1.top-card-layout__title",
        "h1.topcard__title",
        ".job-details-jobs-unified-top-card__job-title h1",
        "h1",
    ],
    "company": [
        "a.topcard__org-name-link",
        ".topcard__org-name-link",
        ".job-details-jobs-unified-top-card__company-name a",
        ".jobs-unified-top-card__company-name a",
        "span.topcard__flavor a",
    ],
    "location": [
        "span.topcard__flavor--bullet",
        ".topcard__flavor:not(.topcard__flavor--secondary)",
        ".job-details-jobs-unified-top-card__bullet",
        ".jobs-unified-top-card__bullet",
    ],
    "description": [
        "div.show-more-less-html__markup",
        ".description__text--rich",
        "#job-details",
        "article.job-view-layout",
    ],
    "seniority": [
        "li.description__job-criteria-item:nth-child(1) span.description__job-criteria-text",
        ".job-criteria-item:nth-child(1) .job-criteria-item__text",
    ],
    "employment_type": [
        "li.description__job-criteria-item:nth-child(2) span.description__job-criteria-text",
        ".job-criteria-item:nth-child(2) .job-criteria-item__text",
    ],
    "department": [
        "li.description__job-criteria-item:nth-child(3) span.description__job-criteria-text",
        ".job-criteria-item:nth-child(3) .job-criteria-item__text",
    ],
    "industry": [
        "li.description__job-criteria-item:nth-child(4) span.description__job-criteria-text",
    ],
    "applicants": [
        "figcaption.num-applicants__caption",
        ".num-applicants__caption",
        ".jobs-unified-top-card__bullet:last-child",
        "span[class*='applicant']",
        ".jobs-unified-top-card__applicant-count",
    ],
    "posted_time": [
        "span.posted-time-ago__text",
        ".jobs-unified-top-card__posted-date",
        "time[datetime]",
    ],
}


# ── Generic extraction helpers ────────────────────────────────────────────────

async def try_selectors(
    parent: Any, selectors: List[str], attribute: Optional[str] = None
) -> Optional[str]:
    """
    Try each selector in order, return first non-empty result.
    If attribute is set, return that attribute value; otherwise inner_text().
    """
    for sel in selectors:
        try:
            el = await parent.query_selector(sel)
            if el is None:
                continue
            if attribute:
                val = await el.get_attribute(attribute)
            else:
                val = await el.inner_text()
            val = (val or "").strip()
            if val:
                return val
        except Exception:
            continue
    return None


async def try_selectors_all(
    parent: Any, selectors: List[str]
) -> List[ElementHandle]:
    for sel in selectors:
        try:
            els = await parent.query_selector_all(sel)
            if els:
                return els
        except Exception:
            continue
    return []


# ── Card-level extraction ─────────────────────────────────────────────────────

async def extract_card_data(card: ElementHandle) -> Dict[str, Optional[str]]:
    """
    Extract all available fields from a LinkedIn job search result card.
    Soft failures: missing fields are None.
    """
    data: Dict[str, Optional[str]] = {
        "raw_job_id": None,
        "job_url": None,
        "title": None,
        "company": None,
        "location": None,
        "posted_time": None,
    }

    # Job ID from attribute
    for attr_name in ["data-job-id", "data-occludable-job-id"]:
        val = await card.get_attribute(attr_name)
        if val:
            data["raw_job_id"] = val.strip()
            break

    # Job URL
    data["job_url"] = await try_selectors(card, SEARCH_CARD_SELECTORS["job_url"], attribute="href")

    # Extract job ID from URL if not found in attribute
    if not data["raw_job_id"] and data["job_url"]:
        m = re.search(r"/jobs/view/(\d+)", data["job_url"])
        if m:
            data["raw_job_id"] = m.group(1)

    # entity urn fallback
    if not data["raw_job_id"]:
        urn = await card.get_attribute("data-entity-urn")
        if urn:
            m = re.search(r":(\d+)$", urn)
            if m:
                data["raw_job_id"] = m.group(1)

    data["title"] = await try_selectors(card, SEARCH_CARD_SELECTORS["title"])
    data["company"] = await try_selectors(card, SEARCH_CARD_SELECTORS["company"])
    data["location"] = await try_selectors(card, SEARCH_CARD_SELECTORS["location"])

    # Posted time: prefer datetime attribute
    time_els = await card.query_selector_all("time")
    for tel in time_els:
        dt = await tel.get_attribute("datetime")
        if dt:
            data["posted_time"] = dt
            break
    if not data["posted_time"]:
        data["posted_time"] = await try_selectors(card, SEARCH_CARD_SELECTORS["posted_time"])

    return data


# ── Detail page extraction ────────────────────────────────────────────────────

async def extract_detail_data(page: Page) -> Dict[str, Optional[str]]:
    """
    Extract full job data from an open LinkedIn job detail page.
    """
    data: Dict[str, Optional[str]] = {
        "title": None,
        "company": None,
        "location": None,
        "description": None,
        "seniority": None,
        "employment_type": None,
        "department": None,
        "applicants": None,
        "posted_time": None,
    }

    data["title"] = await try_selectors(page, DETAIL_SELECTORS["title"])
    data["company"] = await try_selectors(page, DETAIL_SELECTORS["company"])
    data["location"] = await try_selectors(page, DETAIL_SELECTORS["location"])
    data["description"] = await try_selectors(page, DETAIL_SELECTORS["description"])
    data["seniority"] = await try_selectors(page, DETAIL_SELECTORS["seniority"])
    data["employment_type"] = await try_selectors(page, DETAIL_SELECTORS["employment_type"])
    data["department"] = await try_selectors(page, DETAIL_SELECTORS["department"])
    data["applicants"] = await try_selectors(page, DETAIL_SELECTORS["applicants"])

    # Posted time: prefer datetime attribute
    time_els = await page.query_selector_all("time")
    for tel in time_els:
        dt = await tel.get_attribute("datetime")
        if dt:
            data["posted_time"] = dt
            break
    if not data["posted_time"]:
        data["posted_time"] = await try_selectors(page, DETAIL_SELECTORS["posted_time"])

    # Clean description: strip excessive whitespace
    if data["description"]:
        data["description"] = re.sub(r"\n{3,}", "\n\n", data["description"].strip())

    return data


# ── Scroll and collect job cards ──────────────────────────────────────────────

async def collect_job_cards(page: Page, scroll_count: int = 5) -> List[ElementHandle]:
    """
    Scroll the search results page to trigger lazy-loaded job cards,
    then return all visible card elements.
    """
    import asyncio

    # Wait for initial load
    try:
        await page.wait_for_selector(
            "ul.jobs-search__results-list, .scaffold-layout__list-container",
            timeout=15000
        )
    except Exception:
        pass

    for _ in range(scroll_count):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        # Click "Load more" if present
        try:
            btn = await page.query_selector("button.infinite-scroller__show-more-button")
            if btn:
                await btn.click()
                await asyncio.sleep(1.0)
        except Exception:
            pass

    return await try_selectors_all(page, SEARCH_CARD_SELECTORS["container"])

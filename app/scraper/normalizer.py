"""
URL canonicalization, key generation, and data normalization utilities.
All functions are pure — no side effects, deterministic output.
"""
import re
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# ── URL normalization ─────────────────────────────────────────────────────────

_LINKEDIN_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
_ENTITY_URN_RE = re.compile(r"jobPosting:(\d+)")


def extract_linkedin_job_id(url: str) -> Optional[str]:
    """Extract the numeric LinkedIn job ID from a job URL or data-entity-urn."""
    if not url:
        return None
    m = _LINKEDIN_JOB_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _ENTITY_URN_RE.search(url)
    if m:
        return m.group(1)
    return None


def canonicalize_linkedin_url(url: str) -> Optional[str]:
    """
    Normalize a LinkedIn job URL to its canonical form.
    Strips tracking params, normalizes path.
    Returns None if url cannot be parsed.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        if not parsed.netloc:
            return url.strip()
        # Keep only the /jobs/view/{id}/ path
        job_id = extract_linkedin_job_id(url)
        if job_id:
            return f"https://www.linkedin.com/jobs/view/{job_id}/"
        # Generic canonicalization: strip tracking params
        keep_params = {}
        allowed = {"keywords", "location", "f_C", "geoId", "sortBy", "f_TPR"}
        qs = parse_qs(parsed.query, keep_blank_values=False)
        for k, v in qs.items():
            if k in allowed:
                keep_params[k] = v[0]
        clean_query = urlencode(sorted(keep_params.items()))
        canonical = urlunparse((
            "https", "www.linkedin.com",
            parsed.path.rstrip("/") + "/",
            "", clean_query, ""
        ))
        return canonical
    except Exception:
        return url


# ── Canonical job key ─────────────────────────────────────────────────────────

def make_canonical_job_key(
    linkedin_job_id: Optional[str],
    title: Optional[str],
    company: Optional[str],
    location: Optional[str],
    posted_text: Optional[str],
) -> str:
    """
    Generate a stable, unique key for a job.
    Priority: LinkedIn job ID → hash of (title + company + location + posted).
    """
    if linkedin_job_id:
        return f"linkedin:{linkedin_job_id}"
    # Fallback: hash of normalized fields
    parts = [
        _normalize_str(title),
        _normalize_str(company),
        _normalize_str(location),
        _normalize_str(posted_text),
    ]
    combined = "|".join(p for p in parts if p)
    digest = hashlib.sha256(combined.encode()).hexdigest()[:16]
    return f"hash:{digest}"


def _normalize_str(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


# ── Location normalization ────────────────────────────────────────────────────

_LOCATION_OVERRIDES: dict[str, str] = {
    "greater bay area": "Greater Bay Area",
    "hong kong sar": "Hong Kong",
    "hong kong, hong kong sar": "Hong Kong",
    "hong kong s.a.r.": "Hong Kong",
    "macau sar": "Macau",
    "taiwan": "Taiwan",
}

_RE_GREATER = re.compile(r"^Greater\s+", re.IGNORECASE)
_RE_METRO = re.compile(r"\s+Metropolitan\s+Area\s*$", re.IGNORECASE)
_RE_AREA = re.compile(r"\s+Area\s*$", re.IGNORECASE)


def normalize_location(location: Optional[str]) -> Optional[str]:
    """
    Reduce verbose LinkedIn location strings to a clean city name.

    Examples:
      "Greater Munich Metropolitan Area"  → "Munich"
      "Munich, Bavaria, Germany"          → "Munich"
      "Greater London Area"               → "London"
      "Singapore, Singapore"              → "Singapore"
      "Hong Kong SAR"                     → "Hong Kong"
      "Greater Bay Area"                  → "Greater Bay Area"  (kept — ambiguous region)
    """
    if not location:
        return location

    loc = location.strip()
    lower = loc.lower()

    # Manual overrides for ambiguous / special-case strings
    if lower in _LOCATION_OVERRIDES:
        return _LOCATION_OVERRIDES[lower]

    # Strip "Greater " prefix
    loc = _RE_GREATER.sub("", loc)

    # Strip " Metropolitan Area" suffix
    loc = _RE_METRO.sub("", loc).strip()

    # Strip " Area" suffix (only when something remains)
    stripped = _RE_AREA.sub("", loc).strip()
    if stripped:
        loc = stripped

    # Take first segment before comma (e.g. "Munich, Bavaria, Germany" → "Munich")
    if "," in loc:
        loc = loc.split(",")[0].strip()

    return loc or location.strip()


# ── Posted date normalization ─────────────────────────────────────────────────

_RELATIVE_PATTERNS = [
    (re.compile(r"(\d+)\s+hour", re.I), "hours"),
    (re.compile(r"(\d+)\s+day", re.I), "days"),
    (re.compile(r"(\d+)\s+week", re.I), "weeks"),
    (re.compile(r"(\d+)\s+month", re.I), "months"),
    (re.compile(r"just now|moments ago", re.I), "now"),
]


def parse_posted_date(raw_text: Optional[str], reference: Optional[datetime] = None) -> Optional[datetime]:
    """
    Convert LinkedIn's relative posted strings to an approximate datetime.
    Examples: "2 days ago", "3 weeks ago", "1 month ago", "2024-01-15"
    """
    if not raw_text:
        return None
    ref = reference or datetime.utcnow()
    text = raw_text.strip().lower()

    # ISO date
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for pattern, unit in _RELATIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            if unit == "now":
                return ref
            n = int(m.group(1))
            if unit == "hours":
                return ref - timedelta(hours=n)
            if unit == "days":
                return ref - timedelta(days=n)
            if unit == "weeks":
                return ref - timedelta(weeks=n)
            if unit == "months":
                return ref - timedelta(days=n * 30)

    return None


# ── Applicant count parsing ───────────────────────────────────────────────────

_EXACT_RE = re.compile(r"^(\d[\d,]*)$")
_OVER_RE = re.compile(r"(?:over|more than|>)\s*(\d[\d,]*)", re.I)
_RANGE_RE = re.compile(r"(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)")
_STANDALONE_RE = re.compile(r"(\d[\d,]+)")


def parse_applicant_count(raw_text: Optional[str]) -> dict:
    """
    Parse LinkedIn applicant text into structured fields.
    Returns dict with: raw, exact, min, quality.

    Examples:
        "47 applicants"          → exact=47,  min=47,  quality=exact
        "Over 200 applicants"    → exact=None, min=200, quality=lower_bound
        "100-200 applicants"     → exact=None, min=100, quality=lower_bound
        "Be an early applicant"  → exact=None, min=None, quality=unavailable
    """
    result = {
        "raw": raw_text,
        "exact": None,
        "min": None,
        "quality": "unavailable",
    }
    if not raw_text:
        return result

    text = raw_text.strip()

    m = _OVER_RE.search(text)
    if m:
        result["min"] = _parse_int(m.group(1))
        result["quality"] = "lower_bound"
        return result

    m = _RANGE_RE.search(text)
    if m:
        result["min"] = _parse_int(m.group(1))
        result["quality"] = "lower_bound"
        return result

    m = _EXACT_RE.match(text.replace(",", "").split()[0]) if text else None
    if not m:
        m = _STANDALONE_RE.search(text)
    if m:
        val = _parse_int(m.group(1))
        if val is not None:
            result["exact"] = val
            result["min"] = val
            result["quality"] = "exact"
        return result

    return result


# ── Department normalization ──────────────────────────────────────────────────

DEPT_ENGINEERING = "Engineering & R&D"
DEPT_PRODUCT     = "Product & Design"
DEPT_BUSINESS    = "Business & Operations"

# Rules applied to LinkedIn's "Job Function" field.
_DEPT_FIELD_RULES: list[tuple[list[str], str]] = [
    ([
        "engineering", "research", "science", "information technology",
        "quality assurance", "manufacturing", "technical",
    ], DEPT_ENGINEERING),
    ([
        "product management", "product", "design", "art/creative",
        "creative", "strategy", "planning", "user experience",
    ], DEPT_PRODUCT),
    ([
        "sales", "marketing", "business development", "business",
        "operations", "finance", "legal", "human resources",
        "hr", "administrative", "accounting", "consulting",
        "supply chain", "purchasing", "management",
        "customer", "public relations",
    ], DEPT_BUSINESS),
]

# Rules applied to the job title — longer/more-specific phrases first.
_DEPT_TITLE_RULES: list[tuple[list[str], str]] = [
    ([
        # Engineering & R&D title signals
        "r&d", "research", "researcher", "scientist", "engineer", "engineering",
        "developer", "architect", "software", "hardware", "firmware", "embedded",
        "algorithm", "machine learning", "deep learning", "artificial intelligence",
        "computer vision", "autonomous", "autopilot", "lidar", "radar",
        "battery", "powertrain", "electric motor", "thermal management",
        "mechanical", "electrical", "electronic", "simulation", "cfd",
        "quality assurance", "qa", "test engineer", "testing", "validation",
        "data scientist", "data engineer", "devops", "sre", "platform engineer",
        "full stack", "frontend", "backend", "ios", "android", "mobile developer",
        "cloud engineer", "network engineer", "security engineer", "cybersecurity",
        "manufacturing engineer", "process engineer", "industrial engineer",
        "technical lead", "tech lead", "staff engineer", "principal engineer",
    ], DEPT_ENGINEERING),
    ([
        # Product & Design title signals
        "product manager", "product owner", "product lead", "product director",
        "ux", "ui ", "ui/ux", "user experience", "user interface",
        "interaction design", "visual design", "graphic design",
        "brand design", "brand manager", "brand director",
        "creative director", "art director", "motion design",
        "industrial design", "industrial designer",
    ], DEPT_PRODUCT),
    ([
        # Business & Operations title signals
        "sales", "account manager", "account executive", "sales manager",
        "business development", "bd manager", "bd director",
        "marketing manager", "marketing director", "marketing specialist",
        "growth", "demand generation", "campaign manager",
        "finance", "financial", "controller", "accountant", "treasury",
        "legal", "counsel", "compliance", "regulatory",
        "hr ", "human resources", "recruiter", "recruiting", "talent",
        "people partner", "hrbp",
        "operations manager", "operations director", "biz ops",
        "supply chain", "logistics", "procurement", "purchasing",
        "project manager", "program manager",
        "communications", "public relations", "pr manager",
        "strategy", "strategic", "business analyst",
        "customer success", "customer experience", "customer service",
        "content", "copywriter", "social media",
        "general manager", "managing director",
    ], DEPT_BUSINESS),
]


def _match_rules(text: str, rules: list) -> Optional[str]:
    lower = text.strip().lower()
    for keywords, group in rules:
        if any(kw in lower for kw in keywords):
            return group
    return None


def normalize_department(department: Optional[str]) -> Optional[str]:
    """Map LinkedIn job-function string to one of three canonical groups."""
    if not department:
        return None
    return _match_rules(department, _DEPT_FIELD_RULES) or department.strip()


def classify_department(title: Optional[str], department: Optional[str]) -> Optional[str]:
    """
    Determine the canonical department using both the LinkedIn field and the
    job title.  Title takes priority when it produces a confident match,
    otherwise the field result is used.
    """
    field_result = normalize_department(department)
    title_result = _match_rules(title or "", _DEPT_TITLE_RULES)

    # If title gives a clear signal, prefer it
    if title_result:
        return title_result
    # Otherwise fall back to the field result (may be None)
    return field_result


def _parse_int(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None

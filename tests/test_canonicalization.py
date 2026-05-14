"""Tests for URL canonicalization and job key generation."""
import pytest
from app.scraper.normalizer import (
    extract_linkedin_job_id,
    canonicalize_linkedin_url,
    make_canonical_job_key,
)


class TestExtractLinkedInJobId:
    def test_standard_view_url(self):
        url = "https://www.linkedin.com/jobs/view/3987654321/?refId=abc"
        assert extract_linkedin_job_id(url) == "3987654321"

    def test_url_without_trailing_slash(self):
        url = "https://www.linkedin.com/jobs/view/1234567890"
        assert extract_linkedin_job_id(url) == "1234567890"

    def test_entity_urn(self):
        urn = "urn:li:jobPosting:9876543210"
        assert extract_linkedin_job_id(urn) == "9876543210"

    def test_empty_string(self):
        assert extract_linkedin_job_id("") is None

    def test_none(self):
        assert extract_linkedin_job_id(None) is None

    def test_non_job_url(self):
        assert extract_linkedin_job_id("https://www.linkedin.com/in/someprofile") is None


class TestCanonicalizeLinkedInUrl:
    def test_strips_tracking_params(self):
        url = "https://www.linkedin.com/jobs/view/3987654321/?refId=abc&trackingId=xyz&trk=guest"
        result = canonicalize_linkedin_url(url)
        assert result == "https://www.linkedin.com/jobs/view/3987654321/"

    def test_preserves_job_id(self):
        url = "https://www.linkedin.com/jobs/view/111222333/"
        result = canonicalize_linkedin_url(url)
        assert "111222333" in result

    def test_handles_none(self):
        assert canonicalize_linkedin_url(None) is None

    def test_handles_empty(self):
        assert canonicalize_linkedin_url("") is None

    def test_search_url_keeps_params(self):
        url = "https://www.linkedin.com/jobs/search/?keywords=xiaomi&f_C=1090514"
        result = canonicalize_linkedin_url(url)
        assert "keywords=xiaomi" in result
        assert "f_C=1090514" in result


class TestMakeCanonicalJobKey:
    def test_prefers_linkedin_id(self):
        key = make_canonical_job_key("123456", "Engineer", "Xiaomi", "Munich", "2 days ago")
        assert key == "linkedin:123456"

    def test_falls_back_to_hash(self):
        key = make_canonical_job_key(None, "Battery Engineer", "Xiaomi", "Munich", "1 week ago")
        assert key.startswith("hash:")
        assert len(key) > 5

    def test_same_inputs_same_key(self):
        key1 = make_canonical_job_key(None, "EV Engineer", "Xiaomi", "Berlin", "3 days ago")
        key2 = make_canonical_job_key(None, "EV Engineer", "Xiaomi", "Berlin", "3 days ago")
        assert key1 == key2

    def test_different_inputs_different_keys(self):
        key1 = make_canonical_job_key(None, "EV Engineer", "Xiaomi", "Berlin", None)
        key2 = make_canonical_job_key(None, "EV Designer", "Xiaomi", "Berlin", None)
        assert key1 != key2

    def test_case_insensitive(self):
        key1 = make_canonical_job_key(None, "EV ENGINEER", "Xiaomi", "BERLIN", None)
        key2 = make_canonical_job_key(None, "ev engineer", "Xiaomi", "berlin", None)
        assert key1 == key2

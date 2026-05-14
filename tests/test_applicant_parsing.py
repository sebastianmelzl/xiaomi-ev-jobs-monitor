"""Tests for applicant count parsing."""
import pytest
from app.scraper.normalizer import parse_applicant_count


class TestParseApplicantCount:
    def test_exact_integer(self):
        result = parse_applicant_count("47 applicants")
        assert result["exact"] == 47
        assert result["min"] == 47
        assert result["quality"] == "exact"

    def test_exact_with_comma(self):
        result = parse_applicant_count("1,234 applicants")
        assert result["exact"] == 1234
        assert result["quality"] == "exact"

    def test_over_prefix(self):
        result = parse_applicant_count("Over 200 applicants")
        assert result["exact"] is None
        assert result["min"] == 200
        assert result["quality"] == "lower_bound"

    def test_more_than_prefix(self):
        result = parse_applicant_count("more than 100 applicants")
        assert result["min"] == 100
        assert result["quality"] == "lower_bound"

    def test_greater_than_symbol(self):
        result = parse_applicant_count(">500 applicants")
        assert result["min"] == 500
        assert result["quality"] == "lower_bound"

    def test_range(self):
        result = parse_applicant_count("100–200 applicants")
        assert result["min"] == 100
        assert result["quality"] == "lower_bound"

    def test_range_with_hyphen(self):
        result = parse_applicant_count("50-100 applicants")
        assert result["min"] == 50
        assert result["quality"] == "lower_bound"

    def test_no_number(self):
        result = parse_applicant_count("Be an early applicant")
        assert result["exact"] is None
        assert result["min"] is None
        assert result["quality"] == "unavailable"

    def test_none_input(self):
        result = parse_applicant_count(None)
        assert result["exact"] is None
        assert result["min"] is None
        assert result["quality"] == "unavailable"

    def test_empty_string(self):
        result = parse_applicant_count("")
        assert result["quality"] == "unavailable"

    def test_raw_preserved(self):
        raw = "Over 200 applicants"
        result = parse_applicant_count(raw)
        assert result["raw"] == raw

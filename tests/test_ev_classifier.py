"""Tests for EV relevance classifier."""
import pytest
from unittest.mock import patch

# Minimal config for testing — avoids filesystem dependency
MOCK_POSITIVE = {
    "clusters": {
        "vehicle_engineering": {
            "tier": "hard",
            "keywords": ["vehicle dynamics", "chassis", "powertrain", "eAxle"],
        },
        "battery_systems": {
            "tier": "hard",
            "keywords": ["battery", "BMS", "battery management system"],
        },
        "ev_explicit": {
            "tier": "hard",
            "keywords": ["electric vehicle", "EV", "BEV"],
        },
        "automotive_general": {
            "tier": "soft",
            "keywords": ["automotive", "automobile"],
        },
    },
    "location_boost": ["Munich", "München", "Stuttgart"],
}

MOCK_NEGATIVE = {
    "clusters": {
        "consumer_electronics": {
            "penalty": "strong",
            "keywords": ["smartphone", "mobile phone", "handset"],
        },
        "retail": {
            "penalty": "moderate",
            "keywords": ["e-commerce", "online retail"],
        },
    },
    "excluded_title_patterns": [
        r"smartphone.*engineer",
        r"iOS.*engineer",
    ],
}


def make_classifier():
    from app.classifier.ev_classifier import EVClassifier
    with patch("app.classifier.ev_classifier.load_ev_positive_keywords", return_value=MOCK_POSITIVE), \
         patch("app.classifier.ev_classifier.load_ev_negative_keywords", return_value=MOCK_NEGATIVE):
        return EVClassifier()


class TestEVClassifier:
    def test_core_ev_job(self):
        clf = make_classifier()
        job = {
            "title": "Vehicle Dynamics Engineer",
            "department": "EV Engineering",
            "description": "Responsible for chassis development and electric vehicle dynamics",
            "location": "Munich",
        }
        result = clf.classify(job)
        assert result.ev_label.value == "core_ev"
        assert result.ev_score >= 60
        assert len(result.reasoning) > 0

    def test_non_ev_job(self):
        clf = make_classifier()
        job = {
            "title": "Mobile Marketing Manager",
            "department": "Marketing",
            "description": "Manage smartphone e-commerce campaigns and mobile phone promotions",
            "location": "Shanghai",
        }
        result = clf.classify(job)
        assert result.ev_label.value in ("non_ev", "maybe_ev")

    def test_excluded_title_pattern(self):
        clf = make_classifier()
        job = {
            "title": "Smartphone Hardware Engineer",
            "department": "Hardware",
            "description": "Design smartphone circuit boards and battery systems",
            "location": "Beijing",
        }
        result = clf.classify(job)
        assert result.ev_label.value == "non_ev"
        assert result.ev_score == 0
        assert any("Excluded" in r for r in result.reasoning)

    def test_location_boost(self):
        clf = make_classifier()
        job_no_loc = {
            "title": "Automotive Engineer",
            "department": "",
            "description": "automotive development",
            "location": "London",
        }
        job_munich = {**job_no_loc, "location": "Munich"}

        result_no = clf.classify(job_no_loc)
        result_munich = clf.classify(job_munich)
        assert result_munich.ev_score > result_no.ev_score

    def test_battery_keyword_scores(self):
        clf = make_classifier()
        job = {
            "title": "Battery Management Engineer",
            "department": "BMS",
            "description": "BMS and battery system development",
            "location": "Berlin",
        }
        result = clf.classify(job)
        assert result.ev_score > 0
        assert any("battery" in r.lower() or "BMS" in r for r in result.reasoning)

    def test_maybe_ev_mixed_signals(self):
        clf = make_classifier()
        job = {
            "title": "Software Engineer",
            "department": "Automotive Software",
            "description": "automotive embedded software development",
            "location": "Paris",
        }
        result = clf.classify(job)
        # Should score some points for "automotive"
        assert result.ev_score > 0

    def test_classifier_version_set(self):
        clf = make_classifier()
        job = {"title": "Engineer", "department": "", "description": "", "location": ""}
        result = clf.classify(job)
        assert result.classifier_version is not None
        assert len(result.classifier_version) > 0

    def test_score_clamped_to_100(self):
        clf = make_classifier()
        job = {
            "title": "EV vehicle dynamics battery BMS powertrain chassis eAxle",
            "department": "electric vehicle automotive",
            "description": "EV BEV electric vehicle battery BMS chassis powertrain eAxle automotive",
            "location": "Munich",
        }
        result = clf.classify(job)
        assert 0 <= result.ev_score <= 100

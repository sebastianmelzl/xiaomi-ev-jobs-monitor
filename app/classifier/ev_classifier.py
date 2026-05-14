"""
Multi-stage EV relevance classifier for job postings.

Scoring logic:
  - Hard positive keywords:  +25 pts each (cap at 3 hits = 75 pts)
  - Soft positive keywords:  +10 pts each (cap at 2 hits = 20 pts)
  - Context keywords:        +5  pts each (cap at 2 hits = 10 pts)
  - Location boost:          +10 pts if job location matches known automotive hub
  - Strong negative:         -30 pts each
  - Moderate negative:       -15 pts each
  - Weak negative:           -5  pts each
  - Excluded title patterns: forces ev_label = non_ev regardless of score

Label thresholds:
  - core_ev:   score >= 60
  - likely_ev: score >= 35
  - maybe_ev:  score >= 15
  - non_ev:    score < 15

Confidence is score / 100, clamped to [0.0, 1.0].
"""
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from app.config_loader import load_ev_positive_keywords, load_ev_negative_keywords
from app.models import EVLabel

CLASSIFIER_VERSION = "1.1"

TIER_POINTS = {
    "hard": 25,
    "soft": 10,
    "context": 5,
}

TIER_CAPS = {
    "hard": 75,
    "soft": 20,
    "context": 10,
}

PENALTY_POINTS = {
    "strong": 30,
    "moderate": 15,
    "weak": 5,
}

LOCATION_BOOST = 10

LABEL_THRESHOLDS = [
    (60, EVLabel.core_ev),
    (35, EVLabel.likely_ev),
    (15, EVLabel.maybe_ev),
    (0,  EVLabel.non_ev),
]


@dataclass
class ClassificationResult:
    ev_score: int
    ev_confidence: float
    ev_label: EVLabel
    reasoning: List[str] = field(default_factory=list)
    classifier_version: str = CLASSIFIER_VERSION


class EVClassifier:
    def __init__(self) -> None:
        pos_cfg = load_ev_positive_keywords()
        neg_cfg = load_ev_negative_keywords()

        self._pos_clusters: Dict[str, Dict] = pos_cfg.get("clusters", {})
        self._neg_clusters: Dict[str, Dict] = neg_cfg.get("clusters", {})
        self._location_boosts: List[str] = [
            loc.lower() for loc in pos_cfg.get("location_boost", [])
        ]
        self._excluded_title_patterns: List[re.Pattern] = [
            re.compile(p, re.I)
            for p in neg_cfg.get("excluded_title_patterns", [])
        ]

    def classify(self, job: Dict[str, Any]) -> ClassificationResult:
        """
        Classify a job dict for EV relevance.
        Accepts the raw job dict as produced by the scraper.
        """
        title = (job.get("title") or "").lower()
        department = (job.get("department") or "").lower()
        description = (job.get("description") or "").lower()
        location = (job.get("location") or "").lower()

        corpus = f"{title} {department} {description}"
        reasoning: List[str] = []
        score = 0

        # Check excluded title patterns first
        for pattern in self._excluded_title_patterns:
            if pattern.search(title):
                return ClassificationResult(
                    ev_score=0,
                    ev_confidence=0.0,
                    ev_label=EVLabel.non_ev,
                    reasoning=[f"Excluded title pattern: {pattern.pattern}"],
                )

        # Positive scoring
        for cluster_name, cluster in self._pos_clusters.items():
            tier = cluster.get("tier", "context")
            keywords = cluster.get("keywords", [])
            pts_per_hit = TIER_POINTS.get(tier, 5)
            cap = TIER_CAPS.get(tier, 10)
            cluster_pts = 0
            hits = []

            for kw in keywords:
                if kw.lower() in corpus:
                    if cluster_pts < cap:
                        cluster_pts += pts_per_hit
                        hits.append(kw)

            if hits:
                score += cluster_pts
                reasoning.append(
                    f"+{cluster_pts} [{tier}] {cluster_name}: {', '.join(hits[:5])}"
                )

        # Location boost
        for loc in self._location_boosts:
            if loc in location:
                score += LOCATION_BOOST
                reasoning.append(f"+{LOCATION_BOOST} location boost: {loc}")
                break

        # Negative scoring
        for cluster_name, cluster in self._neg_clusters.items():
            penalty_tier = cluster.get("penalty", "weak")
            keywords = cluster.get("keywords", [])
            pts_per_hit = PENALTY_POINTS.get(penalty_tier, 5)
            penalty_total = 0
            hits = []

            for kw in keywords:
                if kw.lower() in corpus:
                    penalty_total += pts_per_hit
                    hits.append(kw)

            if hits:
                score -= penalty_total
                reasoning.append(
                    f"-{penalty_total} [{penalty_tier}] {cluster_name}: {', '.join(hits[:5])}"
                )

        score = max(0, min(100, score))
        confidence = round(score / 100, 3)
        label = self._score_to_label(score)

        return ClassificationResult(
            ev_score=score,
            ev_confidence=confidence,
            ev_label=label,
            reasoning=reasoning,
            classifier_version=CLASSIFIER_VERSION,
        )

    @staticmethod
    def _score_to_label(score: int) -> EVLabel:
        for threshold, label in LABEL_THRESHOLDS:
            if score >= threshold:
                return label
        return EVLabel.non_ev

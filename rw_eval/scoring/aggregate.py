"""Score aggregation and global cap rules."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict

from rw_eval.scoring.common import weighted_average
from rw_eval.utils import round_score

SCORE_DISPLAY_ORDER = [
    "content_coverage",
    "citation_quality",
    "relevance",
    "thematic_structure",
    "synthesis_quality",
    "writing_quality",
    "length_conciseness",
]


def aggregate_scores(metric_results: Dict[str, Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    raw_scores = {name: result["score"] for name, result in metric_results.items()}
    overall = weighted_average(raw_scores, config.get("metric_weights", {}))
    applied_caps = []

    thresholds = config.get("thresholds", {})
    caps = config.get("caps", {}).get("overall", {})
    topic_cov = metric_results.get("thematic_structure", {}).get("details", {}).get("sub_scores", {}).get("topic_coverage", 10.0)
    content_cov = raw_scores.get("content_coverage", 10.0)
    if (
        topic_cov <= float(thresholds.get("topic_mismatch_topic_coverage", 3.0))
        and content_cov <= float(thresholds.get("topic_mismatch_content_coverage", 4.0))
    ):
        cap = float(caps.get("topic_mismatch", overall))
        overall = min(overall, cap)
        applied_caps.append({"rule": "topic_mismatch", "cap": cap})

    ordered_scores = OrderedDict()
    for name in SCORE_DISPLAY_ORDER:
        if name in raw_scores:
            ordered_scores[name] = round_score(raw_scores[name])
    for name, score in raw_scores.items():
        if name not in ordered_scores:
            ordered_scores[name] = round_score(score)

    citation_sub_scores = metric_results.get("citation_quality", {}).get("details", {}).get("sub_scores", {})
    for name in [
        "citation_validity",
        "citation_appropriateness",
        "citation_coverage",
        "citation_placement",
        "citation_topic_consistency",
    ]:
        if name in citation_sub_scores:
            ordered_scores[name] = round_score(citation_sub_scores[name])

    return {
        "overall": round_score(overall),
        "scores": ordered_scores,
        "metric_details": metric_results,
        "applied_caps": applied_caps,
    }

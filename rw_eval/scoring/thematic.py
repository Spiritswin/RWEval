"""Thematic structure scoring."""

from __future__ import annotations

from typing import Any, Dict

from rw_eval.scoring.common import average, metric, weighted_average


def score_thematic_structure(thematic_judgment: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    topic_alignment = thematic_judgment.get("topic_alignment", [])
    paragraph_scores = thematic_judgment.get("paragraph_scores", [])
    sub_scores = {
        "topic_coverage": average([float(x.get("match_score", 0.0) or 0.0) for x in topic_alignment], default=0.0),
        "topic_purity": average([float(x.get("topic_purity", 0.0) or 0.0) for x in paragraph_scores], default=0.0),
        "topic_coherence": average([float(x.get("topic_coherence", 0.0) or 0.0) for x in paragraph_scores], default=0.0),
        "topic_granularity": float(thematic_judgment.get("topic_granularity", {}).get("score", 0.0) or 0.0),
        "topic_ordering": float(thematic_judgment.get("topic_ordering", {}).get("score", 0.0) or 0.0),
    }
    score = weighted_average(sub_scores, config.get("thematic_weights", {}))
    issues = []
    for paragraph in paragraph_scores:
        for issue in paragraph.get("issues", []) or []:
            issues.append({"paragraph_id": paragraph.get("paragraph_id"), "issue": issue})
    return metric(
        "thematic_structure",
        score,
        {
            "sub_scores": sub_scores,
            "topic_alignment": topic_alignment,
            "paragraph_scores": paragraph_scores,
            "issues": issues,
            "granularity": thematic_judgment.get("topic_granularity"),
            "ordering": thematic_judgment.get("topic_ordering"),
        },
    )

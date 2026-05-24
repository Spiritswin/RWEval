"""Content coverage scoring."""

from __future__ import annotations

from typing import Any, Dict

from rw_eval.scoring.common import metric


def score_content_coverage(gold: Dict[str, Any], alignment: Dict[str, Any]) -> Dict[str, Any]:
    points = {p.get("id"): p for p in gold.get("key_points", [])}
    alignments = alignment.get("alignments", [])
    total_weight = 0.0
    matched_weight = 0.0
    missing = []
    partial = []
    incorrect = []

    for item in alignments:
        point_id = item.get("gold_point_id")
        point = points.get(point_id, {})
        importance = float(point.get("importance", 1) or 1)
        match_score = float(item.get("match_score", 0.0) or 0.0)
        status = item.get("status", "")
        total_weight += importance
        matched_weight += importance * max(0.0, min(1.0, match_score))
        if status == "missing" or match_score <= 0:
            missing.append({"gold_point_id": point_id, "text": point.get("text"), "rationale": item.get("rationale")})
        elif status == "partial" or match_score < 1:
            partial.append({"gold_point_id": point_id, "text": point.get("text"), "rationale": item.get("rationale")})
        if status == "incorrect":
            incorrect.append({"gold_point_id": point_id, "text": point.get("text"), "rationale": item.get("rationale")})

    if not alignments:
        for point_id, point in points.items():
            total_weight += float(point.get("importance", 1) or 1)
            missing.append({"gold_point_id": point_id, "text": point.get("text"), "rationale": "No alignment produced."})

    score = 10.0 * matched_weight / total_weight if total_weight else 0.0
    return metric(
        "content_coverage",
        score,
        {
            "matched_weight": matched_weight,
            "total_weight": total_weight,
            "missing_points": missing,
            "partial_points": partial,
            "incorrect_points": incorrect,
        },
    )

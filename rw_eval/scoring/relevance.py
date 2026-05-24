"""Relevance scoring."""

from __future__ import annotations

from typing import Any, Dict

from rw_eval.scoring.common import average, metric


def score_relevance(claim_judgment: Dict[str, Any]) -> Dict[str, Any]:
    judgments = claim_judgment.get("claim_judgments", [])
    scores = [float(j.get("relevance_score", 0.0) or 0.0) * 10.0 for j in judgments]
    irrelevant = [j for j in judgments if float(j.get("relevance_score", 0.0) or 0.0) <= 0.0]
    weak = [j for j in judgments if 0.0 < float(j.get("relevance_score", 0.0) or 0.0) < 1.0]
    return metric(
        "relevance",
        average(scores, default=0.0),
        {"irrelevant_claims": irrelevant, "weakly_relevant_claims": weak, "claim_count": len(judgments)},
    )

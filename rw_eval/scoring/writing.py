"""Writing quality scoring."""

from __future__ import annotations

from typing import Any, Dict

from rw_eval.scoring.common import metric


def score_writing(judgment: Dict[str, Any]) -> Dict[str, Any]:
    item = judgment.get("writing_quality", {})
    return metric(
        "writing_quality",
        float(item.get("score", 0.0) or 0.0),
        {"rationale": item.get("rationale", ""), "issues": item.get("issues", [])},
    )

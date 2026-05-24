"""Shared scoring helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from rw_eval.utils import clamp, round_score


def average(values: Iterable[float], default: float = 0.0) -> float:
    vals = [float(v) for v in values]
    if not vals:
        return default
    return sum(vals) / len(vals)


def metric(name: str, score: float, details: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": name, "score": round_score(score), "details": details}


def weighted_average(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    total = sum(float(w) for w in weights.values())
    if total <= 0:
        return 0.0
    value = 0.0
    for key, weight in weights.items():
        value += clamp(float(scores.get(key, 0.0))) * float(weight)
    return value / total

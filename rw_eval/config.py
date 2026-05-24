"""Rubric configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG_PATH = "configs/rubric.json"


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def weighted_sum(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    total_weight = sum(float(v) for v in weights.values())
    if total_weight <= 0:
        return 0.0
    value = 0.0
    for key, weight in weights.items():
        value += float(scores.get(key, 0.0)) * float(weight)
    return value / total_weight

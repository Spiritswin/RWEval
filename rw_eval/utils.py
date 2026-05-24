"""General helpers."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List


WORD_RE = re.compile(r"[A-Za-z0-9]+")


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, float(value)))


def round_score(value: float) -> float:
    return round(clamp(value), 2)


def normalize_text(text: str) -> str:
    return " ".join(WORD_RE.findall((text or "").lower()))


def token_set(text: str) -> set:
    return set(normalize_text(text).split())


def jaccard(a: str, b: str) -> float:
    a_set = token_set(a)
    b_set = token_set(b)
    if not a_set and not b_set:
        return 1.0
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


def text_similarity(a: str, b: str) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    return max(jaccard(a_norm, b_norm), SequenceMatcher(None, a_norm, b_norm).ratio())


def first_json_object(text: str) -> Dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError("No JSON object found in LLM response")


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def safe_get(d: Dict[str, Any], path: Iterable[str], default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

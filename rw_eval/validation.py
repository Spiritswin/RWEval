"""Input validation for evaluation samples."""

from __future__ import annotations

from typing import Any, Dict, List


REQUIRED_TEXT_FIELDS = ["s_text", "g_text"]
REFERENCE_FIELDS = ["s_references", "g_references"]


def validate_sample(sample: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for field in REQUIRED_TEXT_FIELDS:
        value = sample.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{field} is required and must be a non-empty string")
    for field in REFERENCE_FIELDS:
        value = sample.get(field)
        if value is None:
            issues.append(f"{field} is missing; use an empty string if no references are available")
        elif not isinstance(value, str):
            issues.append(f"{field} must be a string")
    if "sample_id" in sample and not isinstance(sample.get("sample_id"), str):
        issues.append("sample_id must be a string when provided")
    return issues

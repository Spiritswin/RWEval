"""Conservative text cleaning before evaluation.

The replacement table intentionally uses Unicode escapes so the source file
stays ASCII-safe across Windows consoles and editors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class CleaningReport:
    field: str
    changed: bool
    replacements: Dict[str, int] = field(default_factory=dict)
    original_length: int = 0
    cleaned_length: int = 0


ENCODING_REPLACEMENTS = {
    "\u0101\u20ac\u201dh": "-h",
    "\u0101\u20ac\u201dw": "-w",
    "\u0101\u20ac\u201dt": "-t",
    "\u0101\u20ac\u201da": "-a",
    "\u0101\u20ac\u2122s": "'s",
    "\u0101\u20ac": "'",
    "\u0106\u2014": "x",
}

TYPO_LITERAL_REPLACEMENTS = {
    "A14Science": "AI4Science",
}

TYPO_REGEX_REPLACEMENTS = {
    r"\bAl(?=\b|['-])": "AI",
}

LATEX_REPLACEMENTS = {
    "\\&": "&",
    "\\%": "%",
    "\\_": "_",
}


def clean_sample(
    sample: Dict[str, Any],
    enabled: bool = True,
    normalize_ai_typos: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not enabled:
        return dict(sample), []
    cleaned = dict(sample)
    reports: List[Dict[str, Any]] = []
    for field in ["s_text", "s_references", "g_text", "g_references"]:
        value = cleaned.get(field)
        if isinstance(value, str):
            new_value, report = clean_text(value, field, normalize_ai_typos=normalize_ai_typos)
            cleaned[field] = new_value
            reports.append(_report_to_dict(report))
    return cleaned, reports


def clean_text(
    text: str,
    field: str = "text",
    normalize_ai_typos: bool = False,
) -> Tuple[str, CleaningReport]:
    original = text or ""
    cleaned = original
    report = CleaningReport(field=field, changed=False, original_length=len(original))

    for bad, good in ENCODING_REPLACEMENTS.items():
        count = cleaned.count(bad)
        if count:
            cleaned = cleaned.replace(bad, good)
            report.replacements[bad] = report.replacements.get(bad, 0) + count

    if normalize_ai_typos:
        for bad, good in TYPO_LITERAL_REPLACEMENTS.items():
            count = cleaned.count(bad)
            if count:
                cleaned = cleaned.replace(bad, good)
                report.replacements[bad] = report.replacements.get(bad, 0) + count

        for pattern, replacement in TYPO_REGEX_REPLACEMENTS.items():
            cleaned, count = re.subn(pattern, replacement, cleaned)
            if count:
                report.replacements[pattern] = report.replacements.get(pattern, 0) + count

    for bad, good in LATEX_REPLACEMENTS.items():
        count = cleaned.count(bad)
        if count:
            cleaned = cleaned.replace(bad, good)
            report.replacements[bad] = report.replacements.get(bad, 0) + count

    cleaned = _normalize_whitespace(cleaned)
    report.cleaned_length = len(cleaned)
    report.changed = cleaned != original
    return cleaned, report


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _report_to_dict(report: CleaningReport) -> Dict[str, Any]:
    return {
        "field": report.field,
        "changed": report.changed,
        "replacements": report.replacements,
        "original_length": report.original_length,
        "cleaned_length": report.cleaned_length,
    }

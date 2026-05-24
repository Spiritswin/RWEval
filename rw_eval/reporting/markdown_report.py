"""Markdown report rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def render_markdown_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Related Work Evaluation: {report.get('sample_id', 'unknown')}")
    lines.append("")
    lines.append(f"Overall: {report.get('overall', 0.0):.2f}/10")
    lines.append("")
    lines.append("## Metric Breakdown")
    for name, score in report.get("scores", {}).items():
        lines.append(f"- {name}: {score:.2f}/10")
    lines.append("")

    cleaning = [item for item in report.get("cleaning", []) if item.get("changed")]
    lines.append("## Input Cleaning")
    if not cleaning:
        lines.append("- No changes")
    else:
        for item in cleaning:
            lines.append(
                f"- {item.get('field')}: replacements={item.get('replacements', {})}, "
                f"length {item.get('original_length')} -> {item.get('cleaned_length')}"
            )
    lines.append("")

    diagnostics = report.get("diagnostics", {})
    sections = [
        ("Missing Points", diagnostics.get("missing_points", [])),
        ("Hallucinated References", diagnostics.get("hallucinated_references", [])),
        ("Bad Citation-Claim Pairs", diagnostics.get("bad_citation_claim_pairs", [])),
        ("Overclaim Citation-Claim Pairs", diagnostics.get("overclaim_citation_claim_pairs", [])),
        ("Citation Group Support", diagnostics.get("citation_group_support", [])),
        ("Topic Structure Issues", diagnostics.get("topic_structure_issues", [])),
        ("Length / Conciseness Issues", diagnostics.get("length_conciseness_issues", [])),
    ]
    for title, items in sections:
        lines.append(f"## {title}")
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(f"- {_format_item(item)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report: Dict[str, Any], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_report(report), encoding="utf-8")


def _format_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    if "text" in item:
        suffix = f" ({item.get('rationale')})" if item.get("rationale") else ""
        return f"{item.get('text')}{suffix}"
    if "claim_id" in item and "reference_key" in item:
        support = item.get("support", "unknown")
        overclaim = item.get("overclaim_status", "none")
        label = f"support={support}, overclaim={overclaim}" if overclaim != "none" else f"support={support}"
        reasons = []
        support_rationale = item.get("support_rationale") or item.get("rationale")
        if support_rationale:
            reasons.append(f"support_reason={support_rationale}")
        if overclaim != "none" and item.get("overclaim_rationale"):
            reasons.append(f"overclaim_reason={item.get('overclaim_rationale')}")
        suffix = f": {'; '.join(reasons)}" if reasons else ""
        return f"{item.get('claim_id')} -> {item.get('reference_key')} [{label}]{suffix}"
    if "claim_id" in item and "group_support" in item:
        parts = [f"group_support={item.get('group_support', 'unknown')}"]
        if item.get("citation_count") is not None:
            parts.append(f"citation_count={item.get('citation_count')}")
        if item.get("derived_from_single_pair"):
            parts.append("mode=single-pair")
        details = []
        rationale = item.get("group_rationale") or ""
        if rationale:
            details.append(f"reason={rationale}")
        covered = item.get("covered_aspects") or []
        missing = item.get("missing_aspects") or []
        if covered:
            details.append(f"covered={covered}")
        if missing:
            details.append(f"missing={missing}")
        suffix = f": {'; '.join(details)}" if details else ""
        return f"{item.get('claim_id')} [{', '.join(parts)}]{suffix}"
    if "title" in item:
        return f"{item.get('title')} [{item.get('validity', 'unknown')}]"
    if item.get("type") == "relative_length":
        return (
            f"Relative length ratio={item.get('length_ratio'):.2f} "
            f"(s={item.get('s_word_count')} words, g={item.get('g_word_count')} words)"
        )
    if item.get("type") == "duplicate_sentence":
        return f"Duplicate-like sentences {item.get('sentence_a')} and {item.get('sentence_b')} similarity={item.get('similarity'):.2f}"
    if item.get("type") == "duplicate_paragraph":
        return f"Duplicate-like paragraphs {item.get('paragraph_a')} and {item.get('paragraph_b')} similarity={item.get('similarity'):.2f}"
    return ", ".join(f"{k}={v}" for k, v in item.items())

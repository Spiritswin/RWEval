"""Citation quality scoring."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from rw_eval.scoring.common import average, metric, weighted_average
from rw_eval.schemas import ReferenceEntry


def score_citation_quality(
    s_references: List[ReferenceEntry],
    g_references: List[ReferenceEntry],
    gold: Dict[str, Any],
    citation_judgment: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    validity_score, validity_details = _score_validity(s_references)
    citation_judgments = citation_judgment.get("citation_judgments", [])
    appropriateness = average([float(j.get("appropriateness_score", 0.0) or 0.0) for j in citation_judgments], default=5.0)
    placement = average([float(j.get("placement_score", 0.0) or 0.0) for j in citation_judgments], default=5.0)
    topic_consistency = average([float(j.get("topic_consistency_score", 0.0) or 0.0) for j in citation_judgments], default=5.0)
    coverage_score, coverage_details = _score_citation_coverage(s_references, g_references, gold)

    sub_scores = {
        "citation_validity": validity_score,
        "citation_appropriateness": appropriateness,
        "citation_coverage": coverage_score,
        "citation_placement": placement,
        "citation_topic_consistency": topic_consistency,
    }
    score = weighted_average(sub_scores, config.get("citation_weights", {}))

    hallucinated_count = validity_details["hallucinated_reference_count"]
    unresolved_count = validity_details["unresolved_reference_count"]
    caps = config.get("caps", {}).get("citation_quality", {})
    thresholds = config.get("thresholds", {})
    applied_caps = []
    if hallucinated_count >= int(thresholds.get("many_hallucinated_references", 3)):
        cap = float(caps.get("hallucinated_reference_count_many", score))
        score = min(score, cap)
        applied_caps.append({"rule": "hallucinated_reference_count_many", "cap": cap})
    elif hallucinated_count > 0:
        cap = float(caps.get("hallucinated_reference_count_any", score))
        score = min(score, cap)
        applied_caps.append({"rule": "hallucinated_reference_count_any", "cap": cap})
    elif unresolved_count > 0:
        cap = float(caps.get("unresolved_reference_count_any", score))
        score = min(score, cap)
        applied_caps.append({"rule": "unresolved_reference_count_any", "cap": cap})

    problematic_pairs = [
        j
        for j in citation_judgments
        if str(j.get("support", "")).lower() in {"no", "weak", "unknown"}
        or float(j.get("appropriateness_score", 10.0) or 10.0) < 6.0
    ]
    citation_group_judgments = citation_judgment.get("citation_group_judgments", [])
    overclaim_pairs = [
        j
        for j in citation_judgments
        if str(j.get("support", "")).lower() in {"yes", "partial"}
        and str(j.get("overclaim_status", "none")).lower() in {"mild", "moderate", "severe"}
    ]
    return metric(
        "citation_quality",
        score,
        {
            "sub_scores": sub_scores,
            "validity": validity_details,
            "coverage": coverage_details,
            "problematic_citation_claim_pairs": problematic_pairs,
            "overclaim_citation_claim_pairs": overclaim_pairs,
            "citation_group_judgments": citation_group_judgments,
            "citation_judgments": citation_judgments,
            "applied_caps": applied_caps,
        },
    )


def _score_validity(references: List[ReferenceEntry]) -> Any:
    if not references:
        return 0.0, {
            "reference_count": 0,
            "valid_count": 0,
            "unknown_count": 0,
            "unresolved_reference_count": 0,
            "hallucinated_reference_count": 0,
            "references": [],
        }
    valid = 0
    unknown = 0
    unresolved = 0
    hallucinated = 0
    refs = []
    for ref in references:
        if ref.validity == "valid":
            valid += 1
        elif ref.validity == "unknown":
            unknown += 1
        elif ref.validity == "metadata_mismatch":
            hallucinated += 1
        elif ref.validity == "unresolved":
            unresolved += 1
        refs.append(
            {
                "ref_id": ref.ref_id,
                "normalized_key": ref.normalized_key,
                "title": ref.title,
                "validity": ref.validity,
                "match_score": ref.match_score,
                "issues": ref.issues,
            }
        )
    score = 10.0 * (valid + 0.5 * unknown + 0.25 * unresolved) / len(references)
    return score, {
        "reference_count": len(references),
        "valid_count": valid,
        "unknown_count": unknown,
        "unresolved_reference_count": unresolved,
        "hallucinated_reference_count": hallucinated,
        "references": refs,
    }


def _score_citation_coverage(s_references: List[ReferenceEntry], g_references: List[ReferenceEntry], gold: Dict[str, Any]) -> Any:
    s_keys = _reference_key_set(s_references)
    g_lookup = {key: ref for ref in g_references for key in _single_ref_keys(ref)}
    key_refs = gold.get("key_references") or []
    if not key_refs and g_references:
        key_refs = [
            {"reference_key": ref.normalized_key or ref.author_year_key or ref.ref_id, "importance": 1, "reason": "Ground-truth reference."}
            for ref in g_references
        ]
    total_weight = 0.0
    matched_weight = 0.0
    missing = []
    for key_ref in key_refs:
        key = key_ref.get("reference_key")
        importance = float(key_ref.get("importance", 1) or 1)
        total_weight += importance
        equivalent_keys = set([key])
        if key in g_lookup:
            equivalent_keys |= _single_ref_keys(g_lookup[key])
        if equivalent_keys & s_keys:
            matched_weight += importance
        else:
            missing.append(key_ref)
    score = 10.0 * matched_weight / total_weight if total_weight else 10.0
    return score, {"matched_weight": matched_weight, "total_weight": total_weight, "missing_key_references": missing}


def _reference_key_set(references: List[ReferenceEntry]) -> Set[str]:
    keys: Set[str] = set()
    for ref in references:
        keys |= _single_ref_keys(ref)
    return keys


def _single_ref_keys(ref: ReferenceEntry) -> Set[str]:
    return {
        key
        for key in [
            ref.ref_id,
            ref.label,
            ref.normalized_key,
            ref.author_year_key,
            f"s2:{ref.s2_paper_id}" if ref.s2_paper_id else None,
            f"doi:{ref.doi.lower()}" if ref.doi else None,
            f"arxiv:{ref.arxiv_id.lower()}" if ref.arxiv_id else None,
        ]
        if key
    }

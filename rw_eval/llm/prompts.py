"""Prompt templates for extraction and local judging."""

from __future__ import annotations

import json
from typing import Any, Dict


SYSTEM_JSON = (
    "You are a meticulous evaluator for academic related work sections. "
    "Return only valid JSON. Do not include markdown fences."
)


def gold_extraction_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Extract a gold evaluation checklist from the ground-truth related work.\n"
        "Keep points atomic and evaluation-oriented. Importance must be 1, 2, or 3.\n"
        "Use reference keys exactly as provided when possible.\n\n"
        "Return schema:\n"
        "{\n"
        '  "topics": [{"id": "GTopic1", "label": "...", "summary": "...", '
        '"paragraph_ids": ["G1"], "importance": 1, "key_citations": ["..."]}],\n'
        '  "key_points": [{"id": "GPoint1", "type": "topic|method|comparison|limitation|gap|citation", '
        '"text": "...", "importance": 1, "topic_id": "GTopic1", "citations": ["..."]}],\n'
        '  "key_references": [{"reference_key": "...", "importance": 1, "reason": "..."}]\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def candidate_extraction_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Extract candidate topics and atomic claims from the candidate related work.\n"
        "Each claim should be short, factual when possible, and linked to nearby citations.\n"
        "Use reference keys exactly as provided when possible.\n\n"
        "Return schema:\n"
        "{\n"
        '  "topics": [{"id": "STopic1", "label": "...", "summary": "...", '
        '"paragraph_ids": ["S1"], "key_citations": ["..."]}],\n'
        '  "claims": [{"id": "SClaim1", "paragraph_id": "S1", "text": "...", '
        '"is_factual": true, "citations": ["..."]}]\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def alignment_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Judge whether candidate claims cover each gold key point.\n"
        "Use match_score 1.0 for complete coverage, 0.5 for partial coverage, "
        "0.0 for missing, and 0.0 with status incorrect if the candidate covers it incorrectly.\n\n"
        "Return schema:\n"
        "{\n"
        '  "alignments": [{"gold_point_id": "GPoint1", "best_claim_ids": ["SClaim1"], '
        '"match_score": 1.0, "status": "complete|partial|missing|incorrect", "rationale": "..."}]\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def claim_judgment_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Judge candidate claim relevance relative to the ground-truth related work.\n"
        "Use claim text and its nearby citation metadata only as local context for understanding the claim.\n"
        "relevance_score must be 1.0, 0.5, or 0.0.\n\n"
        "Return schema:\n"
        "{\n"
        '  "claim_judgments": [{"claim_id": "SClaim1", "relevance_score": 1.0, "rationale": "..."}]\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def thematic_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Evaluate paragraph/topic organization of the candidate related work.\n"
        "Do not require identical paragraph counts or identical topic order. Use soft alignment.\n"
        "Scores must be 0-10.\n\n"
        "Return schema:\n"
        "{\n"
        '  "topic_alignment": [{"g_topic_id": "GTopic1", "s_topic_ids": ["STopic1"], '
        '"match_score": 0.0, "rationale": "..."}],\n'
        '  "paragraph_scores": [{"paragraph_id": "S1", "topic_purity": 0.0, '
        '"topic_coherence": 0.0, "citation_topic_consistency": 0.0, "issues": ["..."]}],\n'
        '  "topic_granularity": {"score": 0.0, "rationale": "..."},\n'
        '  "topic_ordering": {"score": 0.0, "rationale": "..."}\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def synthesis_writing_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Evaluate synthesis quality and writing quality of the candidate related work. Scores must be 0-10.\n"
        "Synthesis: landscape building, method comparison, limitations, gap motivation, not just paper listing.\n"
        "Writing: academic tone, clarity, conciseness, terminology consistency, sentence flow.\n\n"
        "Return schema:\n"
        "{\n"
        '  "synthesis_quality": {"score": 0.0, "rationale": "...", "issues": ["..."]},\n'
        '  "writing_quality": {"score": 0.0, "rationale": "...", "issues": ["..."]}\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def citation_appropriateness_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Judge whether each cited paper supports the specific candidate claim near the citation.\n"
        "Use paper title/abstract/metadata as evidence. If metadata is missing, use unknown and conservative scores.\n"
        "You must return one citation judgment for every (claim_id, reference_key) pair present in the input.\n"
        "Only assign overclaim_status when support is yes or partial. For weak, no, or unknown support, use none.\n"
        "Explain both the support judgment and, when applicable, the overclaim judgment.\n"
        "Scores must be 0-10.\n\n"
        "Return schema:\n"
        "{\n"
        '  "citation_judgments": [{"claim_id": "SClaim1", "reference_key": "...", '
        '"support": "yes|partial|weak|no|unknown", "appropriateness_score": 0.0, '
        '"placement_score": 0.0, "topic_consistency_score": 0.0, '
        '"support_rationale": "...", "overclaim_status": "none|mild|moderate|severe", '
        '"overclaim_rationale": "..."}]\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def citation_pair_recheck_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Re-evaluate one claim-citation pair using both citation metadata and any retrieved evidence snippets.\n"
        "Treat retrieved evidence as higher-priority support when it is specific and attributable to the cited paper.\n"
        "If the available evidence is still insufficient, use weak or unknown rather than overcommitting.\n"
        "Only assign overclaim_status when support is yes or partial. For weak, no, or unknown support, use none.\n"
        "Scores must be 0-10.\n\n"
        "Return schema:\n"
        "{\n"
        '  "citation_judgment": {"claim_id": "SClaim1", "reference_key": "...", '
        '"support": "yes|partial|weak|no|unknown", "appropriateness_score": 0.0, '
        '"placement_score": 0.0, "topic_consistency_score": 0.0, '
        '"support_rationale": "...", "overclaim_status": "none|mild|moderate|severe", '
        '"overclaim_rationale": "..."}\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def citation_group_support_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Judge whether the full set of citations attached to one claim collectively supports that claim.\n"
        "Consider all provided citation evidence together. A claim may be partially supported if some components are covered while key components remain unsupported.\n"
        "If there is only one citation, the group judgment should be consistent with the single citation pair judgment.\n"
        "Use missing_aspects to name the specific unsupported parts of the claim. Use covered_aspects for parts that are supported by at least one citation.\n"
        "Return only one judgment for the claim.\n\n"
        "Return schema:\n"
        "{\n"
        '  "citation_group_judgment": {"claim_id": "SClaim1", "citation_count": 1, '
        '"group_support": "yes|partial|weak|no|unknown", "group_rationale": "...", '
        '"covered_aspects": ["..."], "missing_aspects": ["..."]}\n'
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

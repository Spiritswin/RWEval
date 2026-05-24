"""End-to-end related work evaluation pipeline."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from rw_eval.cleaning import clean_sample
from rw_eval.config import load_config
from rw_eval.env import env_int, load_dotenv
from rw_eval.external.cache import JsonCache
from rw_eval.external.semantic_scholar import SemanticScholarClient
from rw_eval.llm.client import LLMClient
from rw_eval.llm.extraction import Extractor
from rw_eval.llm.judging import Judger
from rw_eval.parsing.citations import extract_citation_mentions
from rw_eval.parsing.references import build_reference_lookup, parse_references
from rw_eval.parsing.text import split_paragraphs, split_sentences
from rw_eval.schemas import ParsedDocument, ReferenceEntry, to_plain
from rw_eval.scoring.aggregate import aggregate_scores
from rw_eval.scoring.citation import score_citation_quality
from rw_eval.scoring.coverage import score_content_coverage
from rw_eval.scoring.length import score_length_conciseness
from rw_eval.scoring.relevance import score_relevance
from rw_eval.scoring.synthesis import score_synthesis
from rw_eval.scoring.thematic import score_thematic_structure
from rw_eval.scoring.writing import score_writing
from rw_eval.validation import validate_sample

def evaluate_sample(
    sample: Dict[str, Any],
    config_path: str = "configs/rubric.json",
    env_path: str = ".env",
    use_semantic_scholar: bool = True,
    use_llm: bool = True,
    strict_llm: bool = False,
    clean_input: bool = True,
    normalize_ai_typos: bool = False,
) -> Dict[str, Any]:
    load_dotenv(env_path)
    config = load_config(config_path)
    if not use_llm:
        raise ValueError("LLM-backed extraction and judging are required; heuristic mode has been removed.")
    sample, cleaning_reports = clean_sample(sample, enabled=clean_input, normalize_ai_typos=normalize_ai_typos)
    validation_issues = validate_sample(sample)
    if validation_issues:
        raise ValueError("Invalid evaluation sample: " + "; ".join(validation_issues))

    cache = JsonCache(os.environ.get("RW_EVAL_CACHE_DIR", ".cache/rw_eval"))
    llm = LLMClient()
    semantic_scholar = SemanticScholarClient(
        timeout_seconds=env_int("SEMANTIC_SCHOLAR_TIMEOUT_SECONDS", 30),
        cache=cache,
        fields=config.get("semantic_scholar", {}).get("fields", ""),
    )

    s_doc = parse_document(sample.get("s_text", ""), sample.get("s_references", ""), prefix="S")
    g_doc = parse_document(sample.get("g_text", ""), sample.get("g_references", ""), prefix="G")

    if use_semantic_scholar:
        s_doc.references = semantic_scholar.normalize_references(s_doc.references)
        g_doc.references = semantic_scholar.normalize_references(g_doc.references)
    else:
        s_doc.references = _mark_references_unknown(s_doc.references, "semantic_scholar_disabled")
        g_doc.references = _mark_references_unknown(g_doc.references, "semantic_scholar_disabled")

    extractor = Extractor(llm, strict=strict_llm)
    judger = Judger(llm, strict=strict_llm)

    gold = extractor.extract_gold(g_doc)
    candidate = extractor.extract_candidate(s_doc)
    candidate = _resolve_candidate_citation_keys(candidate, s_doc.references)
    gold = _resolve_gold_citation_keys(gold, g_doc.references)

    reference_metadata = _reference_metadata(s_doc.references + g_doc.references)
    alignment = judger.judge_alignment(gold, candidate)
    claim_judgment = judger.judge_claims(gold, candidate, reference_metadata)
    thematic_judgment = judger.judge_thematic(gold, candidate)
    synthesis_writing_judgment = judger.judge_synthesis_writing(sample.get("s_text", ""), gold, candidate)
    citation_judgment = judger.judge_citation_appropriateness(
        candidate,
        reference_metadata,
        reference_lookup=build_reference_lookup(s_doc.references),
        evidence_retriever=semantic_scholar if use_semantic_scholar else None,
    )

    content_coverage_result = score_content_coverage(gold, alignment)
    relevance_result = score_relevance(claim_judgment)
    metric_results = {
        "content_coverage": content_coverage_result,
        "citation_quality": score_citation_quality(s_doc.references, g_doc.references, gold, citation_judgment, config),
        "relevance": relevance_result,
        "thematic_structure": score_thematic_structure(thematic_judgment, config),
        "synthesis_quality": score_synthesis(synthesis_writing_judgment),
        "writing_quality": score_writing(synthesis_writing_judgment),
        "length_conciseness": score_length_conciseness(
            s_doc,
            g_doc,
            content_coverage_result["score"],
            relevance_result["score"],
            config,
        ),
    }
    aggregate = aggregate_scores(metric_results, config)

    report = {
        "sample_id": sample.get("sample_id"),
        "overall": aggregate["overall"],
        "scores": aggregate["scores"],
        "diagnostics": _diagnostics(metric_results, claim_judgment),
        "cleaning": cleaning_reports,
        "intermediate": {
            "parsed_candidate": to_plain(s_doc),
            "parsed_ground_truth": to_plain(g_doc),
            "gold": gold,
            "candidate": candidate,
            "alignment": alignment,
            "claim_judgment": claim_judgment,
            "thematic_judgment": thematic_judgment,
            "synthesis_writing_judgment": synthesis_writing_judgment,
            "citation_judgment": citation_judgment,
        },
        "metric_details": aggregate["metric_details"],
        "applied_caps": aggregate["applied_caps"],
        "warnings": extractor.warnings + judger.warnings,
        "mode": {
            "llm_configured": llm.is_configured() and use_llm,
            "semantic_scholar_api_key_present": bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY")) and use_semantic_scholar,
        },
    }
    return report


def parse_document(text: str, references_text: str, prefix: str) -> ParsedDocument:
    paragraphs = split_paragraphs(text, prefix=prefix)
    sentences = split_sentences(paragraphs)
    citations = extract_citation_mentions(sentences)
    references = parse_references(references_text)
    return ParsedDocument(
        text=text or "",
        references_text=references_text or "",
        paragraphs=paragraphs,
        sentences=sentences,
        citation_mentions=citations,
        references=references,
    )


def _mark_references_unknown(references: List[ReferenceEntry], issue: str) -> List[ReferenceEntry]:
    for ref in references:
        ref.validity = "unknown"
        if issue not in ref.issues:
            ref.issues.append(issue)
    return references


def _reference_metadata(references: List[ReferenceEntry]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for ref in references:
        keys = [ref.normalized_key, ref.author_year_key, ref.label, ref.ref_id]
        value = {
            "ref_id": ref.ref_id,
            "title": ref.s2_metadata.get("title") or ref.title,
            "abstract": ref.s2_metadata.get("abstract"),
            "authors": ref.s2_metadata.get("authors") or ref.authors,
            "year": ref.s2_metadata.get("year") or ref.year,
            "venue": ref.s2_metadata.get("venue"),
            "url": ref.s2_metadata.get("url"),
            "external_ids": ref.s2_metadata.get("externalIds"),
            "tldr": _extract_tldr_text(ref.s2_metadata.get("tldr")),
            "open_access_pdf": ref.s2_metadata.get("openAccessPdf"),
            "validity": ref.validity,
            "s2_paper_id": ref.s2_paper_id,
        }
        for key in keys:
            if key:
                metadata[key] = value
    return metadata


def _extract_tldr_text(value: Any) -> str | None:
    if isinstance(value, dict):
        text = value.get("text")
        return str(text).strip() if text else None
    if isinstance(value, str):
        return value.strip() or None
    return None


def _resolve_candidate_citation_keys(candidate: Dict[str, Any], references: List[ReferenceEntry]) -> Dict[str, Any]:
    lookup = build_reference_lookup(references)
    for claim in candidate.get("claims", []):
        claim["citations"] = _resolve_keys(claim.get("citations", []), lookup)
    for topic in candidate.get("topics", []):
        topic["key_citations"] = _resolve_keys(topic.get("key_citations", []), lookup)
    return candidate


def _resolve_gold_citation_keys(gold: Dict[str, Any], references: List[ReferenceEntry]) -> Dict[str, Any]:
    lookup = build_reference_lookup(references)
    for point in gold.get("key_points", []):
        point["citations"] = _resolve_keys(point.get("citations", []), lookup)
    for topic in gold.get("topics", []):
        topic["key_citations"] = _resolve_keys(topic.get("key_citations", []), lookup)
    for key_ref in gold.get("key_references", []):
        resolved = _resolve_keys([key_ref.get("reference_key")], lookup)
        if resolved:
            key_ref["reference_key"] = resolved[0]
    return gold


def _resolve_keys(keys: List[str], lookup: Dict[str, ReferenceEntry]) -> List[str]:
    resolved = []
    for key in keys or []:
        ref = lookup.get(str(key))
        new_key = ref.normalized_key or ref.author_year_key or ref.label or ref.ref_id if ref else str(key)
        if new_key and new_key not in resolved:
            resolved.append(new_key)
    return resolved


def _diagnostics(metric_results: Dict[str, Dict[str, Any]], claim_judgment: Dict[str, Any]) -> Dict[str, Any]:
    coverage = metric_results["content_coverage"]["details"]
    citation = metric_results["citation_quality"]["details"]
    thematic = metric_results["thematic_structure"]["details"]
    length = metric_results["length_conciseness"]["details"]

    hallucinated_refs = [
        ref
        for ref in citation.get("validity", {}).get("references", [])
        if ref.get("validity") == "metadata_mismatch"
    ]
    return {
        "missing_points": coverage.get("missing_points", []),
        "hallucinated_references": hallucinated_refs,
        "bad_citation_claim_pairs": citation.get("problematic_citation_claim_pairs", []),
        "overclaim_citation_claim_pairs": citation.get("overclaim_citation_claim_pairs", []),
        "citation_group_support": _nonredundant_citation_group_support(citation),
        "topic_structure_issues": thematic.get("issues", []),
        "length_conciseness_issues": _length_issues(length),
    }


def _nonredundant_citation_group_support(citation_details: Dict[str, Any]) -> List[Dict[str, Any]]:
    pair_judgments = citation_details.get("citation_judgments", [])
    pair_support_by_claim: Dict[str, List[str]] = {}
    for item in pair_judgments:
        claim_id = str(item.get("claim_id") or "")
        if not claim_id:
            continue
        pair_support_by_claim.setdefault(claim_id, []).append(str(item.get("support", "unknown") or "unknown").lower())

    filtered: List[Dict[str, Any]] = []
    for item in citation_details.get("citation_group_judgments", []):
        claim_id = str(item.get("claim_id") or "")
        citation_count = int(item.get("citation_count") or 0)
        if citation_count < 2:
            continue

        supports = pair_support_by_claim.get(claim_id, [])
        group_support = str(item.get("group_support", "unknown") or "unknown").lower()
        covered = [str(x).strip() for x in (item.get("covered_aspects") or []) if str(x).strip()]
        missing = [str(x).strip() for x in (item.get("missing_aspects") or []) if str(x).strip()]
        unique_pair_supports = set(supports)

        has_incremental_signal = (
            bool(covered)
            or bool(missing)
            or len(unique_pair_supports) > 1
            or group_support not in unique_pair_supports
        )
        if has_incremental_signal:
            filtered.append(item)
    return filtered


def _length_issues(length_details: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    ratio = float(length_details.get("length_ratio", 0.0) or 0.0)
    sub_scores = length_details.get("sub_scores", {})
    if sub_scores.get("relative_length_score", 10.0) < 7.0:
        issues.append(
            {
                "type": "relative_length",
                "length_ratio": ratio,
                "s_word_count": length_details.get("s_word_count"),
                "g_word_count": length_details.get("g_word_count"),
            }
        )
    redundancy = length_details.get("redundancy", {})
    for pair in redundancy.get("duplicate_sentence_pairs", []):
        issues.append({"type": "duplicate_sentence", **pair})
    for pair in redundancy.get("duplicate_paragraph_pairs", []):
        issues.append({"type": "duplicate_paragraph", **pair})
    return issues

"""LLM-backed judging."""

from __future__ import annotations

from typing import Any, Dict, List

from rw_eval.llm.client import LLMClient, LLMError, LLMNotConfigured
from rw_eval.llm.prompts import (
    SYSTEM_JSON,
    alignment_prompt,
    citation_appropriateness_prompt,
    citation_group_support_prompt,
    citation_pair_recheck_prompt,
    claim_judgment_prompt,
    synthesis_writing_prompt,
    thematic_prompt,
)
from rw_eval.schemas import ReferenceEntry


class Judger:
    def __init__(self, llm: LLMClient, strict: bool = False):
        self.llm = llm
        self.strict = strict
        self.warnings: List[Dict[str, str]] = []

    def judge_alignment(self, gold: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"gold_key_points": gold.get("key_points", []), "candidate_claims": candidate.get("claims", [])}
        self._require_llm("alignment_judging")
        try:
            return _ensure_key(self.llm.chat_json(SYSTEM_JSON, alignment_prompt(payload), max_retries=2), "alignments")
        except LLMError as exc:
            raise LLMError(f"alignment_judging failed: {exc}") from exc

    def judge_claims(self, gold: Dict[str, Any], candidate: Dict[str, Any], reference_metadata: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "ground_truth_key_points": gold.get("key_points", []),
            "candidate_claims": _attach_claim_reference_metadata(candidate.get("claims", []), reference_metadata),
        }
        self._require_llm("claim_judging")
        try:
            return _ensure_key(self.llm.chat_json(SYSTEM_JSON, claim_judgment_prompt(payload), max_retries=2), "claim_judgments")
        except LLMError as exc:
            raise LLMError(f"claim_judging failed: {exc}") from exc

    def judge_thematic(self, gold: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"gold_topics": gold.get("topics", []), "candidate_topics": candidate.get("topics", [])}
        self._require_llm("thematic_judging")
        try:
            data = self.llm.chat_json(SYSTEM_JSON, thematic_prompt(payload), max_retries=2)
            return _normalize_thematic(data)
        except LLMError as exc:
            raise LLMError(f"thematic_judging failed: {exc}") from exc

    def judge_synthesis_writing(self, sample_text: str, gold: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"candidate_text": sample_text, "gold": gold, "candidate": candidate}
        self._require_llm("synthesis_writing_judging")
        try:
            return _normalize_synthesis_writing(
                self.llm.chat_json(SYSTEM_JSON, synthesis_writing_prompt(payload), max_retries=2)
            )
        except LLMError as exc:
            raise LLMError(f"synthesis_writing_judging failed: {exc}") from exc

    def judge_citation_appropriateness(
        self,
        candidate: Dict[str, Any],
        reference_metadata: Dict[str, Any],
        reference_lookup: Dict[str, ReferenceEntry] | None = None,
        evidence_retriever: Any | None = None,
    ) -> Dict[str, Any]:
        payload = {"candidate_claims": candidate.get("claims", []), "reference_metadata": reference_metadata}
        self._require_llm("citation_appropriateness_judging")
        try:
            data = _ensure_key(
                self.llm.chat_json(SYSTEM_JSON, citation_appropriateness_prompt(payload), max_retries=2),
                "citation_judgments",
            )
            normalized = _normalize_citation_judgments(data)
            finalized = self._finalize_citation_judgments(
                candidate.get("claims", []),
                normalized,
                reference_metadata,
                reference_lookup or {},
                evidence_retriever,
            )
            finalized["citation_group_judgments"] = self._judge_citation_groups(candidate.get("claims", []), finalized["citation_judgments"])
            return finalized
        except LLMError as exc:
            raise LLMError(f"citation_appropriateness_judging failed: {exc}") from exc

    def _require_llm(self, stage: str) -> None:
        if not self.llm.is_configured():
            raise LLMNotConfigured(f"{stage} requires a configured LLM; heuristic judging has been removed.")

    def _finalize_citation_judgments(
        self,
        claims: List[Dict[str, Any]],
        data: Dict[str, Any],
        reference_metadata: Dict[str, Any],
        reference_lookup: Dict[str, ReferenceEntry],
        evidence_retriever: Any | None,
    ) -> Dict[str, Any]:
        judgments_by_pair = {
            (str(item.get("claim_id")), str(item.get("reference_key"))): item
            for item in data.get("citation_judgments", [])
            if item.get("claim_id") and item.get("reference_key")
        }
        finalized = []
        retrieval_events = []
        for claim in claims:
            claim_id = str(claim.get("id") or "")
            citations = [str(key) for key in (claim.get("citations") or []) if key]
            for reference_key in citations:
                pair_key = (claim_id, reference_key)
                current = judgments_by_pair.get(pair_key)
                used_second_pass = False
                if current is None or _needs_second_pass(current):
                    used_second_pass = True
                    refreshed, event = self._rejudge_citation_pair(
                        claim,
                        reference_key,
                        reference_metadata.get(reference_key, {}),
                        reference_lookup.get(reference_key),
                        current,
                        evidence_retriever,
                    )
                    if event is not None:
                        retrieval_events.append(event)
                    if refreshed is not None:
                        current = refreshed
                if current is None:
                    current = _missing_citation_judgment(claim_id, reference_key)
                current = dict(current)
                if used_second_pass:
                    current["second_pass_used"] = True
                finalized.append(current)
        return {"citation_judgments": finalized, "retrieval_events": retrieval_events}

    def _rejudge_citation_pair(
        self,
        claim: Dict[str, Any],
        reference_key: str,
        reference_meta: Dict[str, Any],
        reference_entry: ReferenceEntry | None,
        initial_judgment: Dict[str, Any] | None,
        evidence_retriever: Any | None,
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
        evidence_bundle = {"query": "", "snippets": [], "paper_metadata": {}, "errors": []}
        if evidence_retriever is not None and reference_entry is not None:
            try:
                evidence_bundle = evidence_retriever.retrieve_claim_evidence(reference_entry, str(claim.get("text", "") or ""))
            except Exception as exc:  # pragma: no cover - defensive network/retrieval guard
                evidence_bundle = {"query": "", "snippets": [], "paper_metadata": {}, "errors": [str(exc)]}

        payload = {
            "claim": {
                "claim_id": claim.get("id"),
                "text": claim.get("text"),
                "paragraph_id": claim.get("paragraph_id"),
            },
            "reference_key": reference_key,
            "reference_metadata": reference_meta,
            "initial_judgment": initial_judgment or {},
            "retrieved_evidence": evidence_bundle.get("snippets", []),
        }
        event = {
            "claim_id": claim.get("id"),
            "reference_key": reference_key,
            "query": evidence_bundle.get("query", ""),
            "snippet_count": len(evidence_bundle.get("snippets", [])),
            "errors": evidence_bundle.get("errors", []),
        }
        try:
            response = self.llm.chat_json(SYSTEM_JSON, citation_pair_recheck_prompt(payload), max_retries=2)
            refreshed = _normalize_single_citation_judgment(response, claim.get("id"), reference_key)
            if _is_effectively_empty_citation_judgment(refreshed):
                refreshed = _missing_citation_judgment(str(claim.get("id") or ""), reference_key)
            refreshed["retrieval_used"] = bool(evidence_bundle.get("snippets"))
            refreshed["retrieved_evidence"] = evidence_bundle.get("snippets", [])
            return refreshed, event
        except LLMError as exc:
            self.warnings.append(
                {
                    "stage": "citation_pair_recheck",
                    "message": str(exc),
                    "claim_id": str(claim.get("id")),
                    "reference_key": reference_key,
                }
            )
            if initial_judgment is not None:
                preserved = dict(initial_judgment)
                preserved["retrieval_used"] = bool(evidence_bundle.get("snippets"))
                preserved["retrieved_evidence"] = evidence_bundle.get("snippets", [])
                return preserved, event
            fallback = _missing_citation_judgment(str(claim.get("id") or ""), reference_key)
            fallback["retrieval_used"] = bool(evidence_bundle.get("snippets"))
            fallback["retrieved_evidence"] = evidence_bundle.get("snippets", [])
            return fallback, event

    def _judge_citation_groups(self, claims: List[Dict[str, Any]], citation_judgments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        judgments_by_claim: Dict[str, List[Dict[str, Any]]] = {}
        for item in citation_judgments:
            claim_id = str(item.get("claim_id") or "")
            if not claim_id:
                continue
            judgments_by_claim.setdefault(claim_id, []).append(item)

        groups: List[Dict[str, Any]] = []
        for claim in claims:
            claim_id = str(claim.get("id") or "")
            claim_pairs = judgments_by_claim.get(claim_id, [])
            if not claim_pairs:
                continue
            if len(claim_pairs) == 1:
                groups.append(_single_pair_group_judgment(claim_id, claim_pairs[0]))
                continue

            payload = {
                "claim": {
                    "claim_id": claim_id,
                    "text": claim.get("text"),
                    "paragraph_id": claim.get("paragraph_id"),
                },
                "citation_pairs": [
                    {
                        "reference_key": item.get("reference_key"),
                        "support": item.get("support"),
                        "support_rationale": item.get("support_rationale"),
                        "overclaim_status": item.get("overclaim_status"),
                        "overclaim_rationale": item.get("overclaim_rationale"),
                        "retrieved_evidence": item.get("retrieved_evidence", []),
                    }
                    for item in claim_pairs
                ],
            }
            try:
                response = self.llm.chat_json(SYSTEM_JSON, citation_group_support_prompt(payload), max_retries=2)
                groups.append(_normalize_group_judgment(response, claim_id, len(claim_pairs), claim_pairs))
            except LLMError as exc:
                self.warnings.append(
                    {
                        "stage": "citation_group_judging",
                        "message": str(exc),
                        "claim_id": claim_id,
                    }
                )
                groups.append(_fallback_group_judgment(claim_id, claim_pairs))
        return groups


def _ensure_key(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    data.setdefault(key, [])
    return data


def _normalize_thematic(data: Dict[str, Any]) -> Dict[str, Any]:
    data.setdefault("topic_alignment", [])
    data.setdefault("paragraph_scores", [])
    data.setdefault("topic_granularity", {"score": 0.0, "rationale": ""})
    data.setdefault("topic_ordering", {"score": 0.0, "rationale": ""})
    return data


def _normalize_synthesis_writing(data: Dict[str, Any]) -> Dict[str, Any]:
    data.setdefault("synthesis_quality", {"score": 0.0, "rationale": "", "issues": []})
    data.setdefault("writing_quality", {"score": 0.0, "rationale": "", "issues": []})
    return data


def _normalize_citation_judgments(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = []
    for item in data.get("citation_judgments", []):
        normalized.append(_coerce_citation_judgment(item))
    data["citation_judgments"] = normalized
    return data


def _normalize_single_citation_judgment(data: Dict[str, Any], claim_id: Any, reference_key: str) -> Dict[str, Any]:
    item = data.get("citation_judgment") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        item = {}
    item = dict(item)
    item.setdefault("claim_id", claim_id)
    item.setdefault("reference_key", reference_key)
    return _coerce_citation_judgment(item)


def _attach_claim_reference_metadata(claims: List[Dict[str, Any]], reference_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    enriched_claims = []
    for claim in claims:
        citations = claim.get("citations") or []
        claim_metadata = {}
        for key in citations:
            meta = reference_metadata.get(key)
            if meta is not None:
                claim_metadata[key] = meta
        enriched = dict(claim)
        enriched["reference_metadata"] = claim_metadata
        enriched_claims.append(enriched)
    return enriched_claims


def _coerce_citation_judgment(item: Dict[str, Any]) -> Dict[str, Any]:
    support = str(item.get("support", "unknown") or "unknown").lower()
    support_rationale = item.get("support_rationale") or item.get("rationale") or ""
    overclaim_status = str(item.get("overclaim_status", "none") or "none").lower()
    overclaim_rationale = item.get("overclaim_rationale") or ""
    if support not in {"yes", "partial"}:
        overclaim_status = "none"
        overclaim_rationale = ""
    normalized_item = dict(item)
    normalized_item["support"] = support
    normalized_item["support_rationale"] = support_rationale
    normalized_item["rationale"] = support_rationale
    normalized_item["overclaim_status"] = overclaim_status
    normalized_item["overclaim_rationale"] = overclaim_rationale
    return normalized_item


def _needs_second_pass(judgment: Dict[str, Any]) -> bool:
    support = str(judgment.get("support", "unknown") or "unknown").lower()
    appropriateness = float(judgment.get("appropriateness_score", 0.0) or 0.0)
    rationale = str(judgment.get("support_rationale") or judgment.get("rationale") or "").strip()
    return support in {"weak", "no", "unknown"} or appropriateness < 6.0 or not rationale


def _missing_citation_judgment(claim_id: str, reference_key: str) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "reference_key": reference_key,
        "support": "unknown",
        "appropriateness_score": 0.0,
        "placement_score": 0.0,
        "topic_consistency_score": 0.0,
        "support_rationale": "No citation judgment was returned for this claim-citation pair.",
        "overclaim_status": "none",
        "overclaim_rationale": "",
        "rationale": "No citation judgment was returned for this claim-citation pair.",
    }


def _is_effectively_empty_citation_judgment(judgment: Dict[str, Any]) -> bool:
    return (
        str(judgment.get("support", "unknown") or "unknown").lower() == "unknown"
        and not str(judgment.get("support_rationale") or "").strip()
        and float(judgment.get("appropriateness_score", 0.0) or 0.0) == 0.0
        and float(judgment.get("placement_score", 0.0) or 0.0) == 0.0
        and float(judgment.get("topic_consistency_score", 0.0) or 0.0) == 0.0
    )


def _single_pair_group_judgment(claim_id: str, pair: Dict[str, Any]) -> Dict[str, Any]:
    rationale = pair.get("support_rationale") or pair.get("rationale") or ""
    return {
        "claim_id": claim_id,
        "citation_count": 1,
        "group_support": str(pair.get("support", "unknown") or "unknown").lower(),
        "group_rationale": rationale or "Single citation group judgment mirrors the pair-level judgment.",
        "covered_aspects": [],
        "missing_aspects": [],
        "derived_from_single_pair": True,
        "reference_keys": [pair.get("reference_key")],
    }


def _normalize_group_judgment(
    data: Dict[str, Any],
    claim_id: str,
    citation_count: int,
    claim_pairs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    item = data.get("citation_group_judgment") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        item = {}
    support = str(item.get("group_support", "unknown") or "unknown").lower()
    reference_keys = [str(x) for x in (item.get("reference_keys") or []) if str(x)]
    if not reference_keys:
        reference_keys = [str(pair.get("reference_key")) for pair in claim_pairs if pair.get("reference_key")]
    return {
        "claim_id": item.get("claim_id") or claim_id,
        "citation_count": int(item.get("citation_count") or citation_count),
        "group_support": support,
        "group_rationale": str(item.get("group_rationale") or "").strip(),
        "covered_aspects": [str(x).strip() for x in (item.get("covered_aspects") or []) if str(x).strip()],
        "missing_aspects": [str(x).strip() for x in (item.get("missing_aspects") or []) if str(x).strip()],
        "derived_from_single_pair": False,
        "reference_keys": reference_keys,
    }


def _fallback_group_judgment(claim_id: str, claim_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    supports = [str(item.get("support", "unknown") or "unknown").lower() for item in claim_pairs]
    if any(value == "yes" for value in supports):
        group_support = "partial" if any(value in {"weak", "no", "unknown"} for value in supports) else "yes"
    elif any(value == "partial" for value in supports):
        group_support = "partial"
    elif any(value == "weak" for value in supports):
        group_support = "weak"
    elif any(value == "no" for value in supports):
        group_support = "no"
    else:
        group_support = "unknown"
    return {
        "claim_id": claim_id,
        "citation_count": len(claim_pairs),
        "group_support": group_support,
        "group_rationale": "Fallback group judgment aggregated from pair-level citation support.",
        "covered_aspects": [],
        "missing_aspects": [],
        "derived_from_single_pair": False,
        "reference_keys": [item.get("reference_key") for item in claim_pairs if item.get("reference_key")],
    }

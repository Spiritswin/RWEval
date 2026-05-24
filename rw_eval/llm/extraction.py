"""LLM-backed extraction."""

from __future__ import annotations

from typing import Any, Dict, List

from rw_eval.llm.client import LLMClient, LLMError, LLMNotConfigured
from rw_eval.llm.prompts import SYSTEM_JSON, candidate_extraction_prompt, gold_extraction_prompt
from rw_eval.schemas import ParsedDocument, ReferenceEntry, to_plain


class Extractor:
    def __init__(self, llm: LLMClient, strict: bool = False):
        self.llm = llm
        self.strict = strict
        self.warnings: List[Dict[str, str]] = []

    def extract_gold(self, document: ParsedDocument) -> Dict[str, Any]:
        self._require_llm("gold_extraction")
        payload = _document_payload(document)
        try:
            return _normalize_gold(self.llm.chat_json(SYSTEM_JSON, gold_extraction_prompt(payload), max_retries=2))
        except LLMError as exc:
            raise LLMError(f"gold_extraction failed: {exc}") from exc

    def extract_candidate(self, document: ParsedDocument) -> Dict[str, Any]:
        self._require_llm("candidate_extraction")
        payload = _document_payload(document)
        try:
            return _normalize_candidate(self.llm.chat_json(SYSTEM_JSON, candidate_extraction_prompt(payload), max_retries=2))
        except LLMError as exc:
            raise LLMError(f"candidate_extraction failed: {exc}") from exc

    def _require_llm(self, stage: str) -> None:
        if not self.llm.is_configured():
            raise LLMNotConfigured(f"{stage} requires a configured LLM; heuristic extraction has been removed.")


def _document_payload(document: ParsedDocument) -> Dict[str, Any]:
    return {
        "paragraphs": [to_plain(p) for p in document.paragraphs],
        "sentences": [to_plain(s) for s in document.sentences],
        "citation_mentions": [to_plain(c) for c in document.citation_mentions],
        "references": [_reference_payload(r) for r in document.references],
    }


def _reference_payload(ref: ReferenceEntry) -> Dict[str, Any]:
    return {
        "ref_id": ref.ref_id,
        "label": ref.label,
        "title": ref.title,
        "authors": ref.authors,
        "year": ref.year,
        "normalized_key": ref.normalized_key,
        "s2_paper_id": ref.s2_paper_id,
        "validity": ref.validity,
        "metadata": {
            "title": ref.s2_metadata.get("title"),
            "abstract": ref.s2_metadata.get("abstract"),
            "year": ref.s2_metadata.get("year"),
            "venue": ref.s2_metadata.get("venue"),
        },
    }


def _normalize_gold(data: Dict[str, Any]) -> Dict[str, Any]:
    data.setdefault("topics", [])
    data.setdefault("key_points", [])
    data.setdefault("key_references", [])
    return data


def _normalize_candidate(data: Dict[str, Any]) -> Dict[str, Any]:
    data.setdefault("topics", [])
    data.setdefault("claims", [])
    return data

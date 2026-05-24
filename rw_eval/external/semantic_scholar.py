"""Semantic Scholar Graph API client."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from rw_eval.external.cache import JsonCache
from rw_eval.parsing.references import make_reference_key
from rw_eval.schemas import ReferenceEntry
from rw_eval.utils import text_similarity


DEFAULT_FIELDS = (
    "paperId,title,authors,year,venue,publicationDate,abstract,externalIds,"
    "citationCount,referenceCount,fieldsOfStudy,s2FieldsOfStudy,url"
)
RETRIEVAL_FIELDS = DEFAULT_FIELDS + ",tldr,openAccessPdf"


class SemanticScholarClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: int = 30,
        cache: Optional[JsonCache] = None,
        fields: str = DEFAULT_FIELDS,
    ):
        self.base_url = (base_url or os.environ.get("SEMANTIC_SCHOLAR_BASE_URL") or "https://api.semanticscholar.org/graph/v1").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.cache = cache
        self.fields = fields
        self.last_request_at = 0.0
        self.request_retries = max(0, int(os.environ.get("SEMANTIC_SCHOLAR_REQUEST_RETRIES", "3")))
        self.retry_backoff_seconds = _env_float("SEMANTIC_SCHOLAR_RETRY_BACKOFF_SECONDS", 1.5)

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def normalize_references(self, references: List[ReferenceEntry]) -> List[ReferenceEntry]:
        normalized: List[ReferenceEntry] = []
        for ref in references:
            normalized.append(self.normalize_reference(ref))
        return normalized

    def normalize_reference(self, ref: ReferenceEntry) -> ReferenceEntry:
        if not self.api_key:
            out = replace(ref)
            out.validity = "unknown"
            out.issues = list(out.issues) + ["semantic_scholar_api_key_missing"]
            return out

        lookup_key = json.dumps(
            {
                "doi": ref.doi,
                "arxiv_id": ref.arxiv_id,
                "title": ref.title,
                "year": ref.year,
                "raw": ref.raw_text,
            },
            sort_keys=True,
        )
        cached = self.cache.get("semantic_scholar_normalize", lookup_key) if self.cache else None
        if cached is not None:
            return _reference_from_cached(ref, cached)

        metadata: Optional[Dict[str, Any]] = None
        errors: List[str] = []

        for external_id in _external_id_candidates(ref):
            try:
                metadata = self.get_paper(external_id)
                if metadata and metadata.get("paperId"):
                    break
            except SemanticScholarError as exc:
                errors.append(str(exc))
                metadata = None

        if not metadata:
            query = ref.title or ref.raw_text
            try:
                candidates = self.search_papers(query, limit=5)
                metadata, _ = _select_best_candidate(ref, candidates)
            except SemanticScholarError as exc:
                errors.append(str(exc))

        out = replace(ref)
        if metadata:
            out.s2_paper_id = metadata.get("paperId")
            out.s2_metadata = metadata
            out.match_score = _metadata_match_score(ref, metadata)
            out.validity = "valid" if out.match_score >= 0.65 else "metadata_mismatch"
            if out.validity == "metadata_mismatch":
                out.issues = list(out.issues) + ["metadata_mismatch"]
            out.normalized_key = make_reference_key(out)
        else:
            out.validity = "unresolved"
            out.issues = list(out.issues) + (errors or ["semantic_scholar_no_match"])

        if self.cache:
            self.cache.set("semantic_scholar_normalize", lookup_key, _cached_reference_payload(out))
        return out

    def get_paper(self, paper_id: str) -> Dict[str, Any]:
        return self.get_paper_with_fields(paper_id, self.fields)

    def get_paper_with_fields(self, paper_id: str, fields: str) -> Dict[str, Any]:
        return self._request("GET", f"/paper/{urllib.parse.quote(paper_id, safe=':')}", params={"fields": fields})

    def search_papers(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query:
            return []
        payload = self._request(
            "GET",
            "/paper/search",
            params={"query": query, "limit": str(limit), "fields": self.fields},
        )
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return data if isinstance(data, list) else []

    def retrieve_claim_evidence(self, ref: ReferenceEntry, claim_text: str, max_snippets: int = 4) -> Dict[str, Any]:
        cache_key = json.dumps(
            {
                "paper_id": ref.s2_paper_id,
                "doi": ref.doi,
                "arxiv_id": ref.arxiv_id,
                "title": ref.title,
                "claim_text": claim_text,
                "max_snippets": max_snippets,
            },
            sort_keys=True,
        )
        cached = self.cache.get("semantic_scholar_claim_evidence", cache_key) if self.cache else None
        if cached is not None:
            return cached

        snippets: List[Dict[str, str]] = []
        paper = dict(ref.s2_metadata or {})
        errors: List[str] = []

        if ref.s2_paper_id:
            try:
                paper = self.get_paper_with_fields(ref.s2_paper_id, RETRIEVAL_FIELDS)
            except SemanticScholarError as exc:
                errors.append(str(exc))

        if not paper and ref.title:
            try:
                candidates = self.search_papers(ref.title, limit=3)
                paper, _ = _select_best_candidate(ref, candidates)
                paper = paper or {}
            except SemanticScholarError as exc:
                errors.append(str(exc))

        snippets.extend(_paper_evidence_snippets(paper))

        doi = ref.doi or _external_id_from_metadata(paper, "DOI")
        if doi:
            try:
                crossref_abstract = self._fetch_crossref_abstract(doi)
                if crossref_abstract:
                    snippets.append(
                        {
                            "source": "crossref_abstract",
                            "citation": f"doi:{doi}",
                            "text": crossref_abstract,
                        }
                    )
            except SemanticScholarError as exc:
                errors.append(str(exc))

        arxiv_id = ref.arxiv_id or _external_id_from_metadata(paper, "ArXiv")
        if arxiv_id:
            try:
                arxiv_summary = self._fetch_arxiv_summary(arxiv_id)
                if arxiv_summary:
                    snippets.append(
                        {
                            "source": "arxiv_summary",
                            "citation": f"arxiv:{arxiv_id}",
                            "text": arxiv_summary,
                        }
                    )
            except SemanticScholarError as exc:
                errors.append(str(exc))

        result = {
            "query": _build_claim_query(ref, claim_text),
            "snippets": _dedupe_snippets(snippets)[:max_snippets],
            "paper_metadata": {
                "paper_id": paper.get("paperId") or ref.s2_paper_id,
                "title": paper.get("title") or ref.title,
                "venue": paper.get("venue"),
                "year": paper.get("year") or ref.year,
                "url": paper.get("url"),
            },
            "errors": errors,
        }
        if self.cache:
            self.cache.set("semantic_scholar_claim_evidence", cache_key, result)
        return result

    def _request(self, method: str, path: str, params: Optional[Dict[str, str]] = None, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        cache_key = json.dumps({"method": method, "url": url, "body": body}, sort_keys=True)
        cached = self.cache.get("semantic_scholar_http", cache_key) if self.cache else None
        if cached is not None:
            return cached

        self._pace()
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(self.request_retries + 1):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    payload = json.loads(raw) if raw else {}
                    break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = SemanticScholarError(f"Semantic Scholar HTTP {exc.code}: {detail}")
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < self.request_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise last_error from exc
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < self.request_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise SemanticScholarError(f"Semantic Scholar request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise SemanticScholarError(f"Semantic Scholar returned invalid JSON: {exc}") from exc
        else:
            raise SemanticScholarError(f"Semantic Scholar request failed: {last_error}")

        if self.cache:
            self.cache.set("semantic_scholar_http", cache_key, payload)
        return payload

    def _pace(self) -> None:
        elapsed = time.time() - self.last_request_at
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)
        self.last_request_at = time.time()

    def _fetch_crossref_abstract(self, doi: str) -> Optional[str]:
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        payload = self._request_json_url(url, headers={"Accept": "application/json"})
        message = payload.get("message", {}) if isinstance(payload, dict) else {}
        abstract = message.get("abstract")
        if not isinstance(abstract, str) or not abstract.strip():
            return None
        return _clean_markup_text(abstract)

    def _fetch_arxiv_summary(self, arxiv_id: str) -> Optional[str]:
        url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id, safe="")
        payload = self._request_text_url(url, headers={"Accept": "application/atom+xml"})
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise SemanticScholarError(f"arXiv returned invalid XML: {exc}") from exc
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        summary = root.findtext("atom:entry/atom:summary", default="", namespaces=namespace)
        cleaned = re.sub(r"\s+", " ", summary or "").strip()
        return cleaned or None

    def _request_json_url(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        raw = self._request_text_url(url, headers=headers)
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise SemanticScholarError(f"External retrieval returned invalid JSON: {exc}") from exc

    def _request_text_url(self, url: str, headers: Optional[Dict[str, str]] = None) -> str:
        cache_key = json.dumps({"url": url, "headers": headers or {}}, sort_keys=True)
        cached = self.cache.get("semantic_scholar_external_http", cache_key) if self.cache else None
        if cached is not None:
            return str(cached)

        last_error: Exception | None = None
        for attempt in range(self.request_retries + 1):
            request = urllib.request.Request(url, method="GET", headers=headers or {})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    if self.cache:
                        self.cache.set("semantic_scholar_external_http", cache_key, raw)
                    return raw
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = SemanticScholarError(f"External retrieval HTTP {exc.code}: {detail}")
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < self.request_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise last_error from exc
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < self.request_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise SemanticScholarError(f"External retrieval failed: {exc}") from exc
        raise SemanticScholarError(f"External retrieval failed: {last_error}")


class SemanticScholarError(RuntimeError):
    pass


def _external_id_candidates(ref: ReferenceEntry) -> List[str]:
    candidates: List[str] = []
    if ref.doi:
        candidates.append(f"DOI:{ref.doi}")
    if ref.arxiv_id:
        candidates.append(f"ARXIV:{ref.arxiv_id}")
    return candidates


def _select_best_candidate(ref: ReferenceEntry, candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for candidate in candidates:
        score = _metadata_match_score(ref, candidate)
        if score > best_score:
            best = candidate
            best_score = score
    if best_score < 0.45:
        return None, best_score
    return best, best_score


def _metadata_match_score(ref: ReferenceEntry, metadata: Dict[str, Any]) -> float:
    score = 0.0
    weight = 0.0
    if ref.title and metadata.get("title"):
        score += 0.65 * text_similarity(ref.title, metadata.get("title", ""))
        weight += 0.65
    if ref.year and metadata.get("year"):
        score += 0.20 * (1.0 if int(ref.year) == int(metadata.get("year")) else 0.0)
        weight += 0.20
    if ref.authors and metadata.get("authors"):
        ref_first = ref.authors[0].lower()
        meta_authors = " ".join(a.get("name", "") for a in metadata.get("authors", [])).lower()
        score += 0.15 * (1.0 if ref_first.split(",")[0].strip() in meta_authors else 0.0)
        weight += 0.15
    if weight == 0:
        return 0.0
    return score / weight


def _cached_reference_payload(ref: ReferenceEntry) -> Dict[str, Any]:
    return {
        "s2_paper_id": ref.s2_paper_id,
        "s2_metadata": ref.s2_metadata,
        "validity": ref.validity,
        "match_score": ref.match_score,
        "issues": ref.issues,
        "normalized_key": ref.normalized_key,
    }


def _reference_from_cached(ref: ReferenceEntry, cached: Dict[str, Any]) -> ReferenceEntry:
    out = replace(ref)
    out.s2_paper_id = cached.get("s2_paper_id")
    out.s2_metadata = cached.get("s2_metadata") or {}
    out.validity = cached.get("validity", "unknown")
    out.match_score = float(cached.get("match_score", 0.0))
    out.issues = list(cached.get("issues") or [])
    out.normalized_key = cached.get("normalized_key") or make_reference_key(out)
    return out


def _build_claim_query(ref: ReferenceEntry, claim_text: str) -> str:
    title = ref.title or (ref.s2_metadata or {}).get("title") or "unknown paper"
    claim = re.sub(r"\s+", " ", claim_text or "").strip()
    return f"{title}: evidence for claim '{claim}'"


def _paper_evidence_snippets(metadata: Dict[str, Any]) -> List[Dict[str, str]]:
    snippets: List[Dict[str, str]] = []
    title = str(metadata.get("title") or "").strip()
    abstract = str(metadata.get("abstract") or "").strip()
    if title and abstract:
        snippets.append(
            {
                "source": "semantic_scholar_abstract",
                "citation": str(metadata.get("paperId") or title),
                "text": f"{title}. {abstract}",
            }
        )
    tldr = metadata.get("tldr")
    tldr_text = ""
    if isinstance(tldr, dict):
        tldr_text = str(tldr.get("text") or "").strip()
    elif isinstance(tldr, str):
        tldr_text = tldr.strip()
    if tldr_text:
        snippets.append(
            {
                "source": "semantic_scholar_tldr",
                "citation": str(metadata.get("paperId") or title or "tldr"),
                "text": tldr_text,
            }
        )
    return snippets


def _external_id_from_metadata(metadata: Dict[str, Any], key: str) -> Optional[str]:
    external_ids = metadata.get("externalIds") if isinstance(metadata, dict) else None
    if not isinstance(external_ids, dict):
        return None
    value = external_ids.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clean_markup_text(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = re.sub(r"\s+", " ", no_tags).strip()
    return cleaned


def _dedupe_snippets(snippets: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped: List[Dict[str, str]] = []
    for snippet in snippets:
        key = (snippet.get("source", ""), snippet.get("text", ""))
        if key in seen or not snippet.get("text"):
            continue
        seen.add(key)
        deduped.append(snippet)
    return deduped


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default

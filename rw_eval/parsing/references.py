"""Reference-list parsing with lightweight heuristics."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from rw_eval.schemas import ReferenceEntry
from rw_eval.utils import normalize_text


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", re.IGNORECASE)
ARXIV_RE = re.compile(r"\barXiv[:\s]*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+/[0-9]{7}(?:v\d+)?)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
REFERENCE_LABEL_RE = re.compile(r"^\s*(?:\[([A-Za-z0-9_.:-]+)\]|(\d+)[.)])\s*")
BIBTEX_ENTRY_RE = re.compile(r"@\w+\s*\{([^,]+),(.+?)\n\}", re.IGNORECASE | re.DOTALL)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?", re.DOTALL)


def parse_references(references_text: str) -> List[ReferenceEntry]:
    text = (references_text or "").strip()
    if not text:
        return []
    if "@" in text and "title" in text.lower():
        bib_entries = _parse_bibtex(text)
        if bib_entries:
            return bib_entries
    lines = _split_reference_lines(text)
    refs: List[ReferenceEntry] = []
    for index, line in enumerate(lines):
        entry = _parse_reference_line(line, index)
        refs.append(entry)
    return refs


def build_reference_lookup(references: List[ReferenceEntry]) -> Dict[str, ReferenceEntry]:
    lookup: Dict[str, ReferenceEntry] = {}
    for ref in references:
        for key in _reference_keys(ref):
            if key:
                lookup[key] = ref
    return lookup


def _split_reference_lines(text: str) -> List[str]:
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(raw_lines) <= 1:
        semicolon_parts = [p.strip() for p in re.split(r"\n|\r", text) if p.strip()]
        return semicolon_parts if semicolon_parts else [text]

    refs: List[str] = []
    current: List[str] = []
    starts_new = re.compile(r"^\s*(?:\[[A-Za-z0-9_.:-]+\]|\d+[.)]\s+|[A-Z][A-Za-z'`-]+,\s)")
    for line in raw_lines:
        if starts_new.match(line) and current:
            refs.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        refs.append(" ".join(current).strip())
    return refs


def _parse_bibtex(text: str) -> List[ReferenceEntry]:
    refs: List[ReferenceEntry] = []
    for index, match in enumerate(BIBTEX_ENTRY_RE.finditer(text)):
        key = match.group(1).strip()
        body = match.group(2)
        fields = {m.group(1).lower(): re.sub(r"\s+", " ", m.group(2)).strip() for m in BIB_FIELD_RE.finditer(body)}
        title = fields.get("title")
        year = _extract_year(fields.get("year", ""))
        authors = _split_authors(fields.get("author", ""))
        doi = _extract_doi(fields.get("doi", "") or body)
        arxiv_id = _extract_arxiv(fields.get("eprint", "") or body)
        ref = ReferenceEntry(
            ref_id=f"R{index + 1}",
            raw_text=match.group(0),
            label=key,
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
        )
        ref.author_year_key = make_author_year_key(ref)
        ref.normalized_key = make_reference_key(ref)
        refs.append(ref)
    return refs


def _parse_reference_line(line: str, index: int) -> ReferenceEntry:
    label: Optional[str] = None
    cleaned = line.strip()
    label_match = REFERENCE_LABEL_RE.match(cleaned)
    if label_match:
        label = label_match.group(1) or label_match.group(2)
        cleaned = cleaned[label_match.end() :].strip()

    doi = _extract_doi(cleaned)
    arxiv_id = _extract_arxiv(cleaned)
    year = _extract_year(cleaned)
    authors = _extract_authors(cleaned, year)
    title = _extract_title(cleaned, year)

    ref = ReferenceEntry(
        ref_id=f"R{index + 1}",
        raw_text=line,
        label=label,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        arxiv_id=arxiv_id,
    )
    ref.author_year_key = make_author_year_key(ref)
    ref.normalized_key = make_reference_key(ref)
    return ref


def _extract_doi(text: str) -> Optional[str]:
    match = DOI_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(".,)")


def _extract_arxiv(text: str) -> Optional[str]:
    match = ARXIV_RE.search(text or "")
    if not match:
        return None
    return match.group(1).rstrip(".")


def _extract_year(text: str) -> Optional[int]:
    matches = YEAR_RE.findall(text or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def _extract_authors(text: str, year: Optional[int]) -> List[str]:
    sentence_parts = _split_reference_sentences(text)
    if sentence_parts:
        author_part = sentence_parts[0]
        if year:
            author_part = author_part.replace(f"({year})", "").replace(str(year), "")
        return _split_authors(author_part)
    if not year:
        first_sentence = text.split(".", 1)[0]
        return _split_authors(first_sentence)
    year_pos = text.find(str(year))
    prefix = text[:year_pos]
    prefix = re.sub(r"[\(\[\{]\s*$", "", prefix).strip(" .")
    return _split_authors(prefix)


def _split_authors(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" .")
    if not cleaned:
        return []
    cleaned = cleaned.replace(" and ", "; ")
    parts = [p.strip(" .") for p in re.split(r";|\bet al\.\b", cleaned) if p.strip(" .")]
    if len(parts) == 1 and "," not in parts[0]:
        return [parts[0]]
    authors: List[str] = []
    current = []
    tokens = [p.strip() for p in cleaned.split(",") if p.strip()]
    for token in tokens:
        current.append(token)
        if len(current) >= 2:
            authors.append(", ".join(current))
            current = []
    if current and not authors:
        authors.append(" ".join(current))
    return authors[:12]


def _extract_title(text: str, year: Optional[int]) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    quoted = re.search(r"['\"]([^'\"]{8,})['\"]", cleaned)
    if quoted:
        return quoted.group(1).strip()
    sentence_parts = _split_reference_sentences(cleaned)
    if len(sentence_parts) >= 2:
        title = sentence_parts[1].strip()
        if _looks_like_title(title):
            return title
    if year:
        year_pos = cleaned.find(str(year))
        if year_pos >= 0:
            tail = cleaned[year_pos + 4 :].lstrip("). ]")
            pieces = [p.strip() for p in tail.split(".") if p.strip()]
            if pieces:
                return pieces[0]
    pieces = [p.strip() for p in cleaned.split(".") if p.strip()]
    candidates = [p for p in pieces if len(p.split()) >= 4]
    if candidates:
        return max(candidates[:3], key=len)
    return cleaned[:160] if cleaned else None


def _split_reference_sentences(text: str) -> List[str]:
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return []

    parts: List[str] = []
    start = 0
    index = 0
    while index < len(raw):
        if raw[index] != "." or index + 1 >= len(raw) or not raw[index + 1].isspace():
            index += 1
            continue
        if _is_middle_initial_period(raw, index):
            index += 1
            continue
        part = raw[start:index].strip(" .")
        if part:
            parts.append(part)
        start = index + 1
        while start < len(raw) and raw[start].isspace():
            start += 1
        index = start
    tail = raw[start:].strip(" .")
    if tail:
        parts.append(tail)
    return parts


def _is_middle_initial_period(text: str, period_index: int) -> bool:
    prev_start = period_index - 1
    while prev_start >= 0 and text[prev_start].isalpha():
        prev_start -= 1
    prev_token = text[prev_start + 1 : period_index]
    if len(prev_token) != 1 or not prev_token.isupper():
        return False

    next_start = period_index + 1
    while next_start < len(text) and text[next_start].isspace():
        next_start += 1
    if next_start + 1 >= len(text):
        return False
    return text[next_start].isupper() and text[next_start + 1] == "."


def _looks_like_title(text: str) -> bool:
    lower = (text or "").lower()
    if not text or len(text.split()) < 3:
        return False
    venue_starts = (
        "in proceedings",
        "in international",
        "in advances",
        "in conference",
        "proceedings of",
        "arxiv preprint",
        "journal of",
    )
    return not lower.startswith(venue_starts)


def make_author_year_key(ref: ReferenceEntry) -> Optional[str]:
    if not ref.authors or not ref.year:
        return None
    surname = author_surname(ref.authors[0])
    if not surname:
        return None
    return f"{surname.lower()}-{ref.year}"


def make_reference_key(ref: ReferenceEntry) -> str:
    if ref.doi:
        return f"doi:{ref.doi.lower()}"
    if ref.arxiv_id:
        return f"arxiv:{ref.arxiv_id.lower()}"
    if ref.s2_paper_id:
        return f"s2:{ref.s2_paper_id}"
    if ref.author_year_key:
        return ref.author_year_key
    if ref.title:
        title_norm = normalize_text(ref.title)
        return "title:" + "-".join(title_norm.split()[:8])
    return ref.ref_id


def author_surname(author: str) -> str:
    cleaned = re.sub(r"\bet\s+al\.?", "", author or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z\s,'`-]", "", cleaned).strip(" ,")
    if not cleaned:
        return ""
    if "," in cleaned:
        return cleaned.split(",", 1)[0].strip()
    return cleaned.split()[-1].strip()


def _reference_keys(ref: ReferenceEntry) -> List[str]:
    keys = [ref.ref_id]
    if ref.label:
        keys.append(ref.label)
        keys.append(f"[{ref.label}]")
    if ref.author_year_key:
        keys.append(ref.author_year_key)
    if ref.normalized_key:
        keys.append(ref.normalized_key)
    if ref.title:
        keys.append("title:" + normalize_text(ref.title))
    return keys

"""In-text citation parsing."""

from __future__ import annotations

import re
from typing import List

from rw_eval.parsing.references import author_surname
from rw_eval.schemas import CitationMention, Sentence


NUMERIC_CITATION_RE = re.compile(r"\[(\d+(?:\s*[-,;]\s*\d+)*)\]")
BRACKET_KEY_CITATION_RE = re.compile(r"\[([A-Za-z_][A-Za-z0-9_.:-]*(?:\s*[,;]\s*[A-Za-z_][A-Za-z0-9_.:-]*)*)\]")
PAREN_AUTHOR_YEAR_RE = re.compile(r"\(([^()]{0,180}?\b(?:19\d{2}|20\d{2})[a-z]?[^()]*)\)")
NARRATIVE_AUTHOR_YEAR_RE = re.compile(r"\b([A-Z][A-Za-z'`-]+)(?:\s+et\s+al\.)?\s*\((19\d{2}|20\d{2})[a-z]?\)")
BIBTEX_CITATION_RE = re.compile(r"\\cite\w*\s*\{([^{}]+)\}")
YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")


def extract_citation_mentions(sentences: List[Sentence]) -> List[CitationMention]:
    mentions: List[CitationMention] = []
    counter = 1
    for sentence in sentences:
        for match in BIBTEX_CITATION_RE.finditer(sentence.text):
            keys = _parse_bibtex_keys(match.group(1))
            if keys:
                mentions.append(
                    CitationMention(
                        mention_id=f"C{counter}",
                        paragraph_id=sentence.paragraph_id,
                        sentence_id=sentence.sentence_id,
                        raw_text=match.group(0),
                        citation_keys=keys,
                        start=match.start(),
                        end=match.end(),
                    )
                )
                counter += 1
        for match in NUMERIC_CITATION_RE.finditer(sentence.text):
            keys = _parse_numeric_keys(match.group(1))
            mentions.append(
                CitationMention(
                    mention_id=f"C{counter}",
                    paragraph_id=sentence.paragraph_id,
                    sentence_id=sentence.sentence_id,
                    raw_text=match.group(0),
                    citation_keys=keys,
                    start=match.start(),
                    end=match.end(),
                )
            )
            counter += 1
        for match in BRACKET_KEY_CITATION_RE.finditer(sentence.text):
            keys = _parse_bracket_keys(match.group(1))
            if keys:
                mentions.append(
                    CitationMention(
                        mention_id=f"C{counter}",
                        paragraph_id=sentence.paragraph_id,
                        sentence_id=sentence.sentence_id,
                        raw_text=match.group(0),
                        citation_keys=keys,
                        start=match.start(),
                        end=match.end(),
                    )
                )
                counter += 1
        for match in PAREN_AUTHOR_YEAR_RE.finditer(sentence.text):
            keys = _parse_author_year_parenthetical(match.group(1))
            if keys:
                mentions.append(
                    CitationMention(
                        mention_id=f"C{counter}",
                        paragraph_id=sentence.paragraph_id,
                        sentence_id=sentence.sentence_id,
                        raw_text=match.group(0),
                        citation_keys=keys,
                        start=match.start(),
                        end=match.end(),
                    )
                )
                counter += 1
        for match in NARRATIVE_AUTHOR_YEAR_RE.finditer(sentence.text):
            surname = author_surname(match.group(1))
            year = match.group(2)
            if surname and year:
                mentions.append(
                    CitationMention(
                        mention_id=f"C{counter}",
                        paragraph_id=sentence.paragraph_id,
                        sentence_id=sentence.sentence_id,
                        raw_text=match.group(0),
                        citation_keys=[f"{surname.lower()}-{year}"],
                        start=match.start(),
                        end=match.end(),
                    )
                )
                counter += 1
    return mentions


def sentence_citation_keys(sentence_id: str, mentions: List[CitationMention]) -> List[str]:
    keys: List[str] = []
    for mention in mentions:
        if mention.sentence_id == sentence_id:
            for key in mention.citation_keys:
                if key not in keys:
                    keys.append(key)
    return keys


def paragraph_citation_keys(paragraph_id: str, mentions: List[CitationMention]) -> List[str]:
    keys: List[str] = []
    for mention in mentions:
        if mention.paragraph_id == paragraph_id:
            for key in mention.citation_keys:
                if key not in keys:
                    keys.append(key)
    return keys


def _parse_numeric_keys(text: str) -> List[str]:
    keys: List[str] = []
    for part in re.split(r"[,;]\s*", text.strip()):
        if "-" in part:
            start, end = [p.strip() for p in part.split("-", 1)]
            if start.isdigit() and end.isdigit():
                for value in range(int(start), int(end) + 1):
                    keys.append(str(value))
            continue
        if part.strip().isdigit():
            keys.append(part.strip())
    return keys


def _parse_author_year_parenthetical(text: str) -> List[str]:
    keys: List[str] = []
    for chunk in re.split(r";", text):
        year_match = YEAR_RE.search(chunk)
        if not year_match:
            continue
        year = year_match.group(1)
        author_part = chunk[: year_match.start()].strip(" ,")
        if not author_part:
            continue
        first_author = re.split(r",| and |&", author_part)[0].strip()
        surname = author_surname(first_author)
        if surname:
            keys.append(f"{surname.lower()}-{year}")
    return keys


def _parse_bibtex_keys(text: str) -> List[str]:
    keys: List[str] = []
    for chunk in re.split(r"[,;]\s*", text.strip()):
        key = chunk.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _parse_bracket_keys(text: str) -> List[str]:
    return _parse_bibtex_keys(text)

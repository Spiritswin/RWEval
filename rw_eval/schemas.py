"""Dataclasses used by the related work evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


@dataclass
class Paragraph:
    paragraph_id: str
    text: str


@dataclass
class Sentence:
    sentence_id: str
    paragraph_id: str
    text: str


@dataclass
class CitationMention:
    mention_id: str
    paragraph_id: str
    sentence_id: str
    raw_text: str
    citation_keys: List[str]
    start: int = -1
    end: int = -1


@dataclass
class ReferenceEntry:
    ref_id: str
    raw_text: str
    label: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    author_year_key: Optional[str] = None
    normalized_key: Optional[str] = None
    s2_paper_id: Optional[str] = None
    s2_metadata: Dict[str, Any] = field(default_factory=dict)
    validity: str = "unknown"
    match_score: float = 0.0
    issues: List[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    text: str
    references_text: str
    paragraphs: List[Paragraph]
    sentences: List[Sentence]
    citation_mentions: List[CitationMention]
    references: List[ReferenceEntry]


@dataclass
class MetricResult:
    name: str
    score: float
    details: Dict[str, Any] = field(default_factory=dict)


def to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_plain(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    return obj

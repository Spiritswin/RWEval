"""Text segmentation."""

from __future__ import annotations

import re
from typing import List

from rw_eval.schemas import Paragraph, Sentence


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


def split_paragraphs(text: str, prefix: str) -> List[Paragraph]:
    raw = (text or "").strip()
    if not raw:
        return []
    chunks = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if not chunks:
        chunks = [raw]
    return [Paragraph(paragraph_id=f"{prefix}{i + 1}", text=p) for i, p in enumerate(chunks)]


def split_sentences(paragraphs: List[Paragraph]) -> List[Sentence]:
    sentences: List[Sentence] = []
    for paragraph in paragraphs:
        pieces = [s.strip() for s in SENTENCE_SPLIT_RE.split(paragraph.text) if s.strip()]
        if not pieces and paragraph.text.strip():
            pieces = [paragraph.text.strip()]
        for i, sentence in enumerate(pieces):
            sentences.append(
                Sentence(
                    sentence_id=f"{paragraph.paragraph_id}_sent{i + 1}",
                    paragraph_id=paragraph.paragraph_id,
                    text=sentence,
                )
            )
    return sentences

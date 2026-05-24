"""Length and conciseness scoring."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List

from rw_eval.scoring.common import average, metric
from rw_eval.schemas import ParsedDocument
from rw_eval.utils import WORD_RE, clamp, text_similarity


def score_length_conciseness(
    s_doc: ParsedDocument,
    g_doc: ParsedDocument,
    content_coverage_score: float,
    relevance_score: float,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    thresholds = config.get("thresholds", {})
    s_word_count = _word_count(s_doc.text)
    g_word_count = _word_count(g_doc.text)
    ratio = s_word_count / g_word_count if g_word_count else 0.0

    relative_length_score = _relative_length_score(ratio, thresholds)
    information_density_score = _information_density_score(ratio, content_coverage_score, relevance_score)
    redundancy_score, redundancy_details = _redundancy_score(s_doc, thresholds)

    score = (
        0.50 * relative_length_score
        + 0.30 * information_density_score
        + 0.20 * redundancy_score
    )

    return metric(
        "length_conciseness",
        score,
        {
            "s_word_count": s_word_count,
            "g_word_count": g_word_count,
            "length_ratio": ratio,
            "sub_scores": {
                "relative_length_score": relative_length_score,
                "information_density_score": information_density_score,
                "redundancy_score": redundancy_score,
            },
            "redundancy": redundancy_details,
        },
    )


def _word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def _relative_length_score(ratio: float, thresholds: Dict[str, Any]) -> float:
    if ratio <= 0:
        return 0.0
    no_min = float(thresholds.get("length_ratio_no_penalty_min", 0.75))
    no_max = float(thresholds.get("length_ratio_no_penalty_max", 1.35))
    light_min = float(thresholds.get("length_ratio_light_min", 0.50))
    light_max = float(thresholds.get("length_ratio_light_max", 1.75))
    moderate_min = float(thresholds.get("length_ratio_moderate_min", 0.30))
    moderate_max = float(thresholds.get("length_ratio_moderate_max", 2.50))

    if no_min <= ratio <= no_max:
        return 10.0
    if light_min <= ratio < no_min:
        return _interp(ratio, light_min, no_min, 7.0, 10.0)
    if no_max < ratio <= light_max:
        return _interp(ratio, no_max, light_max, 10.0, 7.0)
    if moderate_min <= ratio < light_min:
        return _interp(ratio, moderate_min, light_min, 4.0, 7.0)
    if light_max < ratio <= moderate_max:
        return _interp(ratio, light_max, moderate_max, 7.0, 4.0)
    return 2.0


def _information_density_score(ratio: float, coverage: float, relevance: float) -> float:
    if ratio <= 0:
        return 0.0
    base_quality = 0.65 * clamp(coverage) + 0.35 * clamp(relevance)
    if 0.75 <= ratio <= 1.35:
        return base_quality
    if ratio > 1.35:
        excess = min(ratio / 1.35, 3.0)
        return clamp(base_quality / excess + 2.0 * (1.0 - 1.0 / excess))
    shortfall = min(0.75 / ratio, 3.0)
    return clamp(base_quality / shortfall + 1.0 * (1.0 - 1.0 / shortfall))


def _redundancy_score(s_doc: ParsedDocument, thresholds: Dict[str, Any]) -> Any:
    threshold = float(thresholds.get("redundancy_similarity_threshold", 0.82))
    sentence_pairs = []
    similarities: List[float] = []
    for a, b in combinations(s_doc.sentences, 2):
        sim = text_similarity(a.text, b.text)
        similarities.append(sim)
        if sim >= threshold:
            sentence_pairs.append(
                {
                    "sentence_a": a.sentence_id,
                    "sentence_b": b.sentence_id,
                    "similarity": sim,
                    "text_a": a.text,
                    "text_b": b.text,
                }
            )

    paragraph_pairs = []
    for a, b in combinations(s_doc.paragraphs, 2):
        sim = text_similarity(a.text, b.text)
        if sim >= threshold:
            paragraph_pairs.append(
                {
                    "paragraph_a": a.paragraph_id,
                    "paragraph_b": b.paragraph_id,
                    "similarity": sim,
                }
            )

    duplicate_penalty = min(8.0, len(sentence_pairs) * 1.5 + len(paragraph_pairs) * 2.0)
    avg_similarity = average(similarities, default=0.0)
    diffuse_penalty = 1.5 if avg_similarity >= 0.45 and len(s_doc.sentences) >= 4 else 0.0
    score = clamp(10.0 - duplicate_penalty - diffuse_penalty)
    return score, {
        "duplicate_sentence_pairs": sentence_pairs,
        "duplicate_paragraph_pairs": paragraph_pairs,
        "average_sentence_similarity": avg_similarity,
        "duplicate_penalty": duplicate_penalty,
        "diffuse_repetition_penalty": diffuse_penalty,
    }


def _interp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y1
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)

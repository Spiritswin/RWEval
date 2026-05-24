import unittest

from rw_eval.scoring.aggregate import aggregate_scores
from rw_eval.scoring.citation import score_citation_quality
from rw_eval.scoring.coverage import score_content_coverage
from rw_eval.scoring.relevance import score_relevance


class ScoringTests(unittest.TestCase):
    def test_coverage_weighted(self):
        gold = {
            "key_points": [
                {"id": "G1", "importance": 3, "text": "A"},
                {"id": "G2", "importance": 1, "text": "B"},
            ]
        }
        alignment = {
            "alignments": [
                {"gold_point_id": "G1", "match_score": 1.0, "status": "complete"},
                {"gold_point_id": "G2", "match_score": 0.5, "status": "partial"},
            ]
        }
        self.assertEqual(score_content_coverage(gold, alignment)["score"], 8.75)

    def test_relevance(self):
        judgment = {"claim_judgments": [{"relevance_score": 1.0}, {"relevance_score": 0.5}]}
        self.assertEqual(score_relevance(judgment)["score"], 7.5)

    def test_aggregate_exposes_citation_subscores_in_front_scores(self):
        metric_results = {
            "content_coverage": {"score": 6.0, "details": {}},
            "citation_quality": {
                "score": 7.0,
                "details": {
                    "sub_scores": {
                        "citation_validity": 8.0,
                        "citation_appropriateness": 7.5,
                        "citation_coverage": 6.5,
                        "citation_placement": 6.0,
                        "citation_topic_consistency": 7.0,
                    }
                },
            },
            "relevance": {"score": 5.0, "details": {}},
        }
        config = {
            "metric_weights": {
                "content_coverage": 0.4,
                "citation_quality": 0.4,
                "relevance": 0.2,
            }
        }
        scores = aggregate_scores(metric_results, config)["scores"]
        self.assertEqual(list(scores.keys())[:2], ["content_coverage", "citation_quality"])
        self.assertEqual(scores["citation_validity"], 8.0)

    def test_citation_overclaim_pairs_only_collect_yes_or_partial_support(self):
        result = score_citation_quality(
            s_references=[],
            g_references=[],
            gold={},
            citation_judgment={
                "citation_judgments": [
                    {
                        "claim_id": "S1",
                        "reference_key": "ref-1",
                        "support": "yes",
                        "appropriateness_score": 9.0,
                        "placement_score": 9.0,
                        "topic_consistency_score": 9.0,
                        "overclaim_status": "moderate",
                        "overclaim_rationale": "Adds stronger causal wording than the citation supports.",
                    },
                    {
                        "claim_id": "S2",
                        "reference_key": "ref-2",
                        "support": "weak",
                        "appropriateness_score": 4.0,
                        "placement_score": 4.0,
                        "topic_consistency_score": 4.0,
                        "overclaim_status": "severe",
                        "overclaim_rationale": "Should be ignored because support is weak.",
                    },
                ]
            },
            config={"citation_weights": {}},
        )
        overclaim_pairs = result["details"]["overclaim_citation_claim_pairs"]
        self.assertEqual(len(overclaim_pairs), 1)
        self.assertEqual(overclaim_pairs[0]["claim_id"], "S1")


if __name__ == "__main__":
    unittest.main()

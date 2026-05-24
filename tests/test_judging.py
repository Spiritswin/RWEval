import unittest

from rw_eval.llm.judging import Judger
from rw_eval.schemas import ReferenceEntry


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def is_configured(self):
        return True

    def chat_json(self, system, user, temperature=0.0, max_retries=None):
        if not self.responses:
            raise AssertionError("No fake LLM responses left")
        return self.responses.pop(0)


class FakeRetriever:
    def retrieve_claim_evidence(self, ref, claim_text):
        return {
            "query": f"{ref.title} :: {claim_text}",
            "snippets": [
                {
                    "source": "fake_source",
                    "citation": ref.normalized_key or ref.ref_id,
                    "text": f"Evidence for {ref.title}",
                }
            ],
            "paper_metadata": {"title": ref.title},
            "errors": [],
        }


class JudgingTests(unittest.TestCase):
    def test_citation_judging_completes_missing_pairs_with_second_pass(self):
        llm = FakeLLM(
            [
                {
                    "citation_judgments": [
                        {
                            "claim_id": "SClaim1",
                            "reference_key": "ref-b",
                            "support": "weak",
                            "appropriateness_score": 4.0,
                            "placement_score": 5.0,
                            "topic_consistency_score": 4.0,
                            "support_rationale": "Initial weak judgment.",
                            "overclaim_status": "none",
                            "overclaim_rationale": "",
                        }
                    ]
                },
                {
                    "citation_judgment": {
                        "claim_id": "SClaim1",
                        "reference_key": "ref-a",
                        "support": "yes",
                        "appropriateness_score": 8.0,
                        "placement_score": 8.0,
                        "topic_consistency_score": 8.0,
                        "support_rationale": "Recovered in second pass.",
                        "overclaim_status": "none",
                        "overclaim_rationale": "",
                    }
                },
                {
                    "citation_judgment": {
                        "claim_id": "SClaim1",
                        "reference_key": "ref-b",
                        "support": "no",
                        "appropriateness_score": 2.0,
                        "placement_score": 3.0,
                        "topic_consistency_score": 2.0,
                        "support_rationale": "Confirmed unsupported in second pass.",
                        "overclaim_status": "none",
                        "overclaim_rationale": "",
                    }
                },
                {
                    "citation_group_judgment": {
                        "claim_id": "SClaim1",
                        "citation_count": 2,
                        "group_support": "partial",
                        "group_rationale": "One citation supports a component but the other does not support the full composite claim.",
                        "covered_aspects": ["component support"],
                        "missing_aspects": ["full composite support"],
                    }
                },
            ]
        )
        judger = Judger(llm)
        candidate = {
            "claims": [
                {
                    "id": "SClaim1",
                    "text": "Composite claim.",
                    "paragraph_id": "S1",
                    "citations": ["ref-a", "ref-b"],
                }
            ]
        }
        metadata = {
            "ref-a": {"title": "Paper A", "abstract": "Abstract A"},
            "ref-b": {"title": "Paper B", "abstract": "Abstract B"},
        }
        reference_lookup = {
            "ref-a": ReferenceEntry(ref_id="R1", raw_text="Paper A", title="Paper A", normalized_key="ref-a"),
            "ref-b": ReferenceEntry(ref_id="R2", raw_text="Paper B", title="Paper B", normalized_key="ref-b"),
        }

        result = judger.judge_citation_appropriateness(
            candidate,
            metadata,
            reference_lookup=reference_lookup,
            evidence_retriever=FakeRetriever(),
        )
        judgments = result["citation_judgments"]
        self.assertEqual(len(judgments), 2)
        by_key = {(item["claim_id"], item["reference_key"]): item for item in judgments}
        self.assertEqual(by_key[("SClaim1", "ref-a")]["support"], "yes")
        self.assertEqual(by_key[("SClaim1", "ref-b")]["support"], "no")
        self.assertTrue(by_key[("SClaim1", "ref-a")]["second_pass_used"])
        self.assertTrue(by_key[("SClaim1", "ref-a")]["retrieval_used"])
        self.assertEqual(len(result["retrieval_events"]), 2)
        self.assertEqual(result["citation_group_judgments"][0]["group_support"], "partial")

    def test_missing_pair_without_second_pass_result_becomes_unknown(self):
        llm = FakeLLM([{"citation_judgments": []}, {"citation_judgment": {}}])
        judger = Judger(llm)
        candidate = {"claims": [{"id": "SClaim1", "text": "Claim.", "paragraph_id": "S1", "citations": ["ref-a"]}]}
        metadata = {"ref-a": {"title": "Paper A"}}
        reference_lookup = {"ref-a": ReferenceEntry(ref_id="R1", raw_text="Paper A", title="Paper A", normalized_key="ref-a")}

        result = judger.judge_citation_appropriateness(candidate, metadata, reference_lookup=reference_lookup, evidence_retriever=None)
        judgment = result["citation_judgments"][0]
        self.assertEqual(judgment["support"], "unknown")
        self.assertIn("No citation judgment was returned", judgment["support_rationale"])
        self.assertEqual(result["citation_group_judgments"][0]["group_support"], "unknown")
        self.assertTrue(result["citation_group_judgments"][0]["derived_from_single_pair"])


if __name__ == "__main__":
    unittest.main()

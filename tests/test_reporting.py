import unittest

from rw_eval.reporting.markdown_report import render_markdown_report


class ReportingTests(unittest.TestCase):
    def test_citation_pair_sections_include_reasons(self):
        report = {
            "sample_id": "unit",
            "overall": 7.0,
            "scores": {"content_coverage": 7.0},
            "cleaning": [],
            "diagnostics": {
                "bad_citation_claim_pairs": [
                    {
                        "claim_id": "SClaim1",
                        "reference_key": "ref-1",
                        "support": "weak",
                        "support_rationale": "The cited paper is only loosely related to the claim.",
                        "overclaim_status": "none",
                        "overclaim_rationale": "",
                    }
                ],
                "overclaim_citation_claim_pairs": [
                    {
                        "claim_id": "SClaim2",
                        "reference_key": "ref-2",
                        "support": "partial",
                        "support_rationale": "The citation supports the task setup but not the performance claim.",
                        "overclaim_status": "moderate",
                        "overclaim_rationale": "The wording exaggerates the strength of the empirical finding.",
                    }
                ],
                "citation_group_support": [
                    {
                        "claim_id": "SClaim2",
                        "citation_count": 2,
                        "group_support": "partial",
                        "group_rationale": "Together the citations support the setup but not the integrated system claim.",
                        "covered_aspects": ["method exists", "model exists"],
                        "missing_aspects": ["integration into the proposed system"],
                        "derived_from_single_pair": False,
                    }
                ],
            },
        }

        rendered = render_markdown_report(report)
        self.assertIn("support_reason=The cited paper is only loosely related to the claim.", rendered)
        self.assertIn("support_reason=The citation supports the task setup but not the performance claim.", rendered)
        self.assertIn("overclaim_reason=The wording exaggerates the strength of the empirical finding.", rendered)
        self.assertIn("group_support=partial", rendered)
        self.assertIn("missing=['integration into the proposed system']", rendered)

    def test_empty_group_support_section_renders_none(self):
        report = {
            "sample_id": "unit",
            "overall": 7.0,
            "scores": {"content_coverage": 7.0},
            "cleaning": [],
            "diagnostics": {
                "citation_group_support": [],
            },
        }

        rendered = render_markdown_report(report)
        self.assertIn("## Citation Group Support", rendered)
        self.assertIn("## Citation Group Support\n- None", rendered)


if __name__ == "__main__":
    unittest.main()

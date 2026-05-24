import unittest

from rw_eval.pipeline import parse_document
from rw_eval.scoring.length import score_length_conciseness


class LengthScoringTests(unittest.TestCase):
    def test_balanced_length_scores_high(self):
        s_doc = parse_document("A method improves alignment. It reduces reward modeling.", "", "S")
        g_doc = parse_document("A method improves alignment. It reduces reward modeling.", "", "G")
        result = score_length_conciseness(s_doc, g_doc, 8.0, 8.0, {"thresholds": {}})
        self.assertGreaterEqual(result["score"], 8.0)

    def test_too_long_penalized(self):
        s_doc = parse_document("A method improves alignment. " * 20, "", "S")
        g_doc = parse_document("A method improves alignment.", "", "G")
        result = score_length_conciseness(s_doc, g_doc, 4.0, 4.0, {"thresholds": {}})
        self.assertLess(result["score"], 7.0)


if __name__ == "__main__":
    unittest.main()

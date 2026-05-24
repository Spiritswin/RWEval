import unittest

from rw_eval.cleaning import clean_sample, clean_text


class CleaningTests(unittest.TestCase):
    def test_mojibake_replacement(self):
        cleaned, report = clean_text("feasibility\u0101\u20ac\u201dhighlighting 340\u0106\u2014", "s_text")
        self.assertIn("feasibility-highlighting", cleaned)
        self.assertIn("340x", cleaned)
        self.assertTrue(report.changed)

    def test_sample_cleaning(self):
        sample, reports = clean_sample(
            {
                "s_text": "A \\& B",
                "s_references": "",
                "g_text": "G",
                "g_references": "",
            }
        )
        self.assertEqual(sample["s_text"], "A & B")
        self.assertEqual(len(reports), 4)

    def test_ai_regex_does_not_touch_words(self):
        unchanged, _ = clean_text("Al-assisted AI, Alice and Alpha remain.", "g_text")
        self.assertIn("Al-assisted", unchanged)
        cleaned, _ = clean_text("Al-assisted AI, Alice and Alpha remain.", "g_text", normalize_ai_typos=True)
        self.assertIn("AI-assisted", cleaned)
        self.assertIn("Alice", cleaned)
        self.assertIn("Alpha", cleaned)


if __name__ == "__main__":
    unittest.main()

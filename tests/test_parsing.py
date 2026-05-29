import unittest

from rw_eval.parsing.citations import extract_citation_mentions
from rw_eval.parsing.references import build_reference_lookup, parse_references
from rw_eval.parsing.text import split_paragraphs, split_sentences


class ParsingTests(unittest.TestCase):
    def test_author_year_citation(self):
        paragraphs = split_paragraphs("DPO is widely used (Rafailov et al., 2023).", "S")
        sentences = split_sentences(paragraphs)
        mentions = extract_citation_mentions(sentences)
        self.assertEqual(mentions[0].citation_keys, ["rafailov-2023"])

    def test_numeric_citation_range(self):
        paragraphs = split_paragraphs("Several methods exist [1, 3-4].", "S")
        mentions = extract_citation_mentions(split_sentences(paragraphs))
        self.assertEqual(mentions[0].citation_keys, ["1", "3", "4"])

    def test_bracket_string_citation_key(self):
        paragraphs = split_paragraphs("DPO variants are widely used [dpo].", "S")
        mentions = extract_citation_mentions(split_sentences(paragraphs))
        self.assertEqual(mentions[0].citation_keys, ["dpo"])

    def test_bracket_string_citation_multiple_keys(self):
        paragraphs = split_paragraphs("DPO variants are widely used [dpo, step_dpo].", "S")
        mentions = extract_citation_mentions(split_sentences(paragraphs))
        self.assertEqual(mentions[0].citation_keys, ["dpo", "step_dpo"])

    def test_bibtex_citation_single_key(self):
        paragraphs = split_paragraphs(r"Recent work uses retrieval \cite{yang2023hypothesis}.", "S")
        mentions = extract_citation_mentions(split_sentences(paragraphs))
        self.assertEqual(mentions[0].citation_keys, ["yang2023hypothesis"])

    def test_bibtex_citation_multiple_keys(self):
        paragraphs = split_paragraphs(r"Related efforts include \citep{baek2024researchagent,wang2024autosurvey}.", "S")
        mentions = extract_citation_mentions(split_sentences(paragraphs))
        self.assertEqual(mentions[0].citation_keys, ["baek2024researchagent", "wang2024autosurvey"])

    def test_reference_parse(self):
        refs = parse_references("Rafailov, R. (2023). Direct Preference Optimization. NeurIPS.")
        self.assertEqual(refs[0].year, 2023)
        self.assertIn("Direct Preference Optimization", refs[0].title)

    def test_bracket_string_reference_label(self):
        refs = parse_references("[dpo] Rafailov, R. (2023). Direct Preference Optimization. NeurIPS.")
        lookup = build_reference_lookup(refs)
        self.assertEqual(refs[0].label, "dpo")
        self.assertIs(lookup["dpo"], refs[0])


if __name__ == "__main__":
    unittest.main()

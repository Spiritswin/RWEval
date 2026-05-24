import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rw_eval import cli
from rw_eval.input_files import sample_from_directory, write_sample_json


class InputFilesTests(unittest.TestCase):
    def test_sample_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "s_text.txt").write_text("s", encoding="utf-8")
            (root / "s_reference.txt").write_text("sr", encoding="utf-8")
            (root / "g_text.txt").write_text("g", encoding="utf-8")
            (root / "g_reference.txt").write_text("gr", encoding="utf-8")
            sample = sample_from_directory(str(root), sample_id="x")
        self.assertEqual(sample["sample_id"], "x")
        self.assertEqual(sample["s_references"], "sr")
        self.assertEqual(sample["g_text"], "g")

    def test_write_sample_json_keeps_txt_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "s_text.txt").write_text("s", encoding="utf-8")
            (root / "s_reference.txt").write_text("sr", encoding="utf-8")
            (root / "g_text.txt").write_text("g", encoding="utf-8")
            (root / "g_reference.txt").write_text("gr", encoding="utf-8")
            output = root / "sample.json"
            sample = write_sample_json(
                str(output),
                str(root / "s_text.txt"),
                str(root / "s_reference.txt"),
                str(root / "g_text.txt"),
                str(root / "g_reference.txt"),
                sample_id="pkg",
            )
            written = output.read_text(encoding="utf-8")
        self.assertEqual(sample["sample_id"], "pkg")
        self.assertIn('"sample_id": "pkg"', written)

    def test_resolve_sample_json_output_defaults_to_directory(self):
        args = SimpleNamespace(sample_json_output=None, output="outputs/report.json")
        path = cli._resolve_sample_json_output(args, directory=Path("examples/sample2"))
        self.assertEqual(path, Path("examples/sample2") / "sample_input.json")

    def test_resolve_sample_json_output_defaults_to_shared_parent_for_explicit_files(self):
        args = SimpleNamespace(sample_json_output=None, output="outputs/report.json")
        files = [
            Path("examples/sample2/s_text.txt"),
            Path("examples/sample2/s_reference.txt"),
            Path("examples/sample2/g_text.txt"),
            Path("examples/sample2/g_reference.txt"),
        ]
        path = cli._resolve_sample_json_output(args, file_paths=files)
        self.assertEqual(path.name, "sample_input.json")
        self.assertEqual(path.parent.name, "sample2")

    def test_evaluate_files_writes_sample_json_before_evaluating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "s_text.txt").write_text("s", encoding="utf-8")
            (root / "s_reference.txt").write_text("sr", encoding="utf-8")
            (root / "g_text.txt").write_text("g", encoding="utf-8")
            (root / "g_reference.txt").write_text("gr", encoding="utf-8")
            report_output = root / "report.json"
            sample_json_output = root / "sample_input.json"
            args = SimpleNamespace(
                directory=str(root),
                s_text=None,
                s_references=None,
                g_text=None,
                g_references=None,
                sample_id="pkg",
                sample_json_output=str(sample_json_output),
                output=str(report_output),
                markdown_output=None,
                config="configs/rubric.json",
                env=".env",
                no_llm=False,
                strict_llm=False,
                no_semantic_scholar=True,
                no_clean=False,
                normalize_ai_typos=False,
            )
            seen = {}

            def fake_evaluate(sample, **kwargs):
                seen["sample"] = sample
                return {"sample_id": sample["sample_id"], "overall": 7.0, "scores": {}, "diagnostics": {}, "cleaning": []}

            with patch("rw_eval.cli.evaluate_sample", side_effect=fake_evaluate):
                exit_code = cli._evaluate_files(args)

            self.assertEqual(exit_code, 0)
            self.assertTrue(sample_json_output.exists())
            self.assertEqual(seen["sample"]["sample_id"], "pkg")
            self.assertEqual(seen["sample"]["s_text"], "s")
            self.assertTrue(report_output.exists())


if __name__ == "__main__":
    unittest.main()

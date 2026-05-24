"""Command-line interface for related work evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

from rw_eval.input_files import write_sample_json
from rw_eval.pipeline import evaluate_sample
from rw_eval.reporting.json_report import write_json_report
from rw_eval.reporting.markdown_report import write_markdown_report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate candidate related work against a ground truth related work.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a single JSON sample.")
    eval_parser.add_argument("--input", required=True, help="Input sample JSON.")
    eval_parser.add_argument("--output", required=False, help="Output report JSON.")
    eval_parser.add_argument("--markdown-output", required=False, help="Optional Markdown report path.")
    eval_parser.add_argument("--config", default="configs/rubric.json", help="Rubric config JSON.")
    eval_parser.add_argument("--env", default=".env", help=".env path.")
    eval_parser.add_argument("--no-llm", action="store_true", help="Disable LLM calls. Heuristic mode has been removed, so evaluation will fail.")
    eval_parser.add_argument("--strict-llm", action="store_true", help="Deprecated. LLM failures now fail the evaluation directly.")
    eval_parser.add_argument("--no-semantic-scholar", action="store_true", help="Disable Semantic Scholar calls.")
    eval_parser.add_argument("--no-clean", action="store_true", help="Disable conservative input text cleaning.")
    eval_parser.add_argument("--normalize-ai-typos", action="store_true", help="Optionally normalize AI/Al OCR typos such as Al-assisted -> AI-assisted.")

    batch_parser = subparsers.add_parser("batch", help="Evaluate a JSONL file.")
    batch_parser.add_argument("--input", required=True, help="Input JSONL.")
    batch_parser.add_argument("--output", required=True, help="Output report JSONL.")
    batch_parser.add_argument("--config", default="configs/rubric.json", help="Rubric config JSON.")
    batch_parser.add_argument("--env", default=".env", help=".env path.")
    batch_parser.add_argument("--no-llm", action="store_true", help="Disable LLM calls. Heuristic mode has been removed, so evaluation will fail.")
    batch_parser.add_argument("--strict-llm", action="store_true", help="Deprecated. LLM failures now fail the evaluation directly.")
    batch_parser.add_argument("--no-semantic-scholar", action="store_true", help="Disable Semantic Scholar calls.")
    batch_parser.add_argument("--no-clean", action="store_true", help="Disable conservative input text cleaning.")
    batch_parser.add_argument("--normalize-ai-typos", action="store_true", help="Optionally normalize AI/Al OCR typos such as Al-assisted -> AI-assisted.")

    files_parser = subparsers.add_parser(
        "evaluate-files",
        help="Read four txt files, write sample_input.json, then evaluate that JSON.",
    )
    files_parser.add_argument("--directory", default=None, help="Directory containing s_text.txt, s_reference.txt, g_text.txt, g_reference.txt.")
    files_parser.add_argument("--s-text", default=None, help="Candidate related work txt path.")
    files_parser.add_argument("--s-references", default=None, help="Candidate references txt path.")
    files_parser.add_argument("--g-text", default=None, help="Ground-truth related work txt path.")
    files_parser.add_argument("--g-references", default=None, help="Ground-truth references txt path.")
    files_parser.add_argument("--sample-id", default=None, help="Optional sample id.")
    files_parser.add_argument(
        "--sample-json-output",
        default=None,
        help="Optional path for the generated sample JSON. Defaults to sample_input.json next to the txt inputs when possible.",
    )
    files_parser.add_argument("--output", required=False, help="Output report JSON.")
    files_parser.add_argument("--markdown-output", required=False, help="Optional Markdown report path.")
    files_parser.add_argument("--config", default="configs/rubric.json", help="Rubric config JSON.")
    files_parser.add_argument("--env", default=".env", help=".env path.")
    files_parser.add_argument("--no-llm", action="store_true", help="Disable LLM calls. Heuristic mode has been removed, so evaluation will fail.")
    files_parser.add_argument("--strict-llm", action="store_true", help="Deprecated. LLM failures now fail the evaluation directly.")
    files_parser.add_argument("--no-semantic-scholar", action="store_true", help="Disable Semantic Scholar calls.")
    files_parser.add_argument("--no-clean", action="store_true", help="Disable conservative input text cleaning.")
    files_parser.add_argument("--normalize-ai-typos", action="store_true", help="Optionally normalize AI/Al OCR typos such as Al-assisted -> AI-assisted.")

    package_parser = subparsers.add_parser("package-sample", help="Package separate txt inputs into a single JSON sample.")
    package_parser.add_argument("--directory", default=None, help="Directory containing s_text.txt, s_reference.txt, g_text.txt, g_reference.txt.")
    package_parser.add_argument("--s-text", default=None, help="Candidate related work txt path.")
    package_parser.add_argument("--s-references", default=None, help="Candidate references txt path.")
    package_parser.add_argument("--g-text", default=None, help="Ground-truth related work txt path.")
    package_parser.add_argument("--g-references", default=None, help="Ground-truth references txt path.")
    package_parser.add_argument("--sample-id", default=None, help="Optional sample id.")
    package_parser.add_argument("--output", required=True, help="Output sample JSON.")

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "batch":
        return _batch(args)
    if args.command == "evaluate-files":
        return _evaluate_files(args)
    if args.command == "package-sample":
        return _package_sample(args)
    parser.error("Unknown command")
    return 2


def _evaluate(args: argparse.Namespace) -> int:
    sample = _read_json(args.input)
    report = evaluate_sample(
        sample,
        config_path=args.config,
        env_path=args.env,
        use_semantic_scholar=not args.no_semantic_scholar,
        use_llm=not args.no_llm,
        strict_llm=args.strict_llm,
        clean_input=not args.no_clean,
        normalize_ai_typos=args.normalize_ai_typos,
    )
    if args.output:
        write_json_report(report, args.output)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if args.markdown_output:
        write_markdown_report(report, args.markdown_output)
    return 0


def _batch(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as f_in, output_path.open("w", encoding="utf-8") as f_out:
        for line_number, line in enumerate(f_in, start=1):
            if not line.strip():
                continue
            sample = json.loads(line)
            try:
                report = evaluate_sample(
                    sample,
                    config_path=args.config,
                    env_path=args.env,
                    use_semantic_scholar=not args.no_semantic_scholar,
                    use_llm=not args.no_llm,
                    strict_llm=args.strict_llm,
                    clean_input=not args.no_clean,
                    normalize_ai_typos=args.normalize_ai_typos,
                )
            except Exception as exc:
                report = {"sample_id": sample.get("sample_id"), "error": str(exc), "line_number": line_number}
            f_out.write(json.dumps(report, ensure_ascii=False) + "\n")
    return 0


def _evaluate_files(args: argparse.Namespace) -> int:
    if args.directory:
        sample_json_output = _resolve_sample_json_output(args, directory=Path(args.directory))
        root = Path(args.directory)
        write_sample_json(
            str(sample_json_output),
            str(root / "s_text.txt"),
            str(root / "s_reference.txt"),
            str(root / "g_text.txt"),
            str(root / "g_reference.txt"),
            sample_id=args.sample_id or root.name,
        )
    else:
        required = [args.s_text, args.s_references, args.g_text, args.g_references]
        if any(value is None for value in required):
            raise SystemExit(
                "Either provide --directory or all of --s-text --s-references --g-text --g-references"
            )
        sample_json_output = _resolve_sample_json_output(
            args,
            file_paths=[
                Path(args.s_text),
                Path(args.s_references),
                Path(args.g_text),
                Path(args.g_references),
            ],
        )
        write_sample_json(
            str(sample_json_output),
            args.s_text,
            args.s_references,
            args.g_text,
            args.g_references,
            sample_id=args.sample_id,
        )

    report = evaluate_sample(
        _read_json(str(sample_json_output)),
        config_path=args.config,
        env_path=args.env,
        use_semantic_scholar=not args.no_semantic_scholar,
        use_llm=not args.no_llm,
        strict_llm=args.strict_llm,
        clean_input=not args.no_clean,
        normalize_ai_typos=args.normalize_ai_typos,
    )
    if args.output:
        write_json_report(report, args.output)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if args.markdown_output:
        write_markdown_report(report, args.markdown_output)
    return 0


def _package_sample(args: argparse.Namespace) -> int:
    if args.directory:
        root = Path(args.directory)
        sample = write_sample_json(
            args.output,
            str(root / "s_text.txt"),
            str(root / "s_reference.txt"),
            str(root / "g_text.txt"),
            str(root / "g_reference.txt"),
            sample_id=args.sample_id or root.name,
        )
    else:
        required = [args.s_text, args.s_references, args.g_text, args.g_references]
        if any(value is None for value in required):
            raise SystemExit(
                "Either provide --directory or all of --s-text --s-references --g-text --g-references"
            )
        sample = write_sample_json(
            args.output,
            args.s_text,
            args.s_references,
            args.g_text,
            args.g_references,
            sample_id=args.sample_id,
        )
    json.dump(sample, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def _read_json(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_sample_json_output(
    args: argparse.Namespace,
    *,
    directory: Path | None = None,
    file_paths: list[Path] | None = None,
) -> Path:
    if args.sample_json_output:
        return Path(args.sample_json_output)
    if directory is not None:
        return directory / "sample_input.json"
    if file_paths:
        parents = {path.resolve().parent for path in file_paths}
        if len(parents) == 1:
            return next(iter(parents)) / "sample_input.json"
    if args.output:
        output_path = Path(args.output)
        return output_path.parent / f"{output_path.stem}_sample_input.json"
    return Path("sample_input.json")


if __name__ == "__main__":
    raise SystemExit(main())

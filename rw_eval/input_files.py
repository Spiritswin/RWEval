"""Build evaluation samples from separate text/reference files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def sample_from_files(
    s_text_path: str,
    s_references_path: str,
    g_text_path: str,
    g_references_path: str,
    sample_id: str | None = None,
) -> Dict[str, Any]:
    s_text_file = Path(s_text_path)
    s_ref_file = Path(s_references_path)
    g_text_file = Path(g_text_path)
    g_ref_file = Path(g_references_path)
    return {
        "sample_id": sample_id or s_text_file.stem,
        "s_text": _read_text(s_text_file),
        "s_references": _read_text(s_ref_file),
        "g_text": _read_text(g_text_file),
        "g_references": _read_text(g_ref_file),
    }


def sample_from_directory(directory: str, sample_id: str | None = None) -> Dict[str, Any]:
    root = Path(directory)
    return sample_from_files(
        str(root / "s_text.txt"),
        str(root / "s_reference.txt"),
        str(root / "g_text.txt"),
        str(root / "g_reference.txt"),
        sample_id=sample_id or root.name,
    )


def write_sample_json(
    output_path: str,
    s_text_path: str,
    s_references_path: str,
    g_text_path: str,
    g_references_path: str,
    sample_id: str | None = None,
) -> Dict[str, Any]:
    sample = sample_from_files(
        s_text_path,
        s_references_path,
        g_text_path,
        g_references_path,
        sample_id=sample_id,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return sample


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path.read_text(encoding="utf-8-sig")

#!/usr/bin/env python3
"""Merge multiple benchmark dataset JSON files into one evaluator-ready JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Benchmark dataset must be a JSON list: {path}")
    return data


def _entry_key(entry: Dict[str, Any]) -> Tuple[str, str]:
    metadata = entry.get("metadata", {}) or {}
    input_data = entry.get("input", {}) or {}
    doi = str(metadata.get("doi") or "").strip().lower()
    title = str(input_data.get("title") or entry.get("title") or entry.get("id") or "").strip().casefold()
    return doi, " ".join(title.split())


def merge_datasets(paths: Iterable[Path]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    per_source = []
    duplicates = 0

    for path in paths:
        rows = _load_dataset(path)
        kept = 0
        skipped = 0
        for row in rows:
            key = _entry_key(row)
            if key != ("", "") and key in seen:
                duplicates += 1
                skipped += 1
                continue
            if key != ("", ""):
                seen.add(key)
            merged.append(row)
            kept += 1
        per_source.append(
            {
                "path": str(path),
                "input_records": len(rows),
                "kept_records": kept,
                "duplicate_records_skipped": skipped,
            }
        )

    summary = {
        "num_sources": len(per_source),
        "input_records": sum(item["input_records"] for item in per_source),
        "merged_records": len(merged),
        "duplicate_records_skipped": duplicates,
        "sources": per_source,
    }
    return merged, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True, help="Benchmark dataset JSON files to merge")
    parser.add_argument("--output", required=True, help="Merged benchmark dataset JSON")
    parser.add_argument("--summary", required=True, help="Merge summary JSON")
    args = parser.parse_args()

    paths = [Path(p) for p in args.inputs]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Missing input benchmark dataset: {path}")

    merged, summary = merge_datasets(paths)

    output = Path(args.output)
    summary_path = Path(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

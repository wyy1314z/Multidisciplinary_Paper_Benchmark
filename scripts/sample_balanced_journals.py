#!/usr/bin/env python3
"""Sample JSON/JSONL records with journal balance constraints."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.prepare_temporal_papers import select_balanced_by_journal

logger = logging.getLogger("sample_balanced_journals")


def _load_records(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def _write_records(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".jsonl":
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Journal-balanced sampling for JSON/JSONL records")
    parser.add_argument("--input", required=True, help="Input JSON or JSONL file")
    parser.add_argument("--output", required=True, help="Output JSON or JSONL file")
    parser.add_argument("--total", type=int, required=True, help="Target number of records")
    parser.add_argument("--min-per-journal", type=int, default=5, help="Minimum records per selected journal")
    parser.add_argument("--max-journals", type=int, default=None, help="Optional max selected journals")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--summary", default=None, help="Optional JSON summary output path")
    parser.add_argument("--strict", action="store_true", help="Fail if fewer than --total records are selected")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    rows = _load_records(Path(args.input))
    selected, summary = select_balanced_by_journal(
        rows,
        total=args.total,
        min_per_journal=args.min_per_journal,
        seed=args.seed,
        max_journals=args.max_journals,
    )
    if args.strict and len(selected) < args.total:
        raise SystemExit(
            f"Only selected {len(selected)} records, fewer than requested {args.total}. "
            f"See summary: {summary}"
        )

    _write_records(Path(args.output), selected)

    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info(
        "Selected %d/%d records across %d journals -> %s",
        len(selected),
        len(rows),
        summary["selected_journals"],
        args.output,
    )


if __name__ == "__main__":
    main()

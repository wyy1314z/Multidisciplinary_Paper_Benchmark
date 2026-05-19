#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _paper_id(item: Dict[str, Any]) -> str:
    title = item.get("title", "")
    return str(item.get("paper_id") or hashlib.md5(title.encode("utf-8")).hexdigest()[:12])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select papers from a query dataset according to paper_screening progress labels."
    )
    parser.add_argument("--screening", required=True, help="paper_screening_158_progress.json")
    parser.add_argument("--query-input", required=True, help="single_query_hypothesis_dataset_computer_158.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for selected subset")
    parser.add_argument("--status", default="selected", help="Screening status to keep (default: selected)")
    args = parser.parse_args()

    screening = _load_json(Path(args.screening))
    query_items = _load_json(Path(args.query_input))
    if not isinstance(screening, dict):
        raise SystemExit("screening JSON must be an object mapping paper_id -> status payload")
    if not isinstance(query_items, list):
        raise SystemExit("query-input must be a JSON list")

    selected_ids = [
        pid for pid, payload in screening.items()
        if isinstance(payload, dict) and str(payload.get("status", "")).strip() == args.status
    ]
    selected_id_set = set(selected_ids)

    subset = [item for item in query_items if _paper_id(item) in selected_id_set]
    found_ids = {_paper_id(item) for item in subset}
    missing = [pid for pid in selected_ids if pid not in found_ids]
    if missing:
        raise SystemExit(f"{len(missing)} screened papers were not found in query-input, sample={missing[:5]}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    subset_out = output_dir / "computer158_selected_query.json"
    manifest_out = output_dir / "computer158_selected_manifest.json"

    with subset_out.open("w", encoding="utf-8") as f:
        json.dump(subset, f, ensure_ascii=False, indent=2)

    manifest = {
        "screening": str(Path(args.screening)),
        "query_input": str(Path(args.query_input)),
        "status": args.status,
        "count": len(subset),
        "paper_ids": selected_ids,
        "papers": [
            {
                "paper_id": _paper_id(item),
                "title": item.get("title", ""),
                "journal": item.get("journal", ""),
                "doi": item.get("doi", ""),
                "primary_discipline": item.get("primary_discipline", ""),
            }
            for item in subset
        ],
    }
    with manifest_out.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Selected {len(subset)} papers with status='{args.status}' -> {output_dir}")
    print(f"Subset query: {subset_out}")
    print(f"Manifest:     {manifest_out}")


if __name__ == "__main__":
    main()

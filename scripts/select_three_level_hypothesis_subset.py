#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _paper_key(item: Dict[str, Any]) -> str:
    return str(item.get("doi") or item.get("title") or "").strip()


def _entry_is_ok(info: Dict[str, Any]) -> bool:
    text = str(info.get("text") or "").strip()
    return not info.get("error") and not text.startswith("[ERROR]")


def _all_models_all_levels_ok(item: Dict[str, Any]) -> bool:
    generated = item.get("generated_hypotheses", {}) or {}
    for level in ("L1", "L2", "L3"):
        model_map = generated.get(level, {}) or {}
        if not model_map:
            return False
        for info in model_map.values():
            if not _entry_is_ok(info or {}):
                return False
    return True


def _select_items(
    items: List[Dict[str, Any]],
    sample_size: int,
    strategy: str,
    seed: int,
) -> List[Dict[str, Any]]:
    if sample_size <= 0:
        raise ValueError("sample_size must be > 0")
    if sample_size > len(items):
        raise ValueError(f"sample_size={sample_size} > total_items={len(items)}")

    if strategy == "first":
        return items[:sample_size]

    rng = random.Random(seed)
    indices = sorted(rng.sample(range(len(items)), sample_size))
    return [items[i] for i in indices]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a reproducible subset of papers from the three-level computer158 hypothesis set."
    )
    parser.add_argument("--merged-input", required=True, help="Merged three-level hypotheses JSON")
    parser.add_argument("--query-input", required=True, help="single_query_hypothesis_dataset_computer_158.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for subset files")
    parser.add_argument("--sample-size", type=int, default=20, help="Number of papers to keep")
    parser.add_argument(
        "--strategy",
        choices=["first", "random"],
        default="random",
        help="Subset selection strategy (default: random)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed when strategy=random")
    parser.add_argument(
        "--require-all-models-ok",
        action="store_true",
        help="Keep only papers whose generated_hypotheses have no error entries for every model at L1/L2/L3.",
    )
    args = parser.parse_args()

    merged_items = _load_json(Path(args.merged_input))
    query_items = _load_json(Path(args.query_input))
    if not isinstance(merged_items, list) or not isinstance(query_items, list):
        raise SystemExit("Both inputs must be JSON lists.")

    eligible_items = merged_items
    if args.require_all_models_ok:
        eligible_items = [item for item in merged_items if _all_models_all_levels_ok(item)]
        if len(eligible_items) < args.sample_size:
            raise SystemExit(
                f"Only {len(eligible_items)} papers satisfy --require-all-models-ok, "
                f"which is smaller than sample-size={args.sample_size}."
            )

    selected_merged = _select_items(
        eligible_items,
        sample_size=args.sample_size,
        strategy=args.strategy,
        seed=args.seed,
    )

    selected_keys = {_paper_key(item) for item in selected_merged}
    query_index = {_paper_key(item): item for item in query_items}
    selected_query = [query_index[key] for key in (_paper_key(item) for item in selected_merged) if key in query_index]

    if len(selected_query) != len(selected_merged):
        missing = [
            _paper_key(item)
            for item in selected_merged
            if _paper_key(item) not in query_index
        ]
        raise SystemExit(f"Subset mismatch between merged/query inputs. Missing keys: {missing[:5]}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    merged_out = output_dir / "computer158_subset_merged.json"
    query_out = output_dir / "computer158_subset_query.json"
    manifest_out = output_dir / "computer158_subset_manifest.json"

    with merged_out.open("w", encoding="utf-8") as f:
        json.dump(selected_merged, f, ensure_ascii=False, indent=2)
    with query_out.open("w", encoding="utf-8") as f:
        json.dump(selected_query, f, ensure_ascii=False, indent=2)

    manifest = {
        "sample_size": len(selected_merged),
        "strategy": args.strategy,
        "seed": args.seed if args.strategy == "random" else None,
        "require_all_models_ok": args.require_all_models_ok,
        "eligible_pool_size": len(eligible_items),
        "papers": [
            {
                "index": item.get("index"),
                "title": item.get("title", ""),
                "doi": item.get("doi", ""),
                "journal": item.get("journal", ""),
                "primary_discipline": item.get("primary_discipline", ""),
            }
            for item in selected_merged
        ],
    }
    with manifest_out.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Selected {len(selected_merged)} papers -> {output_dir}")
    print(f"Merged subset: {merged_out}")
    print(f"Query subset:  {query_out}")
    print(f"Manifest:      {manifest_out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sample a fixed number of papers from each official journal-quality tier."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _tier_value(row: Dict[str, Any]) -> int | None:
    value = row.get("official_tier")
    try:
        return int(float(value))
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input JSONL with official_tier")
    parser.add_argument("--output", required=True, help="Output sampled JSONL")
    parser.add_argument("--summary", required=True, help="Output summary JSON")
    parser.add_argument("--tiers", nargs="+", type=int, default=[5, 4, 3, 2, 1])
    parser.add_argument("--per-tier", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--strict", action="store_true", help="Fail if any tier has fewer than --per-tier records")
    parser.add_argument(
        "--sort-by-crossdisc",
        action="store_true",
        help="Prefer records with higher crossdisc_score before random tie-breaking",
    )
    args = parser.parse_args()

    rows = _read_jsonl(Path(args.input))
    rng = random.Random(args.seed)
    by_tier: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        tier = _tier_value(row)
        if tier is not None:
            by_tier[tier].append(row)

    selected: List[Dict[str, Any]] = []
    tier_summary: Dict[str, Any] = {}
    for tier in args.tiers:
        candidates = list(by_tier.get(tier, []))
        if len(candidates) < args.per_tier and args.strict:
            raise SystemExit(f"Tier {tier} has {len(candidates)} records; need {args.per_tier}")

        rng.shuffle(candidates)
        if args.sort_by_crossdisc:
            candidates.sort(
                key=lambda row: (
                    _as_float(row.get("crossdisc_score")) is not None,
                    _as_float(row.get("crossdisc_score")) or -1.0,
                ),
                reverse=True,
            )
        picks = candidates[: args.per_tier]
        selected.extend(picks)
        tier_summary[str(tier)] = {
            "available_records": len(candidates),
            "selected_records": len(picks),
            "selected_journals": dict(Counter(str(row.get("journal", "")) for row in picks)),
            "selected_titles": [row.get("title", "") for row in picks],
            "crossdisc_score_min": min(
                [score for score in (_as_float(row.get("crossdisc_score")) for row in picks) if score is not None],
                default=None,
            ),
            "crossdisc_score_mean": (
                sum(scores) / len(scores)
                if (scores := [score for score in (_as_float(row.get("crossdisc_score")) for row in picks) if score is not None])
                else None
            ),
        }

    _write_jsonl(Path(args.output), selected)
    summary = {
        "input": args.input,
        "output": args.output,
        "total_input_records": len(rows),
        "total_selected_records": len(selected),
        "tiers": args.tiers,
        "per_tier": args.per_tier,
        "seed": args.seed,
        "strict": args.strict,
        "sort_by_crossdisc": args.sort_by_crossdisc,
        "selected_by_tier": dict(Counter(str(_tier_value(row)) for row in selected)),
        "tier_summary": tier_summary,
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

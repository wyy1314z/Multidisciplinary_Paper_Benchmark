#!/usr/bin/env python3
"""Summarize per-command timing logs produced by temporal pipeline scripts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _round(v: float) -> float:
    return round(float(v), 4)


def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_stage: Dict[str, Dict[str, Any]] = {}
    stage_rows = defaultdict(list)
    for row in rows:
        stage_rows[row.get("stage", "unknown")].append(row)

    for stage, items in sorted(stage_rows.items()):
        elapsed = sum(float(x.get("elapsed_sec", 0) or 0) for x in items)
        real = sum(float(x.get("real_sec", 0) or 0) for x in items)
        max_rss = max(int(x.get("max_rss_kb", 0) or 0) for x in items) if items else 0
        by_stage[stage] = {
            "num_commands": len(items),
            "elapsed_sec_sum": _round(elapsed),
            "real_sec_sum": _round(real),
            "max_rss_kb_max": max_rss,
            "commands": sorted(
                [
                    {
                        "command": x.get("command", ""),
                        "elapsed_sec": _round(float(x.get("elapsed_sec", 0) or 0)),
                        "real_sec": _round(float(x.get("real_sec", 0) or 0)),
                        "max_rss_kb": int(x.get("max_rss_kb", 0) or 0),
                        "exit_code": int(x.get("exit_code", 0) or 0),
                    }
                    for x in items
                ],
                key=lambda x: x["elapsed_sec"],
                reverse=True,
            ),
        }

    slowest = sorted(
        [
            {
                "stage": row.get("stage", "unknown"),
                "command": row.get("command", ""),
                "elapsed_sec": _round(float(row.get("elapsed_sec", 0) or 0)),
                "real_sec": _round(float(row.get("real_sec", 0) or 0)),
                "max_rss_kb": int(row.get("max_rss_kb", 0) or 0),
                "exit_code": int(row.get("exit_code", 0) or 0),
            }
            for row in rows
        ],
        key=lambda x: x["elapsed_sec"],
        reverse=True,
    )

    return {
        "num_records": len(rows),
        "by_stage": by_stage,
        "slowest_commands": slowest[:20],
    }


def render_markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Timing Summary", ""]
    lines.append(f"- `num_records`: {summary.get('num_records', 0)}")
    lines.append("")
    lines.append("## Stage Totals")
    for stage, info in summary.get("by_stage", {}).items():
        lines.append(
            f"- `{stage}`: commands={info['num_commands']}, elapsed={info['elapsed_sec_sum']}s, "
            f"real={info['real_sec_sum']}s, max_rss={info['max_rss_kb_max']}KB"
        )
    lines.append("")
    lines.append("## Slowest Commands")
    for item in summary.get("slowest_commands", []):
        lines.append(
            f"- `{item['stage']}` / `{item['command']}`: elapsed={item['elapsed_sec']}s, "
            f"real={item['real_sec']}s, max_rss={item['max_rss_kb']}KB, exit={item['exit_code']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize command timings for temporal benchmark runs")
    parser.add_argument("--input", required=True, help="Path to command_timings.jsonl")
    parser.add_argument("--output-json", required=True, help="Path to write JSON summary")
    parser.add_argument("--output-md", required=True, help="Path to write Markdown summary")
    args = parser.parse_args()

    rows = _load_jsonl(Path(args.input))
    summary = build_summary(rows)

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(summary), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nTiming JSON written to: {out_json}")
    print(f"Timing Markdown written to: {out_md}")


if __name__ == "__main__":
    main()

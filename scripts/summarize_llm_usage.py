#!/usr/bin/env python3
"""Summarize LLM usage telemetry produced by temporal pipeline runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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


def _sum_int(items: List[Dict[str, Any]], key: str) -> int:
    total = 0
    for item in items:
        try:
            total += int(item.get(key, 0) or 0)
        except Exception:
            continue
    return total


def _sum_float(items: List[Dict[str, Any]], key: str) -> float:
    total = 0.0
    for item in items:
        try:
            total += float(item.get(key, 0.0) or 0.0)
        except Exception:
            continue
    return total


def _aggregate(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "calls": len(items),
        "success_calls": sum(1 for x in items if x.get("success", True)),
        "error_calls": sum(1 for x in items if not x.get("success", True)),
        "prompt_tokens": _sum_int(items, "prompt_tokens"),
        "completion_tokens": _sum_int(items, "completion_tokens"),
        "total_tokens": _sum_int(items, "total_tokens"),
        "latency_sec_sum": round(_sum_float(items, "latency_sec"), 4),
        "usage_source_counts": dict(Counter(str(x.get("usage_source", "unknown")) for x in items)),
        "call_kind_counts": dict(Counter(str(x.get("call_kind", "unknown")) for x in items)),
        "models": dict(Counter(str(x.get("model", "")) for x in items if x.get("model"))),
    }


def build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_stage = defaultdict(list)
    by_command = defaultdict(list)
    for row in rows:
        by_stage[str(row.get("stage", "unknown"))].append(row)
        cmd_key = f"{row.get('stage', 'unknown')}::{row.get('command', 'unknown')}"
        by_command[cmd_key].append(row)

    summary = {
        "num_records": len(rows),
        "overall": _aggregate(rows),
        "by_stage": {stage: _aggregate(items) for stage, items in sorted(by_stage.items())},
        "by_command": {key: _aggregate(items) for key, items in sorted(by_command.items())},
        "largest_token_commands": [],
    }

    top = []
    for key, items in by_command.items():
        agg = _aggregate(items)
        top.append({
            "command_key": key,
            "total_tokens": agg["total_tokens"],
            "prompt_tokens": agg["prompt_tokens"],
            "completion_tokens": agg["completion_tokens"],
            "calls": agg["calls"],
            "latency_sec_sum": agg["latency_sec_sum"],
        })
    summary["largest_token_commands"] = sorted(top, key=lambda x: x["total_tokens"], reverse=True)[:20]
    return summary


def render_markdown(summary: Dict[str, Any]) -> str:
    lines = ["# LLM Usage Summary", ""]
    overall = summary.get("overall", {})
    lines.append(f"- `num_records`: {summary.get('num_records', 0)}")
    lines.append(f"- `total_tokens`: {overall.get('total_tokens', 0)}")
    lines.append(f"- `prompt_tokens`: {overall.get('prompt_tokens', 0)}")
    lines.append(f"- `completion_tokens`: {overall.get('completion_tokens', 0)}")
    lines.append(f"- `calls`: {overall.get('calls', 0)}")
    lines.append(f"- `error_calls`: {overall.get('error_calls', 0)}")
    lines.append("")
    lines.append("## By Stage")
    for stage, info in summary.get("by_stage", {}).items():
        lines.append(
            f"- `{stage}`: calls={info['calls']}, total_tokens={info['total_tokens']}, "
            f"prompt={info['prompt_tokens']}, completion={info['completion_tokens']}, "
            f"latency_sum={info['latency_sec_sum']}s"
        )
    lines.append("")
    lines.append("## Largest Token Commands")
    for item in summary.get("largest_token_commands", []):
        lines.append(
            f"- `{item['command_key']}`: total_tokens={item['total_tokens']}, "
            f"prompt={item['prompt_tokens']}, completion={item['completion_tokens']}, "
            f"calls={item['calls']}, latency_sum={item['latency_sec_sum']}s"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize LLM usage telemetry")
    parser.add_argument("--input", required=True, help="Path to llm_usage.jsonl")
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
    print(f"\nUsage JSON written to: {out_json}")
    print(f"Usage Markdown written to: {out_md}")


if __name__ == "__main__":
    main()

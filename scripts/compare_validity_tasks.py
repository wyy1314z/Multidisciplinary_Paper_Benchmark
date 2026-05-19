#!/usr/bin/env python3
"""Compare official-tier validity results across evidence-source tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_pair(text: str) -> Tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("Expected LABEL=PATH")
    label, path = text.split("=", 1)
    label = label.strip()
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError("Expected non-empty LABEL=PATH")
    return label, path


def _safe_mean(values: List[float]) -> float | None:
    values = [float(v) for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _paper_x5_overall(validity: Dict[str, Any]) -> List[float]:
    values: List[float] = []
    for paper in validity.get("papers", []):
        l1_x5 = ((paper.get("x5_by_level") or {}).get("L1") or {})
        metrics = [
            l1_x5.get(key)
            for key in (
                "interdisciplinary_integration",
                "structural_validity",
                "evidence_groundedness",
                "novelty",
                "testability",
                "feasibility",
            )
        ]
        numeric = []
        for item in metrics:
            try:
                numeric.append(float(item))
            except Exception:
                continue
        if numeric:
            values.append(sum(numeric) / len(numeric))
    return values


def _reference_source_means(validity: Dict[str, Any]) -> Dict[str, float | None]:
    keys = ["benchmark_gt_paths", "web_ref_paths", "reference_paths", "terms", "relations", "evidence_paths"]
    out: Dict[str, float | None] = {}
    for key in keys:
        vals = []
        for paper in validity.get("papers", []):
            source = paper.get("reference_sources", {}) or {}
            if key in source:
                vals.append(source.get(key))
        out[f"{key}_mean"] = _safe_mean(vals)
    return out


def _corr(analysis: Dict[str, Any], signal: str) -> Dict[str, Any]:
    return ((analysis.get("correlations") or {}).get(signal) or {}).get("x5_l1_overall") or {}


def build_comparison(validity_pairs: List[Tuple[str, str]], analysis_pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
    analysis_by_label = dict(analysis_pairs)
    rows: List[Dict[str, Any]] = []
    for label, validity_path in validity_pairs:
        validity = _load_json(validity_path)
        analysis_path = analysis_by_label.get(label)
        analysis = _load_json(analysis_path) if analysis_path else {}
        x5_values = _paper_x5_overall(validity)

        row = {
            "task": label,
            "validity_path": validity_path,
            "analysis_path": analysis_path,
            "num_papers": int(validity.get("num_papers", len(validity.get("papers", [])))),
            "x5_l1_overall_mean": _safe_mean(x5_values),
            "x5_l1_overall_min": min(x5_values) if x5_values else None,
            "x5_l1_overall_max": max(x5_values) if x5_values else None,
            **_reference_source_means(validity),
            "official_tier_spearman": _corr(analysis, "official_tier").get("spearman"),
            "official_tier_pearson": _corr(analysis, "official_tier").get("pearson"),
            "fwci_spearman": _corr(analysis, "fwci").get("spearman"),
            "fwci_pearson": _corr(analysis, "fwci").get("pearson"),
            "log1p_fwci_spearman": _corr(analysis, "log1p_fwci").get("spearman"),
            "log1p_fwci_pearson": _corr(analysis, "log1p_fwci").get("pearson"),
        }
        rows.append(row)
    return {"tasks": rows}


def _fmt(value: Any, ndigits: int = 3) -> str:
    try:
        if value is None:
            return ""
        return f"{float(value):.{ndigits}f}"
    except Exception:
        return str(value)


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Validity Evidence-Source Task Comparison",
        "",
        "| task | papers | x5_l1_mean | benchmark_refs | web_refs | all_refs | tier_spearman | fwci_spearman | log_fwci_spearman |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("tasks", []):
        lines.append(
            f"| {row.get('task', '')} "
            f"| {row.get('num_papers', '')} "
            f"| {_fmt(row.get('x5_l1_overall_mean'))} "
            f"| {_fmt(row.get('benchmark_gt_paths_mean'))} "
            f"| {_fmt(row.get('web_ref_paths_mean'))} "
            f"| {_fmt(row.get('reference_paths_mean'))} "
            f"| {_fmt(row.get('official_tier_spearman'))} "
            f"| {_fmt(row.get('fwci_spearman'))} "
            f"| {_fmt(row.get('log1p_fwci_spearman'))} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validity", nargs="+", type=_parse_pair, required=True, help="Task validity result as LABEL=PATH")
    parser.add_argument("--analysis", nargs="*", type=_parse_pair, default=[], help="Task analysis JSON as LABEL=PATH")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    payload = build_comparison(args.validity, args.analysis)
    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

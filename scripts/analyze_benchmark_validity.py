"""Analyze benchmark validity against journal-level and impact signals."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


logger = logging.getLogger("analyze_benchmark_validity")


def _flatten_rows(payload: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for paper in payload.get("papers", []):
        row = {
            "paper_id": paper.get("paper_id", ""),
            "title": paper.get("title", ""),
            "primary_discipline": paper.get("primary_discipline", ""),
        }
        row.update(paper.get("metadata", {}))
        for metric, value in paper.get("overall_scores", {}).items():
            row[f"score_{metric}"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze benchmark validity outputs")
    parser.add_argument("--input", required=True, help="Output JSON from evaluate_benchmark_validity.py")
    parser.add_argument("--output", required=True, help="Output JSON summary path")
    parser.add_argument("--min-journal-count", type=int, default=20, help="Min papers per journal for grouped analysis")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    with Path(args.input).open(encoding="utf-8") as f:
        payload = json.load(f)

    df = _flatten_rows(payload)
    if df.empty:
        raise SystemExit("No paper rows found in validity result")

    score_cols = [c for c in df.columns if c.startswith("score_")]
    numeric_signals = [c for c in ["fwci", "cited_by_count"] if c in df.columns]

    signal_correlations: Dict[str, Dict[str, float]] = {}
    for signal in numeric_signals:
        series = pd.to_numeric(df[signal], errors="coerce")
        if series.notna().sum() == 0:
            continue
        signal_correlations[signal] = {}
        for score_col in score_cols:
            score_series = pd.to_numeric(df[score_col], errors="coerce")
            valid = pd.concat([series, score_series], axis=1).dropna()
            if len(valid) < 3:
                continue
            signal_correlations[signal][score_col] = float(valid.corr(method="spearman").iloc[0, 1])

    journal_groups = (
        df.groupby("journal")
        .agg(
            paper_count=("paper_id", "count"),
            fwci_mean=("fwci", "mean"),
            cited_by_count_mean=("cited_by_count", "mean"),
            **{f"{col}_mean": (col, "mean") for col in score_cols},
        )
        .reset_index()
        if "journal" in df.columns
        else pd.DataFrame()
    )
    if not journal_groups.empty:
        journal_groups = journal_groups[journal_groups["paper_count"] >= args.min_journal_count]
        journal_groups = journal_groups.sort_values("paper_count", ascending=False)

    output = {
        "num_papers": int(len(df)),
        "num_journals": int(df["journal"].nunique(dropna=True)) if "journal" in df.columns else 0,
        "score_signal_spearman": signal_correlations,
        "top_journal_groups": journal_groups.head(50).to_dict(orient="records") if not journal_groups.empty else [],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Saved benchmark validity analysis -> %s", out_path)


if __name__ == "__main__":
    main()

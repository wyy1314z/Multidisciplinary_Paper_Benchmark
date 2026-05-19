"""Analyze L1 X+5 hypothesis scores against external journal-quality tiers."""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


logger = logging.getLogger("analyze_official_tier_validity")


X5_METRICS = [
    "interdisciplinary_integration",
    "structural_validity",
    "evidence_groundedness",
    "novelty",
    "testability",
    "feasibility",
]

OFFICIAL_FIELDS = [
    "official_tier",
    "official_tier_source",
    "official_journal",
    "official_issn_l",
    "official_quality_percentile",
    "jif",
    "jif_percentile",
    "jif_quartile",
    "jci",
    "jci_percentile",
    "jci_quartile",
    "citescore",
    "citescore_percentile",
    "citescore_quartile",
    "sjr",
    "sjr_quartile",
    "cas_zone",
    "publisher_source",
]


def _norm_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _norm_doi(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return text.replace("https://doi.org/", "").replace("http://doi.org/", "")


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _metadata_indexes(rows: Iterable[Dict[str, Any]]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_doi: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        doi = _norm_doi(row.get("doi"))
        title = _norm_title(row.get("title"))
        if doi:
            by_doi[doi] = row
        if title:
            by_title[title] = row
    return by_doi, by_title


def _find_meta(paper: Dict[str, Any], by_doi: Dict[str, Dict[str, Any]], by_title: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    metadata = paper.get("metadata", {}) or {}
    for doi in (_norm_doi(metadata.get("doi")), _norm_doi(paper.get("doi"))):
        if doi and doi in by_doi:
            return by_doi[doi]
    for title in (_norm_title(paper.get("title")), _norm_title(metadata.get("title"))):
        if title and title in by_title:
            return by_title[title]
    return {}


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    num = _safe_float(value)
    if num is None or math.isnan(num):
        return None
    return int(num)


def _flatten(validity: Dict[str, Any], sample_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    by_doi, by_title = _metadata_indexes(sample_rows)
    rows: List[Dict[str, Any]] = []
    for paper in validity.get("papers", []):
        metadata = paper.get("metadata", {}) or {}
        sample_meta = _find_meta(paper, by_doi, by_title)
        row: Dict[str, Any] = {
            "paper_id": paper.get("paper_id", ""),
            "title": paper.get("title", ""),
            "journal": metadata.get("journal") or sample_meta.get("journal", ""),
            "issn_l": metadata.get("issn_l") or sample_meta.get("issn_l", ""),
            "doi": metadata.get("doi") or sample_meta.get("doi", ""),
            "publication_date": metadata.get("publication_date") or sample_meta.get("publication_date", ""),
            "publication_year": metadata.get("publication_year") or sample_meta.get("publication_year"),
            "fwci": metadata.get("fwci") or sample_meta.get("fwci"),
            "cited_by_count": metadata.get("cited_by_count") or sample_meta.get("cited_by_count"),
            "primary_discipline": paper.get("primary_discipline", ""),
        }
        for key in OFFICIAL_FIELDS:
            row[key] = metadata.get(key, sample_meta.get(key))

        l1_x5 = ((paper.get("x5_by_level") or {}).get("L1") or {})
        for key in X5_METRICS:
            row[f"x5_l1_{key}"] = l1_x5.get(key)
        metric_values = [_safe_float(l1_x5.get(key)) for key in X5_METRICS]
        metric_values = [v for v in metric_values if v is not None]
        row["x5_l1_overall"] = sum(metric_values) / len(metric_values) if metric_values else None

        l1_scores = ((paper.get("scores_by_level") or {}).get("L1") or {})
        for key, value in l1_scores.items():
            row[f"score_l1_{key}"] = value

        rows.append(row)

    df = pd.DataFrame(rows)
    for col in [
        "official_tier",
        "official_quality_percentile",
        "jif",
        "jif_percentile",
        "jci",
        "jci_percentile",
        "citescore",
        "citescore_percentile",
        "sjr",
        "cas_zone",
        "fwci",
        "cited_by_count",
        "publication_year",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _add_paper_impact_features(df: pd.DataFrame, analysis_date: str) -> pd.DataFrame:
    df = df.copy()
    df["publication_datetime"] = pd.to_datetime(df.get("publication_date"), errors="coerce")
    analysis_ts = pd.to_datetime(analysis_date)
    df["publication_month"] = df["publication_datetime"].dt.month
    df["days_since_publication"] = (analysis_ts - df["publication_datetime"]).dt.days
    df.loc[df["days_since_publication"] < 0, "days_since_publication"] = pd.NA
    for col in ("fwci", "cited_by_count", "sjr", "official_quality_percentile"):
        if col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            df[f"log1p_{col}"] = np.log1p(numeric.clip(lower=0))
    return df


def _correlations(df: pd.DataFrame, signals: List[str], scores: List[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
    output: Dict[str, Dict[str, Dict[str, float]]] = {}
    for signal in signals:
        if signal not in df.columns:
            continue
        s1 = pd.to_numeric(df[signal], errors="coerce")
        if s1.notna().sum() < 3 or s1.nunique(dropna=True) < 2:
            continue
        output[signal] = {}
        for score in scores:
            if score not in df.columns:
                continue
            s2 = pd.to_numeric(df[score], errors="coerce")
            valid = pd.concat([s1, s2], axis=1).dropna()
            if len(valid) < 3 or valid.iloc[:, 1].nunique() < 2:
                continue
            output[signal][score] = {
                "n": int(len(valid)),
                "spearman": float(valid.corr(method="spearman").iloc[0, 1]),
                "pearson": float(valid.corr(method="pearson").iloc[0, 1]),
            }
    return output


def _regression_summary(df: pd.DataFrame, y_col: str, x_cols: List[str]) -> Dict[str, Any]:
    cols = [y_col] + x_cols
    valid = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(valid) <= len(x_cols) + 1:
        return {
            "n": int(len(valid)),
            "predictors": x_cols,
            "reason": "insufficient_rows",
        }
    if valid[y_col].nunique() < 2:
        return {
            "n": int(len(valid)),
            "predictors": x_cols,
            "reason": "constant_outcome",
        }

    y = valid[y_col].to_numpy(dtype=float)
    x = valid[x_cols].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(valid)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    pred = design @ beta
    residual = y - pred
    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    n = len(valid)
    p = len(x_cols)
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - p - 1) if n > p + 1 else None

    # Standardized coefficients are easier to compare across official tier,
    # FWCI, citation count, and publication timing signals.
    y_std = (y - np.mean(y)) / np.std(y) if np.std(y) else y * 0.0
    x_std = x.copy()
    for idx in range(x_std.shape[1]):
        col_std = np.std(x_std[:, idx])
        x_std[:, idx] = (x_std[:, idx] - np.mean(x_std[:, idx])) / col_std if col_std else 0.0
    design_std = np.column_stack([np.ones(len(valid)), x_std])
    beta_std, *_ = np.linalg.lstsq(design_std, y_std, rcond=None)

    return {
        "n": int(n),
        "predictors": x_cols,
        "r2": r2,
        "adjusted_r2": adj_r2,
        "intercept": float(beta[0]),
        "coefficients": {col: float(beta[i + 1]) for i, col in enumerate(x_cols)},
        "standardized_coefficients": {col: float(beta_std[i + 1]) for i, col in enumerate(x_cols)},
    }


def _joint_regressions(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    models: Dict[str, List[str]] = {
        "journal_tier_only": ["official_tier"],
        "paper_fwci_only": ["log1p_fwci"],
        "journal_tier_plus_fwci": ["official_tier", "log1p_fwci"],
        "journal_tier_plus_fwci_plus_time": ["official_tier", "log1p_fwci", "days_since_publication"],
        "sjr_percentile_plus_fwci_plus_time": [
            "official_quality_percentile",
            "log1p_fwci",
            "days_since_publication",
        ],
        "sjr_percentile_plus_fwci_citations_time": [
            "official_quality_percentile",
            "log1p_fwci",
            "log1p_cited_by_count",
            "days_since_publication",
        ],
    }
    return {
        name: _regression_summary(df, "x5_l1_overall", predictors)
        for name, predictors in models.items()
        if all(col in df.columns for col in predictors)
    }


def _within_tier_fwci_correlations(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    if "official_tier" not in df.columns:
        return output
    for tier, group in df.groupby("official_tier", dropna=True):
        if pd.isna(tier):
            continue
        corr = _correlations(group, ["fwci", "log1p_fwci", "cited_by_count"], ["x5_l1_overall"])
        output[str(int(tier))] = {
            "n": int(len(group)),
            "num_journals": int(group["journal"].nunique(dropna=True)) if "journal" in group.columns else 0,
            "correlations": corr,
        }
    return output


def _fmt(value: Any, ndigits: int = 3) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.{ndigits}f}"
    except Exception:
        return str(value)


def _fmt_int(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
        return str(int(value))
    except Exception:
        return ""


def _write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    overview = payload["overview"]
    corr = payload["correlations"]
    tier_summary = payload["tier_summary"]
    journal_summary = payload["journal_summary"]
    paper_table = payload["paper_table"]
    joint = payload.get("joint_regressions", {})
    journal_corr = payload.get("journal_level_correlations", {})
    within_tier = payload.get("within_tier_fwci_correlations", {})

    lines = [
        "# Official Journal Tier vs L1 Hypothesis X+5 Validity",
        "",
        "## Overview",
        f"- Papers scored: {overview['num_papers']}",
        f"- Matched official tiers: {overview['matched_official_tier_records']}",
        f"- Unique journals: {overview['num_journals']}",
        f"- Input validity file: `{overview['validity_input']}`",
        f"- Sample metadata file: `{overview['sample_metadata']}`",
        f"- Analysis date for citation-window controls: `{overview['analysis_date']}`",
        "",
        "## Main Correlations",
    ]
    main = corr.get("official_tier", {}).get("x5_l1_overall")
    if main:
        lines.append(
            f"- official_tier vs x5_l1_overall: Spearman={_fmt(main['spearman'])}, "
            f"Pearson={_fmt(main['pearson'])}, n={main['n']}"
        )
    for signal in ["jif_percentile", "citescore_percentile", "sjr", "fwci", "cited_by_count"]:
        item = corr.get(signal, {}).get("x5_l1_overall")
        if item:
            lines.append(
                f"- {signal} vs x5_l1_overall: Spearman={_fmt(item['spearman'])}, "
                f"Pearson={_fmt(item['pearson'])}, n={item['n']}"
            )
    for signal in ["log1p_fwci", "log1p_cited_by_count", "days_since_publication"]:
        item = corr.get(signal, {}).get("x5_l1_overall")
        if item:
            lines.append(
                f"- {signal} vs x5_l1_overall: Spearman={_fmt(item['spearman'])}, "
                f"Pearson={_fmt(item['pearson'])}, n={item['n']}"
            )

    lines.extend([
        "",
        "## Joint Models",
        "| model | n | R2 | adj_R2 | standardized coefficients |",
        "|---|---:|---:|---:|---|",
    ])
    for name, model in joint.items():
        std = model.get("standardized_coefficients") or {}
        std_text = "; ".join(f"{key}={_fmt(value)}" for key, value in std.items())
        lines.append(
            f"| {name} | {model.get('n', '')} | {_fmt(model.get('r2'))} "
            f"| {_fmt(model.get('adjusted_r2'))} | {std_text or model.get('reason', '')} |"
        )

    lines.extend([
        "",
        "## Journal-Level Correlations",
    ])
    item = journal_corr.get("official_tier", {}).get("x5_l1_overall_mean")
    if item:
        lines.append(
            f"- journal mean: official_tier vs x5_l1_overall_mean: "
            f"Spearman={_fmt(item['spearman'])}, Pearson={_fmt(item['pearson'])}, n={item['n']}"
        )
    item = journal_corr.get("sjr_mean", {}).get("x5_l1_overall_mean")
    if item:
        lines.append(
            f"- journal mean: sjr_mean vs x5_l1_overall_mean: "
            f"Spearman={_fmt(item['spearman'])}, Pearson={_fmt(item['pearson'])}, n={item['n']}"
        )

    lines.extend([
        "",
        "## Within-Tier Paper Impact Correlations",
        "| tier | n | journals | fwci_spearman | log1p_fwci_spearman | cited_spearman |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for tier in sorted(within_tier, key=lambda x: int(x), reverse=True):
        row = within_tier[tier]
        corrs = row.get("correlations", {})
        lines.append(
            f"| {tier} | {row.get('n', '')} | {row.get('num_journals', '')} "
            f"| {_fmt((corrs.get('fwci', {}).get('x5_l1_overall') or {}).get('spearman'))} "
            f"| {_fmt((corrs.get('log1p_fwci', {}).get('x5_l1_overall') or {}).get('spearman'))} "
            f"| {_fmt((corrs.get('cited_by_count', {}).get('x5_l1_overall') or {}).get('spearman'))} |"
        )

    lines.extend([
        "",
        "## Tier Summary",
        "| official_tier | papers | journals | x5_l1_overall | fwci | cited | interdisc | structural | evidence | novelty | testability | feasibility |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in tier_summary:
        lines.append(
            f"| {_fmt_int(row.get('official_tier'))} "
            f"| {int(row['paper_count'])} | {int(row['journal_count'])} "
            f"| {_fmt(row.get('x5_l1_overall_mean'))} "
            f"| {_fmt(row.get('fwci_mean'))} "
            f"| {_fmt(row.get('cited_by_count_mean'))} "
            f"| {_fmt(row.get('x5_l1_interdisciplinary_integration_mean'))} "
            f"| {_fmt(row.get('x5_l1_structural_validity_mean'))} "
            f"| {_fmt(row.get('x5_l1_evidence_groundedness_mean'))} "
            f"| {_fmt(row.get('x5_l1_novelty_mean'))} "
            f"| {_fmt(row.get('x5_l1_testability_mean'))} "
            f"| {_fmt(row.get('x5_l1_feasibility_mean'))} |"
        )

    lines.extend([
        "",
        "## Journal Summary",
        "| journal | tier | papers | x5_l1_overall | fwci | cited | jif | jif_pct | citescore_pct | sjr |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in journal_summary[:80]:
        lines.append(
            f"| {str(row.get('journal', '')).replace('|', '/')} "
            f"| {_fmt_int(row.get('official_tier'))} "
            f"| {int(row['paper_count'])} | {_fmt(row.get('x5_l1_overall_mean'))} "
            f"| {_fmt(row.get('fwci_mean'))} | {_fmt(row.get('cited_by_count_mean'))} "
            f"| {_fmt(row.get('jif_mean'))} | {_fmt(row.get('jif_percentile_mean'))} "
            f"| {_fmt(row.get('citescore_percentile_mean'))} | {_fmt(row.get('sjr_mean'))} |"
        )

    lines.extend([
        "",
        "## Paper Table",
        "| journal | tier | x5_l1_overall | fwci | cited | days_since_pub | title |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in paper_table[:120]:
        title = str(row.get("title", "")).replace("|", "/")[:100]
        lines.append(
            f"| {str(row.get('journal', '')).replace('|', '/')} "
            f"| {_fmt_int(row.get('official_tier'))} "
            f"| {_fmt(row.get('x5_l1_overall'))} "
            f"| {_fmt(row.get('fwci'))} "
            f"| {_fmt(row.get('cited_by_count'))} "
            f"| {_fmt(row.get('days_since_publication'), 0)} | {title} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validity", required=True, help="Output JSON from evaluate_benchmark_validity.py")
    parser.add_argument("--sample-metadata", required=True, help="Final selected paper JSONL with official fields")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument(
        "--analysis-date",
        default="2026-04-15",
        help="Date used for days_since_publication controls (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    validity = json.loads(Path(args.validity).read_text(encoding="utf-8"))
    sample_rows = _read_jsonl(args.sample_metadata)
    df = _flatten(validity, sample_rows)
    if df.empty:
        raise SystemExit("No scored papers found")
    df = _add_paper_impact_features(df, args.analysis_date)

    score_cols = ["x5_l1_overall"] + [f"x5_l1_{metric}" for metric in X5_METRICS]
    signal_cols = [
        "official_tier",
        "official_quality_percentile",
        "jif",
        "jif_percentile",
        "jci",
        "jci_percentile",
        "citescore",
        "citescore_percentile",
        "sjr",
        "cas_zone",
        "fwci",
        "log1p_fwci",
        "cited_by_count",
        "log1p_cited_by_count",
        "publication_month",
        "days_since_publication",
    ]

    tier_summary = (
        df.groupby("official_tier", dropna=False)
        .agg(
            paper_count=("paper_id", "count"),
            journal_count=("journal", "nunique"),
            fwci_mean=("fwci", "mean"),
            cited_by_count_mean=("cited_by_count", "mean"),
            **{f"{col}_mean": (col, "mean") for col in score_cols},
        )
        .reset_index()
        .sort_values("official_tier", ascending=False)
    )

    journal_summary = (
        df.groupby(["journal", "official_tier"], dropna=False)
        .agg(
            paper_count=("paper_id", "count"),
            x5_l1_overall_mean=("x5_l1_overall", "mean"),
            fwci_mean=("fwci", "mean"),
            cited_by_count_mean=("cited_by_count", "mean"),
            jif_mean=("jif", "mean"),
            jif_percentile_mean=("jif_percentile", "mean"),
            citescore_percentile_mean=("citescore_percentile", "mean"),
            sjr_mean=("sjr", "mean"),
            official_quality_percentile_mean=("official_quality_percentile", "mean"),
        )
        .reset_index()
        .sort_values(["official_tier", "x5_l1_overall_mean"], ascending=[False, False])
    )

    paper_table = df.sort_values(["official_tier", "x5_l1_overall"], ascending=[False, False])
    paper_table_for_json = paper_table.drop(columns=["publication_datetime"], errors="ignore")

    payload = {
        "overview": {
            "validity_input": args.validity,
            "sample_metadata": args.sample_metadata,
            "analysis_date": args.analysis_date,
            "num_papers": int(len(df)),
            "matched_official_tier_records": int(df["official_tier"].notna().sum()),
            "num_journals": int(df["journal"].nunique(dropna=True)),
        },
        "correlations": _correlations(df, signal_cols, score_cols),
        "joint_regressions": _joint_regressions(df),
        "within_tier_fwci_correlations": _within_tier_fwci_correlations(df),
        "journal_level_correlations": _correlations(
            journal_summary,
            [
                "official_tier",
                "official_quality_percentile_mean",
                "sjr_mean",
                "fwci_mean",
                "cited_by_count_mean",
            ],
            ["x5_l1_overall_mean"],
        ),
        "tier_summary": tier_summary.to_dict(orient="records"),
        "journal_summary": journal_summary.to_dict(orient="records"),
        "paper_table": paper_table_for_json.to_dict(orient="records"),
    }

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_csv(args.output_csv, index=False)
    _write_markdown(Path(args.output_md), payload)

    logger.info("Saved official-tier validity analysis -> %s", args.output_json)


if __name__ == "__main__":
    main()

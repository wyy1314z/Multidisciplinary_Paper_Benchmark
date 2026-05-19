"""Build an official-style journal metrics table from open SJR/CiteScore exports.

The output schema is compatible with ``scripts/sample_official_tier_papers.py``:

    journal,issn_l,official_tier,official_tier_source,
    sjr,sjr_quartile,citescore,citescore_percentile,citescore_quartile,...

Inputs are intentionally local files. SCImago and Scopus web pages may block
automated bulk downloads, while their UI supports CSV/export workflows. Download
the 2024 exports first, then run this converter.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


logger = logging.getLogger("build_journal_metrics_from_open_sources")


OUTPUT_COLUMNS = [
    "journal",
    "issn_l",
    "issns",
    "official_tier",
    "official_tier_source",
    "official_quality_percentile",
    "sjr",
    "sjr_percentile",
    "sjr_quartile",
    "h_index",
    "citescore",
    "citescore_percentile",
    "citescore_quartile",
    "source",
]


ALIASES = {
    "journal": [
        "journal",
        "title",
        "source title",
        "sourcetitle",
        "source_title",
        "publication title",
        "serial title",
        "title name",
    ],
    "issn": ["issn", "issns", "issn(s)", "eissn", "e-issn", "print issn", "source issn"],
    "sjr": ["sjr", "sjr best quartile"],  # handled specially if mixed value like "1.234 Q1"
    "sjr_quartile": ["sjr quartile", "sjr best quartile", "best quartile", "quartile"],
    "h_index": ["h index", "h-index", "h_index"],
    "citescore": ["citescore", "cite score", "cite_score", "citescoretracker", "cite score tracker"],
    "citescore_percentile": [
        "citescore percentile",
        "cite score percentile",
        "percentile",
        "highest percentile",
        "percentile rank",
    ],
    "citescore_quartile": [
        "citescore quartile",
        "cite score quartile",
        "quartile",
        "highest quartile",
    ],
}


def _norm_col(name: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", str(name or "").strip().casefold()).strip("_")


def _norm_journal(name: Any) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().casefold())


def _norm_issn(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or text.lower() == "nan":
        return ""
    compact = re.sub(r"[^0-9X]", "", text)
    return compact if len(compact) == 8 else ""


def _split_issns(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return []
    parts = re.split(r"[;,|/\s]+", text)
    return sorted({issn for part in parts if (issn := _norm_issn(part))})


def _float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".").replace("%", "")
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _quartile(value: Any) -> str:
    text = str(value or "").upper()
    match = re.search(r"Q\s*([1-4])", text)
    return f"Q{match.group(1)}" if match else ""


def _find_col(columns: Sequence[str], key: str) -> Optional[str]:
    norm_to_original = {_norm_col(col): col for col in columns}
    for alias in ALIASES.get(key, []):
        norm = _norm_col(alias)
        if norm in norm_to_original:
            return norm_to_original[norm]
    return None


def _read_table(path: str) -> pd.DataFrame:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)
    if src.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(src, dtype=str)
    # SCImago exports are semicolon-separated and contain comma decimals.
    # Prefer explicit separators before falling back to pandas' sniffer.
    errors: List[str] = []
    for kwargs in (
        {"sep": ";", "engine": "c"},
        {"sep": ",", "engine": "c"},
        {"sep": "\t", "engine": "c"},
        {"sep": None, "engine": "python"},
    ):
        try:
            df = pd.read_csv(src, dtype=str, **kwargs)
            if len(df.columns) > 1:
                return df
        except Exception as exc:
            errors.append(f"{kwargs}: {type(exc).__name__}: {exc}")
    raise ValueError(f"Could not read tabular file {src}. Tried separators: {' | '.join(errors)}")


def _best_issn(issns: Iterable[str]) -> str:
    vals = sorted({issn for issn in issns if issn})
    return vals[0] if vals else ""


def _tier_from_percentile(percentile: Optional[float], source: str) -> Tuple[Optional[int], str]:
    if percentile is None:
        return None, ""
    if 0 <= percentile <= 1:
        percentile *= 100
    if percentile >= 90:
        return 5, f"{source}_percentile>=90"
    if percentile >= 75:
        return 4, f"{source}_percentile>=75"
    if percentile >= 50:
        return 3, f"{source}_percentile>=50"
    if percentile >= 25:
        return 2, f"{source}_percentile>=25"
    if percentile >= 0:
        return 1, f"{source}_percentile<25"
    return None, ""


def _tier_from_quartile(quartile: str, source: str) -> Tuple[Optional[int], str]:
    if quartile == "Q1":
        return 4, f"{source}_quartile_Q1"
    if quartile == "Q2":
        return 3, f"{source}_quartile_Q2"
    if quartile == "Q3":
        return 2, f"{source}_quartile_Q3"
    if quartile == "Q4":
        return 1, f"{source}_quartile_Q4"
    return None, ""


def _clean_percentile(value: Any) -> Optional[float]:
    val = _float(value)
    if val is None:
        return None
    if 0 <= val <= 1:
        val *= 100
    if 0 <= val <= 100:
        return val
    return None


def _load_scimago(path: str) -> List[Dict[str, Any]]:
    df = _read_table(path)
    cols = list(df.columns)
    journal_col = _find_col(cols, "journal")
    issn_col = _find_col(cols, "issn")
    sjr_col = _find_col(cols, "sjr")
    quartile_col = _find_col(cols, "sjr_quartile")
    h_col = _find_col(cols, "h_index")
    if not journal_col:
        raise ValueError(f"Could not find journal/title column in SCImago file: {path}")

    rows: List[Dict[str, Any]] = []
    for raw in df.to_dict(orient="records"):
        journal = str(raw.get(journal_col) or "").strip()
        if not journal:
            continue
        sjr = _float(raw.get(sjr_col)) if sjr_col else None
        quartile = _quartile(raw.get(quartile_col)) if quartile_col else _quartile(raw.get(sjr_col))
        issns = _split_issns(raw.get(issn_col)) if issn_col else []
        rows.append(
            {
                "journal": journal,
                "journal_key": _norm_journal(journal),
                "issns": issns,
                "issn_l": _best_issn(issns),
                "sjr": sjr,
                "sjr_quartile": quartile,
                "h_index": _float(raw.get(h_col)) if h_col else None,
                "source": "scimago",
            }
        )

    # Compute a global SJR percentile from the export itself. This lets us split
    # Q1 into top-10% (tier 5) and remaining Q1 (tier 4).
    metric_df = pd.DataFrame(rows)
    if not metric_df.empty and metric_df["sjr"].notna().sum() > 1:
        ranks = metric_df["sjr"].rank(pct=True)
        for idx, percentile in ranks.items():
            rows[int(idx)]["sjr_percentile"] = float(percentile * 100)
    else:
        for row in rows:
            row["sjr_percentile"] = None
    return rows


def _load_citescore(path: str) -> List[Dict[str, Any]]:
    df = _read_table(path)
    cols = list(df.columns)
    journal_col = _find_col(cols, "journal")
    issn_col = _find_col(cols, "issn")
    score_col = _find_col(cols, "citescore")
    percentile_col = _find_col(cols, "citescore_percentile")
    quartile_col = _find_col(cols, "citescore_quartile")
    if not journal_col:
        raise ValueError(f"Could not find journal/title column in CiteScore file: {path}")

    rows: List[Dict[str, Any]] = []
    for raw in df.to_dict(orient="records"):
        journal = str(raw.get(journal_col) or "").strip()
        if not journal:
            continue
        issns = _split_issns(raw.get(issn_col)) if issn_col else []
        rows.append(
            {
                "journal": journal,
                "journal_key": _norm_journal(journal),
                "issns": issns,
                "issn_l": _best_issn(issns),
                "citescore": _float(raw.get(score_col)) if score_col else None,
                "citescore_percentile": _clean_percentile(raw.get(percentile_col)) if percentile_col else None,
                "citescore_quartile": _quartile(raw.get(quartile_col)) if quartile_col else "",
                "source": "citescore",
            }
        )
    return rows


def _merge_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    def keys_for(row: Dict[str, Any]) -> List[str]:
        keys = [f"issn:{issn}" for issn in row.get("issns", [])]
        if not keys and row.get("journal_key"):
            keys.append(f"journal:{row['journal_key']}")
        return keys

    for row in rows:
        keys = keys_for(row)
        if not keys:
            continue
        existing_key = next((key for key in keys if key in merged), None)
        if existing_key is None:
            existing_key = keys[0]
            merged[existing_key] = {
                "journal": row.get("journal", ""),
                "issn_l": row.get("issn_l", ""),
                "issns": set(row.get("issns", [])),
                "source": set(),
            }
        target = merged[existing_key]
        target["issns"].update(row.get("issns", []))
        if not target.get("issn_l"):
            target["issn_l"] = row.get("issn_l", "")
        for key, value in row.items():
            if key in {"journal_key", "issns", "issn_l", "source"}:
                continue
            if value not in (None, ""):
                target[key] = value
        if row.get("source"):
            target["source"].add(row["source"])
        for alias_key in keys:
            merged[alias_key] = target

    # Collapse aliases pointing to the same object.
    unique: Dict[int, Dict[str, Any]] = {}
    for row in merged.values():
        unique[id(row)] = row
    return {str(idx): row for idx, row in enumerate(unique.values())}


def _assign_tier(row: Dict[str, Any]) -> None:
    candidates: List[Tuple[int, str, Optional[float]]] = []
    for percentile_key, source in [
        ("citescore_percentile", "citescore"),
        ("sjr_percentile", "sjr"),
    ]:
        percentile = row.get(percentile_key)
        tier, reason = _tier_from_percentile(percentile, source)
        if tier is not None:
            candidates.append((tier, reason, percentile))
    for quartile_key, source in [
        ("citescore_quartile", "citescore"),
        ("sjr_quartile", "sjr"),
    ]:
        tier, reason = _tier_from_quartile(str(row.get(quartile_key) or ""), source)
        if tier is not None:
            candidates.append((tier, reason, None))
    if not candidates:
        row["official_tier"] = ""
        row["official_tier_source"] = "unmatched"
        row["official_quality_percentile"] = ""
        return
    # Prefer the highest tier; for equal tier, prefer percentile-derived evidence.
    candidates.sort(key=lambda item: (item[0], item[2] is not None, item[2] or -1), reverse=True)
    tier, reason, percentile = candidates[0]
    row["official_tier"] = tier
    row["official_tier_source"] = reason
    row["official_quality_percentile"] = percentile if percentile is not None else ""


def _target_journal_keys(paths: Sequence[str]) -> Tuple[set[str], set[str]]:
    if not paths:
        return set(), set()

    journals: set[str] = set()
    issns: set[str] = set()
    cols = [
        "primary_location.source.display_name",
        "primary_location.source.issn_l",
        "primary_location.source.type",
    ]
    for path in paths:
        for chunk in pd.read_csv(path, dtype=str, usecols=lambda col: col in cols, chunksize=200000):
            for raw in chunk.to_dict(orient="records"):
                if str(raw.get("primary_location.source.type", "")).strip().casefold() != "journal":
                    continue
                journal = _norm_journal(raw.get("primary_location.source.display_name"))
                if journal:
                    journals.add(journal)
                for issn in _split_issns(raw.get("primary_location.source.issn_l")):
                    issns.add(issn)
    return journals, issns


def _row_matches_targets(row: Dict[str, Any], target_journals: set[str], target_issns: set[str]) -> bool:
    if not target_journals and not target_issns:
        return True
    if any(issn in target_issns for issn in row.get("issns", set())):
        return True
    return _norm_journal(row.get("journal")) in target_journals


def _finalize(merged: Dict[str, Dict[str, Any]], target_csvs: Sequence[str]) -> List[Dict[str, Any]]:
    target_journals, target_issns = _target_journal_keys(target_csvs)
    output = []
    for row in merged.values():
        if not _row_matches_targets(row, target_journals, target_issns):
            continue
        row = dict(row)
        row["issns"] = ";".join(sorted(row.get("issns", set())))
        row["issn_l"] = row.get("issn_l") or _best_issn(row["issns"].split(";"))
        row["source"] = "+".join(sorted(row.get("source", set())))
        _assign_tier(row)
        output.append({col: row.get(col, "") for col in OUTPUT_COLUMNS})
    output.sort(key=lambda r: (-(int(r["official_tier"]) if str(r["official_tier"]).isdigit() else -1), r["journal"]))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scimago-csv", nargs="*", default=[], help="SCImago/SJR CSV/XLSX exports")
    parser.add_argument("--citescore-csv", nargs="*", default=[], help="CiteScore CSV/XLSX exports")
    parser.add_argument("--target-csvs", nargs="*", default=[], help="Optional raw paper CSVs; if provided, output only matching journals")
    parser.add_argument("--output", required=True, help="Output journal_metrics_2024.csv")
    parser.add_argument("--summary", required=True, help="Output summary JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if not args.scimago_csv and not args.citescore_csv:
        raise SystemExit("Provide at least one --scimago-csv or --citescore-csv file")

    rows: List[Dict[str, Any]] = []
    for path in args.scimago_csv:
        loaded = _load_scimago(path)
        logger.info("Loaded %d SCImago rows from %s", len(loaded), path)
        rows.extend(loaded)
    for path in args.citescore_csv:
        loaded = _load_citescore(path)
        logger.info("Loaded %d CiteScore rows from %s", len(loaded), path)
        rows.extend(loaded)

    merged = _merge_rows(rows)
    output = _finalize(merged, args.target_csvs)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(output, columns=OUTPUT_COLUMNS).to_csv(out_path, index=False)

    tier_counts = pd.Series([row["official_tier"] for row in output]).value_counts(dropna=False).to_dict()
    source_counts = pd.Series([row["source"] for row in output]).value_counts(dropna=False).to_dict()
    summary = {
        "scimago_inputs": args.scimago_csv,
        "citescore_inputs": args.citescore_csv,
        "target_csvs": args.target_csvs,
        "input_rows": len(rows),
        "merged_unique_journals": len(merged),
        "output_rows": len(output),
        "tier_counts": {str(k): int(v) for k, v in tier_counts.items()},
        "source_counts": {str(k): int(v) for k, v in source_counts.items()},
        "output": str(out_path),
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d journal metric rows -> %s", len(output), out_path)


if __name__ == "__main__":
    main()

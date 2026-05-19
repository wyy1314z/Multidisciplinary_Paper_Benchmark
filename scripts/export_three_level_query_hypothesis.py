#!/usr/bin/env python3
"""Export three-level queries and hypotheses from extraction JSONL results."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_items(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _norm_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _norm_doi(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return text.replace("https://doi.org/", "").replace("http://doi.org/", "")


def _metadata_indexes(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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


def _find_metadata(item: Dict[str, Any], by_doi: Dict[str, Dict[str, Any]], by_title: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    parsed = item.get("parsed") or {}
    meta = parsed.get("meta", {}) or {}
    for doi in (_norm_doi(meta.get("doi")), _norm_doi(item.get("doi"))):
        if doi and doi in by_doi:
            return by_doi[doi]
    for title in (_norm_title(item.get("title")), _norm_title(meta.get("title"))):
        if title and title in by_title:
            return by_title[title]
    return {}


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _path_summary(path: List[Dict[str, Any]]) -> str:
    if not path:
        return ""
    claims = [str(step.get("claim", "")).strip() for step in path if step.get("claim")]
    if claims:
        return claims[-1]
    parts = []
    for step in path:
        head = str(step.get("head", "")).strip()
        relation = str(step.get("relation", "")).strip()
        tail = str(step.get("tail", "")).strip()
        if head or relation or tail:
            parts.append(f"{head} --{relation}--> {tail}")
    return " | ".join(parts)


def _flatten_for_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    queries = row.get("queries", {}) or {}
    hypotheses = row.get("hypotheses", {}) or {}
    flat = {
        "title": row.get("title", ""),
        "journal": row.get("journal", ""),
        "official_tier": row.get("official_tier", ""),
        "doi": row.get("doi", ""),
        "primary": row.get("primary", ""),
        "secondary_list": "; ".join(row.get("secondary_list", []) or []),
        "crossdisc_score": row.get("crossdisc_score", ""),
        "query_L1": queries.get("L1", ""),
        "query_L2": " | ".join(queries.get("L2", []) or []),
        "query_L3": " | ".join(queries.get("L3", []) or []),
    }
    for level in ("L1", "L2", "L3"):
        level_data = hypotheses.get(level, {}) or {}
        summaries = level_data.get("summaries", []) or []
        flat[f"hypothesis_{level}_count"] = len(level_data.get("paths", []) or [])
        flat[f"hypothesis_{level}_summaries"] = " | ".join(str(x) for x in summaries)
        flat[f"hypothesis_{level}_path_claims"] = " | ".join(level_data.get("path_claims", []) or [])
    return flat


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flat_rows = [_flatten_for_csv(row) for row in rows]
    fieldnames = list(flat_rows[0].keys()) if flat_rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)


def _extract_row(item: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    parsed = item.get("parsed") or {}
    meta = parsed.get("meta", {}) or {}
    query = parsed.get("查询", {}) or {}
    hyp = parsed.get("假设", {}) or {}
    level_map = {"L1": "一级", "L2": "二级", "L3": "三级"}

    hypotheses: Dict[str, Any] = {}
    for level, cn_key in level_map.items():
        paths = hyp.get(cn_key, []) or []
        summaries = hyp.get(f"{cn_key}总结", []) or []
        hypotheses[level] = {
            "paths": paths,
            "summaries": summaries,
            "path_claims": [_path_summary(path) for path in paths if isinstance(path, list)],
        }

    return {
        "ok": bool(item.get("ok")),
        "error": item.get("error", ""),
        "title": item.get("title") or meta.get("title", "") or metadata.get("title", ""),
        "journal": meta.get("journal", item.get("journal", "")) or metadata.get("journal", ""),
        "official_tier": item.get("official_tier") or meta.get("official_tier") or metadata.get("official_tier"),
        "doi": meta.get("doi", item.get("doi", "")) or metadata.get("doi", ""),
        "primary": meta.get("primary", item.get("primary", "")),
        "secondary_list": meta.get("secondary_list", item.get("secondary_list", [])),
        "crossdisc_score": item.get("crossdisc_score", metadata.get("crossdisc_score")),
        "queries": {
            "L1": query.get("一级", ""),
            "L2": query.get("二级", []) or [],
            "L3": query.get("三级", []) or [],
        },
        "hypotheses": hypotheses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Extraction JSONL/JSON from run.py batch")
    parser.add_argument("--metadata-jsonl", default=None, help="Optional sampled paper JSONL used to re-attach tier/crossdisc metadata")
    parser.add_argument("--output-jsonl", required=True, help="Compact three-level query/hypothesis JSONL")
    parser.add_argument("--output-csv", required=True, help="Flat CSV summary")
    parser.add_argument("--summary", required=True, help="Summary JSON")
    args = parser.parse_args()

    items = _read_items(Path(args.input))
    by_doi: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    if args.metadata_jsonl:
        by_doi, by_title = _metadata_indexes(_read_items(Path(args.metadata_jsonl)))
    rows = [_extract_row(item, _find_metadata(item, by_doi, by_title)) for item in items]
    _write_jsonl(Path(args.output_jsonl), rows)
    _write_csv(Path(args.output_csv), rows)

    summary = {
        "input": args.input,
        "metadata_jsonl": args.metadata_jsonl,
        "output_jsonl": args.output_jsonl,
        "output_csv": args.output_csv,
        "total_records": len(rows),
        "ok_records": sum(1 for row in rows if row.get("ok")),
        "error_records": sum(1 for row in rows if not row.get("ok")),
        "level_path_counts": {
            level: sum(len(((row.get("hypotheses") or {}).get(level) or {}).get("paths", []) or []) for row in rows)
            for level in ("L1", "L2", "L3")
        },
        "level_query_counts": {
            "L1": sum(1 for row in rows if ((row.get("queries") or {}).get("L1") or "").strip()),
            "L2": sum(len((row.get("queries") or {}).get("L2", []) or []) for row in rows),
            "L3": sum(len((row.get("queries") or {}).get("L3", []) or []) for row in rows),
        },
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

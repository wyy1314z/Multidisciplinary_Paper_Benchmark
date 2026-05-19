"""Keep only L1 hypotheses from extraction JSONL and optionally enrich metadata."""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger("keep_l1_extractions")


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


def _write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _metadata_indexes(rows: List[Dict[str, Any]]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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


def _find_meta(item: Dict[str, Any], by_doi: Dict[str, Dict[str, Any]], by_title: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    parsed_meta = (item.get("parsed") or {}).get("meta") or {}
    for doi in (_norm_doi(item.get("doi")), _norm_doi(parsed_meta.get("doi"))):
        if doi and doi in by_doi:
            return by_doi[doi]
    for title in (_norm_title(item.get("title")), _norm_title(parsed_meta.get("title"))):
        if title and title in by_title:
            return by_title[title]
    return None


def _strip_to_l1(item: Dict[str, Any], first_l1_only: bool = False) -> Dict[str, Any]:
    out = dict(item)
    parsed = json.loads(json.dumps(out.get("parsed") or {}, ensure_ascii=False))

    hyp = parsed.get("假设")
    if isinstance(hyp, dict):
        if first_l1_only:
            hyp["一级"] = (hyp.get("一级") or [])[:1]
            hyp["一级总结"] = (hyp.get("一级总结") or [])[:1]
        hyp["二级"] = []
        hyp["三级"] = []
        hyp["二级总结"] = []
        hyp["三级总结"] = []

    queries = parsed.get("查询")
    if isinstance(queries, dict):
        queries["二级"] = []
        queries["三级"] = []

    out["parsed"] = parsed
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Extraction JSONL")
    parser.add_argument("--output", required=True, help="L1-only extraction JSONL")
    parser.add_argument("--metadata-jsonl", default=None, help="Optional selected-paper JSONL with official journal metadata")
    parser.add_argument("--summary", default=None, help="Optional summary JSON")
    parser.add_argument("--first-l1-only", action="store_true", help="Keep only the first L1 hypothesis path per paper")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    items = _read_jsonl(args.input)
    by_doi: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    if args.metadata_jsonl:
        by_doi, by_title = _metadata_indexes(_read_jsonl(args.metadata_jsonl))

    kept = []
    enriched = 0
    l1_path_count = 0
    for item in items:
        out = _strip_to_l1(item, first_l1_only=args.first_l1_only)
        meta = _find_meta(out, by_doi, by_title) if args.metadata_jsonl else None
        if meta:
            enriched += 1
            parsed_meta = out.setdefault("parsed", {}).setdefault("meta", {})
            for key in OFFICIAL_FIELDS:
                if key in meta:
                    out[key] = meta[key]
                    parsed_meta[key] = meta[key]

        hyp = ((out.get("parsed") or {}).get("假设") or {})
        l1_path_count += len(hyp.get("一级") or [])
        kept.append(out)

    _write_jsonl(args.output, kept)
    summary = {
        "input": args.input,
        "output": args.output,
        "records": len(kept),
        "metadata_enriched_records": enriched,
        "total_l1_paths": l1_path_count,
        "first_l1_only": args.first_l1_only,
    }
    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Saved %d L1-only extraction records -> %s", len(kept), args.output)


if __name__ == "__main__":
    main()

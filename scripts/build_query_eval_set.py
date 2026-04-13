"""Build a query-centric evaluation set from extraction outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List


logger = logging.getLogger("build_query_eval_set")


def _load_items(path: str) -> List[Dict[str, Any]]:
    src = Path(path)
    if src.suffix.lower() == ".jsonl":
        items: List[Dict[str, Any]] = []
        with src.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items
    with src.open(encoding="utf-8") as f:
        return json.load(f)


def _extract_gt_terms(parsed: Dict[str, Any]) -> List[str]:
    concepts = parsed.get("概念", {})
    terms: List[str] = []
    for c in concepts.get("主学科", []):
        term = (c.get("normalized") or c.get("term") or "").strip()
        if term:
            terms.append(term)
    for concept_list in concepts.get("辅学科", {}).values():
        for c in concept_list:
            term = (c.get("normalized") or c.get("term") or "").strip()
            if term:
                terms.append(term)
    return terms


def build_query_eval_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items:
        if not item.get("ok") or not item.get("parsed"):
            continue
        parsed = item["parsed"]
        meta = parsed.get("meta", {})
        title = meta.get("title", item.get("title", ""))
        paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        queries = parsed.get("查询", {})
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "abstract": item.get("abstract", ""),
                "primary_discipline": meta.get("primary", item.get("primary", "")),
                "secondary_disciplines": meta.get("secondary_list", item.get("secondary_list", [])),
                "queries": {
                    "L1": queries.get("一级", ""),
                    "L2": queries.get("二级", []),
                    "L3": queries.get("三级", []),
                },
                "gt_terms": _extract_gt_terms(parsed),
                "gt_relations": parsed.get("跨学科关系", []),
                "metadata": {
                    "journal": meta.get("journal", item.get("journal", "")),
                    "journal_id": meta.get("journal_id", item.get("journal_id", "")),
                    "issn_l": meta.get("issn_l", item.get("issn_l", "")),
                    "source_type": meta.get("source_type", item.get("source_type", "")),
                    "doi": meta.get("doi", item.get("doi", "")),
                    "publication_date": meta.get("publication_date", item.get("publication_date", "")),
                    "publication_year": meta.get("publication_year", item.get("publication_year")),
                    "fwci": meta.get("fwci", item.get("fwci")),
                    "cited_by_count": meta.get("cited_by_count", item.get("cited_by_count")),
                    "field": meta.get("field", item.get("field", "")),
                },
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build query-centric eval set from extractions")
    parser.add_argument("--input", required=True, help="Extraction results (.json or .jsonl)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--max-items", type=int, default=None, help="Keep only the first N valid items")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    rows = build_query_eval_rows(_load_items(args.input))
    if args.max_items is not None:
        rows = rows[: args.max_items]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    logger.info("Saved %d query-eval rows -> %s", len(rows), out_path)


if __name__ == "__main__":
    main()

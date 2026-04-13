"""Evaluate benchmark validity using extracted hypotheses from held-out papers.

This script is designed for the temporal validation stage:
1. Build the benchmark from past papers (for example 2023-2024)
2. Extract hypotheses from held-out future papers (for example 2025)
3. Score those real-paper hypotheses against the benchmark
4. Export per-paper and summary metrics for downstream validity analysis
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from crossdisc_extractor.benchmark.evaluate_benchmark import (
    GlobalKG,
    evaluate_single_path,
    normalize_paths_structure,
)

logger = logging.getLogger("benchmark_validity")


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


def _safe_mean(values: List[float]) -> float:
    return float(np.mean(values)) if values else 0.0


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


def _metadata_from_item(item: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
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
    }


def iter_validity_rows(
    benchmark_path: str,
    extraction_path: str,
    taxonomy_path: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Iterable[Dict[str, Any]]:
    kg = GlobalKG(benchmark_path, taxonomy_path=taxonomy_path)
    items = _load_items(extraction_path)
    if max_items is not None:
        items = items[:max_items]

    for item_idx, item in enumerate(items, start=1):
        if not item.get("ok") or not item.get("parsed"):
            continue

        parsed = item["parsed"]
        meta = parsed.get("meta", {})
        title = meta.get("title", item.get("title", ""))
        primary = meta.get("primary", item.get("primary", "unknown"))
        abstract = item.get("abstract", "")
        item_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        query_data = parsed.get("查询", {})
        hyp = parsed.get("假设", {})
        gt_terms = _extract_gt_terms(parsed)
        gt_relations = parsed.get("跨学科关系", [])

        l1_query = query_data.get("一级", "") or f"关于 {primary} 的 {title} 的跨学科研究假设"
        gt_set = kg.retrieve_relevant_paths(primary, l1_query, k=3)
        if not gt_set:
            logger.warning("[%d] No GT reference paths found for %s", item_idx, title[:80])
            continue

        per_level_scores: Dict[str, List[Dict[str, float]]] = defaultdict(list)
        for level, cn_key, query_key in [
            ("L1", "一级", "一级"),
            ("L2", "二级", "二级"),
            ("L3", "三级", "三级"),
        ]:
            raw_paths = hyp.get(cn_key, [])
            normalized_paths = normalize_paths_structure(raw_paths)
            if not normalized_paths:
                continue
            level_queries = query_data.get(query_key, [])

            for path_idx, path in enumerate(normalized_paths):
                gen_query = l1_query
                if isinstance(level_queries, list) and path_idx < len(level_queries):
                    gen_query = level_queries[path_idx] or l1_query
                elif isinstance(level_queries, str) and level_queries.strip():
                    gen_query = level_queries.strip()

                scores = evaluate_single_path(
                    path=path,
                    gt_paths=gt_set,
                    query=l1_query,
                    discipline=primary,
                    level=level,
                    gen_query=gen_query,
                    kg=kg,
                    gt_terms=gt_terms,
                    gt_relations=gt_relations,
                    gt_evidence_paths=None,
                    abstract=abstract,
                    _item_id=item_id,
                    _path_idx=path_idx,
                )
                per_level_scores[level].append(scores)

        if not per_level_scores:
            continue

        aggregated_by_level: Dict[str, Dict[str, float]] = {}
        overall_acc: Dict[str, List[float]] = defaultdict(list)
        for level, score_list in per_level_scores.items():
            level_metrics: Dict[str, List[float]] = defaultdict(list)
            for score_dict in score_list:
                for key, value in score_dict.items():
                    level_metrics[key].append(value)
                    overall_acc[key].append(value)
            aggregated_by_level[level] = {
                metric: _safe_mean(values)
                for metric, values in sorted(level_metrics.items())
            }

        overall_scores = {
            metric: _safe_mean(values)
            for metric, values in sorted(overall_acc.items())
        }

        yield {
            "paper_id": item_id,
            "title": title,
            "primary_discipline": primary,
            "secondary_disciplines": meta.get("secondary_list", item.get("secondary_list", [])),
            "l1_query": l1_query,
            "path_counts": {level: len(v) for level, v in per_level_scores.items()},
            "overall_scores": overall_scores,
            "scores_by_level": aggregated_by_level,
            "metadata": _metadata_from_item(item, meta),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate benchmark validity using real extracted hypotheses")
    parser.add_argument("--benchmark", required=True, help="Benchmark dataset JSON")
    parser.add_argument("--extractions", required=True, help="Held-out extraction results (.json or .jsonl)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--taxonomy", default=None, help="Optional taxonomy path")
    parser.add_argument("--max-items", type=int, default=None, help="Evaluate only the first N items")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    rows = list(
        iter_validity_rows(
            benchmark_path=args.benchmark,
            extraction_path=args.extractions,
            taxonomy_path=args.taxonomy,
            max_items=args.max_items,
        )
    )
    summary_metrics: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        for key, value in row["overall_scores"].items():
            summary_metrics[key].append(value)

    output = {
        "num_papers": len(rows),
        "summary": {
            key: _safe_mean(values)
            for key, values in sorted(summary_metrics.items())
        },
        "papers": rows,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Saved benchmark validity results for %d papers -> %s", len(rows), out_path)


if __name__ == "__main__":
    main()

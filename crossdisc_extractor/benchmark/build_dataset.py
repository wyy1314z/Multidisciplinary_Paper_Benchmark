"""
build_dataset.py — Build benchmark dataset from extraction results.

Supports two GT construction modes:
  - legacy: Uses LLM-generated hypothesis paths directly (v1/v2)
  - evidence: Uses evidence-grounded GT construction pipeline (v3)

The evidence-grounded mode (--gt-mode evidence) builds GT from:
  Stage 1: Constrained terminology extraction + dictionary grounding
  Stage 2: Evidence-based relation construction from co-occurrence
  Stage 3: Graph traversal for path construction
"""

import argparse
import json
import logging
import os
from typing import Any, Dict, List, Optional

from crossdisc_extractor.graph_builder import build_graph_and_metrics
from crossdisc_extractor.schemas import Extraction

logger = logging.getLogger("build_dataset")


def _build_metadata(item: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = meta or {}
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


def load_extractions(input_path: str) -> List[Dict[str, Any]]:
    with open(input_path, "r", encoding="utf-8") as f:
        if input_path.lower().endswith(".jsonl"):
            data = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)

    valid_data = []
    for item in data:
        if item.get("ok") and item.get("parsed"):
            valid_data.append(item)
    return valid_data


def convert_to_benchmark_format(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Legacy GT construction: uses LLM hypothesis paths directly."""
    parsed = item["parsed"]
    try:
        extraction = Extraction(**parsed)
        if not extraction.graph:
            extraction = build_graph_and_metrics(extraction)

        entry = {
            "id": item.get("title", "")[:50],
            "input": {
                "title": extraction.meta.title,
                "primary_discipline": extraction.meta.primary,
                "secondary_disciplines": extraction.meta.secondary_list,
                "abstract": item.get("abstract", ""),
            },
            "metadata": _build_metadata(item, extraction.meta.model_dump()),
            "ground_truth": {
                "graph": extraction.graph.model_dump() if extraction.graph else None,
                "hypothesis_paths": {
                    "L1": [
                        [p.model_dump() for p in path]
                        for path in extraction.假设.一级
                    ],
                    "L2": [
                        [p.model_dump() for p in path]
                        for path in extraction.假设.二级
                    ],
                    "L3": [
                        [p.model_dump() for p in path]
                        for path in extraction.假设.三级
                    ],
                },
            },
            "metrics": extraction.metrics.model_dump()
            if extraction.metrics
            else {},
        }
        return entry
    except Exception as e:
        print(f"Error converting item {item.get('title')}: {e}")
        return None


def convert_to_evidence_grounded_format(
    item: Dict[str, Any],
    taxonomy_path: Optional[str] = None,
    llm_fn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evidence-grounded GT construction (v3).

    Builds GT from paper text using:
    1. Constrained term extraction + dictionary grounding
    2. Co-occurrence based relation construction with evidence
    3. Graph traversal for path generation
    """
    from crossdisc_extractor.benchmark.gt_builder import build_ground_truth

    title = item.get("title", "")
    abstract = item.get("abstract", "")
    introduction = item.get("introduction", "")

    # Try to get metadata from parsed field
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    primary_disc = meta.get("primary", item.get("primary", "unknown"))
    secondary_list = meta.get(
        "secondary_list", item.get("secondary_list", [])
    )

    if not abstract and not introduction:
        logger.warning("No abstract or introduction for: %s", title[:60])
        return None

    # Extract pre-parsed concepts if available (from production pipeline)
    parsed_concepts = parsed.get("概念") if parsed else None

    try:
        gt = build_ground_truth(
            title=title,
            abstract=abstract,
            introduction=introduction,
            taxonomy_path=taxonomy_path,
            llm_fn=llm_fn,
            parsed_concepts=parsed_concepts,
            primary_discipline=primary_disc,
        )

        entry = {
            "id": title[:50],
            "input": {
                "title": title,
                "primary_discipline": primary_disc,
                "secondary_disciplines": secondary_list,
                "abstract": abstract,
            },
            "metadata": _build_metadata(item, meta),
            "ground_truth": {
                "terms": gt["terms"],
                "relations": gt["relations"],
                "paths": gt["paths"],
                "concept_graph": gt["concept_graph"],
            },
            "gt_stats": gt["stats"],
        }

        # Also include legacy hypothesis paths if available
        hyp = parsed.get("假设", {})
        if hyp:
            hp = {
                "L1": hyp.get("一级", []),
                "L2": hyp.get("二级", []),
                "L3": hyp.get("三级", []),
            }
            entry["ground_truth"]["hypothesis_paths_legacy"] = hp
            # evaluate_benchmark.py reads "hypothesis_paths" key
            entry["ground_truth"]["hypothesis_paths"] = hp

        return entry

    except Exception as e:
        logger.error("Error building evidence GT for %s: %s", title[:60], e)
        return None


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Build Benchmark Dataset from Extractions"
    )
    parser.add_argument(
        "--input", required=True, help="Input JSON file with extraction results"
    )
    parser.add_argument(
        "--output", required=True, help="Output JSON file for benchmark dataset"
    )
    parser.add_argument(
        "--gt-mode",
        choices=["legacy", "evidence"],
        default="evidence",
        help="GT construction mode: 'legacy' (LLM hypothesis paths) or "
        "'evidence' (evidence-grounded from paper text). Default: evidence",
    )
    parser.add_argument(
        "--taxonomy",
        default=None,
        help="Path to taxonomy JSON (for evidence mode term grounding)",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for term extraction and relation classification "
        "(evidence mode only). Requires API key.",
    )
    args = parser.parse_args()

    print(f"Loading data from {args.input}...")
    items = load_extractions(args.input)
    print(f"Found {len(items)} valid items.")
    print(f"GT construction mode: {args.gt_mode}")

    # Setup LLM function if requested
    llm_fn = None
    if args.use_llm and args.gt_mode == "evidence":
        try:
            from crossdisc_extractor.utils.llm import chat_completion_with_retry
            llm_fn = chat_completion_with_retry
            print("LLM enabled for term extraction and relation classification")
        except ImportError:
            print("Warning: LLM module not available, using heuristic extraction")

    benchmark_data = []
    for item in items:
        if args.gt_mode == "evidence":
            entry = convert_to_evidence_grounded_format(
                item,
                taxonomy_path=args.taxonomy,
                llm_fn=llm_fn,
            )
        else:
            entry = convert_to_benchmark_format(item)

        if entry:
            benchmark_data.append(entry)

    print(f"Converted {len(benchmark_data)} items to benchmark format.")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)
    print(f"Saved benchmark dataset to {args.output}")

    # Print summary statistics for evidence mode
    if args.gt_mode == "evidence":
        total_terms = sum(len(e.get("ground_truth", {}).get("terms", [])) for e in benchmark_data)
        total_rels = sum(len(e.get("ground_truth", {}).get("relations", [])) for e in benchmark_data)
        total_paths = sum(len(e.get("ground_truth", {}).get("paths", [])) for e in benchmark_data)
        grounded = sum(
            e.get("gt_stats", {}).get("n_grounded", 0)
            for e in benchmark_data
        )
        print(f"\n=== Evidence-Grounded GT Summary ===")
        print(f"  Total terms: {total_terms} ({grounded} grounded to dictionary)")
        print(f"  Total relations: {total_rels}")
        print(f"  Total paths: {total_paths}")


if __name__ == "__main__":
    main()

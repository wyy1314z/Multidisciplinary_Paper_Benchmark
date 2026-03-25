"""Unified pipeline: classify papers → filter multidisciplinary → extract hypotheses.

Three CLI subcommands:
  classify  — Run discipline classification only
  extract   — Run knowledge extraction on pre-classified data
  full      — Full pipeline: classify → filter multidisciplinary → extract
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge: convert classifier output → extractor input
# ---------------------------------------------------------------------------

def _classifier_output_to_extractor_input(
    paper: Dict[str, Any],
    main_levels: List[Tuple[str, str]],
    non_main_levels: List[Tuple[str, str]],
) -> Optional[Dict[str, Any]]:
    """Convert classifier output format to extractor input format.

    Args:
        paper: Original paper dict (title, abstract, pdf_url, ...)
        main_levels: [(level_num, name), ...] e.g. [("1", "数学"), ("2", "代数学")]
        non_main_levels: [(level_num, name), ...] e.g. [("1", "物理学"), ("2", "光学")]

    Returns:
        Dict in extractor-compatible format, or None if no primary discipline found.
    """
    # Extract primary = first L1 from main_levels
    primary = ""
    for lvl, name in main_levels:
        if lvl == "1":
            primary = name
            break

    # Extract secondary = all distinct L1 names from non_main_levels,
    # excluding the primary discipline itself
    secondary_list: List[str] = []
    seen: set = {primary}  # pre-seed with primary to exclude it
    for lvl, name in non_main_levels:
        if lvl == "1" and name not in seen:
            secondary_list.append(name)
            seen.add(name)

    if not primary:
        return None

    # Format main_levels / non_main_levels as "L1:X; L2:Y" strings
    # so that extractor's _extract_L1_list() can also parse them
    ml_str = "; ".join(f"L{lvl}:{name}" for lvl, name in main_levels)
    nml_str = "; ".join(f"L{lvl}:{name}" for lvl, name in non_main_levels)

    # Resolve pdf_url: prefer explicit pdf_url, then try to derive from doi
    pdf_url = (paper.get("pdf_url") or "").strip()
    if not pdf_url:
        doi = (paper.get("doi") or "").strip()
        if doi:
            pdf_url = doi  # fetch_pdf_and_extract_intro handles DOI→PDF conversion

    return {
        "title": paper.get("title", ""),
        "abstract": paper.get("abstract", ""),
        "pdf_url": pdf_url,
        "primary": primary,
        "secondary": ", ".join(secondary_list),
        "secondary_list": secondary_list,
        "main_levels": ml_str,
        "non_main_levels": nml_str,
    }


# ---------------------------------------------------------------------------
# Phase 1: Classify papers and filter multidisciplinary
# ---------------------------------------------------------------------------

async def classify_and_filter(
    input_path: str,
    output_path: str,
    config_path: Optional[str] = None,
    model_name: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    taxonomy_path: Optional[str] = None,
    concurrency: Optional[int] = None,
    crossdisc_threshold: Optional[float] = None,
) -> str:
    """Classify papers, filter multidisciplinary ones, write to JSONL.

    Returns:
        Path to the output file containing multidisciplinary papers.
    """
    from crossdisc_extractor.classifier import (
        AsyncHierarchicalClassifier,
        DisciplinePromptBuilder,
        Taxonomy,
        load_config,
    )
    from crossdisc_extractor.classifier.utils.parsing import (
        extract_multidisciplinary,
        levels_from_paths,
    )

    cfg = load_config(config_path, model_name=model_name, api_base=api_base, api_key=api_key)
    # CLI threshold override takes priority over config
    if crossdisc_threshold is not None:
        cfg.llm.crossdisc_confidence_threshold = crossdisc_threshold
    taxo_path = taxonomy_path or cfg.taxonomy_path
    taxonomy = Taxonomy.from_json_file(taxo_path)
    prompt_builder = DisciplinePromptBuilder()
    classifier = AsyncHierarchicalClassifier(taxonomy, prompt_builder, cfg.llm)

    # Load input papers (JSONL)
    papers: List[Dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                papers.append(json.loads(line))

    sem = asyncio.Semaphore(concurrency or cfg.concurrency)
    multidisc_records: List[Dict[str, Any]] = []
    total = len(papers)
    classified_count = 0
    multi_count = 0

    async def process_one(idx: int, paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        nonlocal classified_count, multi_count
        async with sem:
            title = paper.get("title", "").strip()
            abstract = paper.get("abstract", "").strip()
            introduction = paper.get("introduction", "").strip()

            if not title or not abstract:
                logger.warning("[%d/%d] Skipped (no title/abstract): %s", idx, total, title[:60])
                return None

            question = (title, abstract, introduction) if introduction else (title, abstract)
            try:
                result = await classifier.classify_async(question)
            except Exception as e:
                logger.error("[%d/%d] Classification failed for '%s': %s", idx, total, title[:60], e)
                return None

            classified_count += 1

            # Cross-disciplinary = multiple distinct L1 disciplines in paths
            distinct_l1 = set()
            for path in result.paths:
                if path:
                    distinct_l1.add(path[0])

            if len(distinct_l1) <= 1:
                logger.info("[%d/%d] Non-multidisciplinary (single L1: %s): %s",
                            idx, total, distinct_l1, title[:60])
                return None

            # Check cross-disciplinary confidence score
            threshold = cfg.llm.crossdisc_confidence_threshold
            if result.crossdisc_score is not None and result.crossdisc_score < threshold:
                logger.info(
                    "[%d/%d] Below cross-disc confidence threshold "
                    "(score=%.2f < threshold=%.2f, reason=%s): %s",
                    idx, total, result.crossdisc_score, threshold,
                    result.crossdisc_reason, title[:60],
                )
                return None

            multi_count += 1
            main_levels, non_main_levels = levels_from_paths(result.paths, result.raw_outputs)
            record = _classifier_output_to_extractor_input(paper, main_levels, non_main_levels)
            if record:
                record["crossdisc_score"] = result.crossdisc_score
                record["crossdisc_reason"] = result.crossdisc_reason
                logger.info("[%d/%d] Multidisciplinary (score=%.2f): %s → primary=%s, secondary=%s",
                            idx, total, result.crossdisc_score or 0.0,
                            title[:60], record["primary"], record["secondary"])
            return record

    tasks = [process_one(i + 1, p) for i, p in enumerate(papers)]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r is not None:
            multidisc_records.append(r)

    # Write filtered output
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in multidisc_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(
        "Classification complete: %d total → %d classified → %d multidisciplinary → %s",
        total, classified_count, multi_count, output_path,
    )
    return output_path


# ---------------------------------------------------------------------------
# CLI: subcommands
# ---------------------------------------------------------------------------

def cmd_classify(args: argparse.Namespace) -> None:
    """Run classification only."""
    asyncio.run(classify_and_filter(
        input_path=args.input,
        output_path=args.output,
        config_path=args.config,
        model_name=args.model,
        api_base=args.api_base,
        api_key=args.api_key,
        taxonomy_path=args.taxonomy,
        concurrency=args.concurrency,
        crossdisc_threshold=getattr(args, "crossdisc_threshold", None),
    ))


def cmd_extract(args: argparse.Namespace) -> None:
    """Run extraction on pre-classified data."""
    from crossdisc_extractor.extractor_multi_stage import run_benchmark

    run_benchmark(
        input_path=args.input,
        output_path=args.output,
        max_items=args.max_items,
        sleep_s=args.sleep,
        num_workers=args.num_workers,
        max_tokens_struct=args.max_tokens_struct,
        max_tokens_query=args.max_tokens_query,
        max_tokens_hyp=args.max_tokens_hyp,
        language_mode=args.language_mode,
        resume=args.resume,
    )


def cmd_full(args: argparse.Namespace) -> None:
    """Full pipeline: classify → filter → extract."""
    # Determine intermediate file path
    intermediate_path = args.intermediate
    if not intermediate_path:
        base, ext = os.path.splitext(args.output)
        intermediate_path = f"{base}_classified.jsonl"

    # Phase 1: Classify and filter
    logger.info("=== Phase 1: Classifying papers ===")
    asyncio.run(classify_and_filter(
        input_path=args.input,
        output_path=intermediate_path,
        config_path=args.config,
        model_name=args.model,
        api_base=args.api_base,
        api_key=args.api_key,
        taxonomy_path=args.taxonomy,
        concurrency=args.concurrency,
        crossdisc_threshold=getattr(args, "crossdisc_threshold", None),
    ))

    # Check if any multidisciplinary papers were found
    line_count = 0
    if os.path.exists(intermediate_path):
        with open(intermediate_path, "r", encoding="utf-8") as f:
            line_count = sum(1 for line in f if line.strip())

    if line_count == 0:
        logger.warning("No multidisciplinary papers found. Skipping extraction.")
        return

    # Phase 2: Extract
    logger.info("=== Phase 2: Extracting hypotheses from %d multidisciplinary papers ===", line_count)
    from crossdisc_extractor.extractor_multi_stage import run_benchmark

    run_benchmark(
        input_path=intermediate_path,
        output_path=args.output,
        max_items=args.max_items,
        sleep_s=args.sleep,
        num_workers=args.num_workers,
        max_tokens_struct=args.max_tokens_struct,
        max_tokens_query=args.max_tokens_query,
        max_tokens_hyp=args.max_tokens_hyp,
        language_mode=args.language_mode,
        resume=args.resume,
    )

    logger.info("=== Full pipeline complete. Output: %s ===", args.output)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _add_classifier_args(parser: argparse.ArgumentParser) -> None:
    """Add classifier-related arguments to a subparser."""
    parser.add_argument("--config", default=None, help="Classifier YAML config file path")
    parser.add_argument("--model", default=None, help="LLM model name (overrides config/env)")
    parser.add_argument("--api-base", default=None, help="LLM API base URL (overrides config/env)")
    parser.add_argument("--api-key", default=None, help="LLM API key (overrides config/env)")
    parser.add_argument("--taxonomy", default=None, help="Taxonomy JSON file path")
    parser.add_argument("--concurrency", type=int, default=None, help="Async classification concurrency")
    parser.add_argument("--crossdisc-threshold", type=float, default=None,
                        help="Cross-disciplinary confidence threshold (0.0-1.0, default=0.5). "
                             "Papers with confidence below this are filtered as non-cross-disciplinary.")


def _add_extractor_args(parser: argparse.ArgumentParser) -> None:
    """Add extractor-related arguments to a subparser."""
    parser.add_argument("--max-items", type=int, default=None, help="Max papers to process")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between items (seconds)")
    parser.add_argument("--num-workers", type=int, default=1, help="Parallel workers for extraction")
    parser.add_argument("--language-mode", choices=["chinese", "original"], default="chinese",
                        help="Output language mode")
    parser.add_argument("--max-tokens-struct", type=int, default=8192, help="Stage1 max tokens")
    parser.add_argument("--max-tokens-query", type=int, default=4096, help="Stage2 max tokens")
    parser.add_argument("--max-tokens-hyp", type=int, default=4096, help="Stage3 max tokens")
    parser.add_argument("--resume", action="store_true", default=True, help="Enable checkpoint/resume")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Disable checkpoint/resume")


def build_parser() -> argparse.ArgumentParser:
    """Build the unified pipeline argument parser."""
    parser = argparse.ArgumentParser(
        prog="crossdisc-pipeline",
        description="Unified cross-disciplinary paper analysis pipeline: classify → filter → extract",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # classify subcommand
    cls_parser = sub.add_parser("classify", help="Classify papers and filter multidisciplinary ones")
    cls_parser.add_argument("--input", "-i", required=True, help="Input JSONL file with papers")
    cls_parser.add_argument("--output", "-o", required=True, help="Output JSONL file (multidisciplinary papers only)")
    _add_classifier_args(cls_parser)

    # extract subcommand
    ext_parser = sub.add_parser("extract", help="Run knowledge extraction on pre-classified data")
    ext_parser.add_argument("--input", "-i", required=True, help="Input file (JSON/JSONL/CSV)")
    ext_parser.add_argument("--output", "-o", required=True, help="Output file (JSONL)")
    _add_extractor_args(ext_parser)

    # full subcommand
    full_parser = sub.add_parser("full", help="Full pipeline: classify → filter → extract")
    full_parser.add_argument("--input", "-i", required=True, help="Input JSONL file with papers")
    full_parser.add_argument("--output", "-o", required=True, help="Final output file (JSONL)")
    full_parser.add_argument("--intermediate", default=None,
                             help="Intermediate classified file path (default: <output>_classified.jsonl)")
    _add_classifier_args(full_parser)
    _add_extractor_args(full_parser)

    return parser


def main() -> None:
    """Entry point for the unified pipeline CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "classify":
        cmd_classify(args)
    elif args.cmd == "extract":
        cmd_extract(args)
    elif args.cmd == "full":
        cmd_full(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

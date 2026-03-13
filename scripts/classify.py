"""Batch classification script: classify papers from JSONL and output CSV."""

import argparse
import asyncio
import csv
import json
import logging
import os
from collections import Counter

from tqdm.asyncio import tqdm_asyncio

from crossdisc_extractor.classifier.config import load_config
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy
from crossdisc_extractor.classifier.prompts.msc_prompt_builder import DisciplinePromptBuilder
from crossdisc_extractor.classifier.hierarchical_async import AsyncHierarchicalClassifier
from crossdisc_extractor.classifier.utils.parsing import (
    extract_discipline_levels,
    extract_main_discipline,
    extract_multidisciplinary,
    levels_from_paths,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CSV_HEADER = [
    "title", "abstract", "introduction", "journal", "field",
    "main_discipline", "main_levels", "non_main_levels", "pdf_url", "status",
]


async def classify_paper(classifier, paper):
    """Classify a single paper and extract structured results."""
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    introduction = paper.get("introduction", "")
    if not title or not abstract:
        return "Unknown", [], [], ["Unknown"], "Unknown"

    result = await classifier.classify_async((title, abstract, introduction))

    # Cross-disciplinary = multiple distinct L1 disciplines in paths
    distinct_l1 = set()
    for path in result.paths:
        if path:
            distinct_l1.add(path[0])
    multi_flag = "Yes" if len(distinct_l1) > 1 else "No"

    main_levels, non_main_levels = levels_from_paths(result.paths, result.raw_outputs)
    main_disc = extract_main_discipline(result.raw_outputs)
    return multi_flag, main_levels, non_main_levels, result.raw_outputs, main_disc


async def run(args) -> None:
    cfg = load_config(args.config, model_name=args.model, api_base=args.api_base, api_key=args.api_key)
    taxo_path = args.taxonomy or cfg.taxonomy_path

    taxonomy = Taxonomy.from_json_file(taxo_path)
    prompt_builder = DisciplinePromptBuilder()
    classifier = AsyncHierarchicalClassifier(taxonomy, prompt_builder, cfg.llm)

    with open(args.input, "r", encoding="utf-8") as f:
        papers = [json.loads(line) for line in f if line.strip()]

    total = len(papers)
    sem = asyncio.Semaphore(cfg.concurrency)
    csv_lock = asyncio.Lock()
    processed_titles: set = set()
    level_counters = {
        "main": {1: Counter(), 2: Counter(), 3: Counter()},
        "non_main": {1: Counter(), 2: Counter(), 3: Counter()},
    }
    main_discipline_counter: Counter = Counter()

    # Initialize or resume CSV
    if not os.path.exists(args.output):
        with open(args.output, "w", encoding="utf-8-sig", newline="") as csvfile:
            csv.writer(csvfile).writerow(CSV_HEADER)
    else:
        with open(args.output, "r", encoding="utf-8-sig") as csvfile:
            for row in csv.DictReader(csvfile):
                processed_titles.add(row["title"])
        logger.info("Resuming: found %d already-processed papers", len(processed_titles))

    async def sem_classify(paper):
        async with sem:
            title = paper.get("title", "")
            if title in processed_titles:
                return None

            multi_flag, main_levels, non_main_levels, raws, main_disc = await classify_paper(
                classifier, paper
            )

            async with csv_lock:
                with open(args.output, "a", encoding="utf-8-sig", newline="") as csvfile:
                    csv.writer(csvfile).writerow([
                        title,
                        paper.get("abstract", ""),
                        paper.get("introduction", ""),
                        paper.get("journal", ""),
                        paper.get("field", ""),
                        main_disc,
                        "; ".join(f"L{lvl}:{name}" for lvl, name in main_levels),
                        "; ".join(f"L{lvl}:{name}" for lvl, name in non_main_levels),
                        paper.get("pdf_url", ""),
                        paper.get("status", ""),
                    ])

            processed_titles.add(title)

            if multi_flag == "Yes":
                for lvl, name in main_levels:
                    level_counters["main"][int(lvl)][name] += 1
                for lvl, name in non_main_levels:
                    level_counters["non_main"][int(lvl)][name] += 1
                if main_disc != "Unknown":
                    main_discipline_counter[main_disc] += 1
                return 1
            return 0

    tasks = [sem_classify(p) for p in papers if p.get("title", "") not in processed_titles]
    total_multi = 0
    for coro in tqdm_asyncio.as_completed(tasks, total=len(tasks)):
        result = await coro
        if result:
            total_multi += result

    # Print statistics
    print(f"\n{'='*50}")
    print(f"Total papers: {total}")
    print(f"Multidisciplinary papers: {total_multi}")
    if total > 0:
        print(f"Multidisciplinary ratio: {total_multi / total:.4f}")

    print(f"\nTop 20 main disciplines:")
    for i, (disc, cnt) in enumerate(main_discipline_counter.most_common(20), 1):
        print(f"  {i}. {disc} - {cnt}")

    for category in ("main", "non_main"):
        label = "Main" if category == "main" else "Non-main"
        print(f"\nTop 20 {label} disciplines by level:")
        for lvl in (1, 2, 3):
            print(f"  Level {lvl}:")
            for i, (name, cnt) in enumerate(level_counters[category][lvl].most_common(20), 1):
                print(f"    {i}. {name} - {cnt}")

    print(f"\nCSV saved to: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch classify papers into discipline hierarchy")
    parser.add_argument("--input", "-i", required=True, help="Input JSONL file")
    parser.add_argument("--output", "-o", required=True, help="Output CSV file")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--taxonomy", default=None, help="Override taxonomy JSON path")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--api-base", default=None, help="Override API base URL")
    parser.add_argument("--api-key", default=None, help="Override API key")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()

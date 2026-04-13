"""Prepare temporal paper datasets from heterogeneous CSV sources.

Examples:
    python scripts/prepare_temporal_papers.py \
        --inputs /ssd/wangyuyang/git/data/raw_data/nature_springer_2023.csv \
                 /ssd/wangyuyang/git/data/raw_data/nature_springer_2024.csv \
        --output benchmark_raw_2023_2024.jsonl \
        --year-lte 2024

    python scripts/prepare_temporal_papers.py \
        --inputs /ssd/wangyuyang/git/data/raw_data/nature_springer_2025.csv \
        --output validity_raw_2025.jsonl \
        --year-eq 2025
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger("prepare_temporal_papers")


STANDARD_COLUMNS = {
    "title": ("title", "display_name"),
    "abstract": ("abstract",),
    "journal": ("journal", "journal_name", "primary_location.source.display_name"),
    "journal_id": ("journal_id", "primary_location.source.id"),
    "issn_l": ("issn_l", "primary_location.source.issn_l"),
    "source_type": ("source_type", "primary_location.source.type"),
    "doi": ("doi",),
    "publication_date": ("publication_date",),
    "publication_year": ("publication_year", "year"),
    "fwci": ("fwci",),
    "cited_by_count": ("cited_by_count",),
    "field": ("field", "topics.field.display_name", "primary_topic.display_name"),
    "pdf_url": ("pdf_url", "best_oa_location.pdf_url", "primary_location.pdf_url"),
}


def _first_present(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and pd.notna(row[key]):
            val = row[key]
            if isinstance(val, str):
                val = val.strip()
                if val:
                    return val
            elif val is not None:
                return val
    return ""


def _to_int(value: Any) -> Optional[int]:
    if value in ("", None):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def normalize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    record: Dict[str, Any] = {}
    for target, candidates in STANDARD_COLUMNS.items():
        record[target] = _first_present(row, candidates)

    record["publication_year"] = _to_int(record.get("publication_year"))
    record["cited_by_count"] = _to_int(record.get("cited_by_count"))
    record["fwci"] = _to_float(record.get("fwci"))

    title = str(record.get("title", "")).strip()
    abstract = str(record.get("abstract", "")).strip()
    if not title or not abstract:
        return None

    record["title"] = title
    record["abstract"] = abstract
    record["journal"] = str(record.get("journal", "")).strip()
    record["field"] = str(record.get("field", "")).strip()
    record["pdf_url"] = str(record.get("pdf_url", "")).strip()
    record["doi"] = str(record.get("doi", "")).strip()
    record["publication_date"] = str(record.get("publication_date", "")).strip()
    record["journal_id"] = str(record.get("journal_id", "")).strip()
    record["issn_l"] = str(record.get("issn_l", "")).strip()
    record["source_type"] = str(record.get("source_type", "")).strip()
    return record


def normalize_journal_name(name: str) -> str:
    return " ".join(str(name or "").strip().casefold().split())


def iter_normalized_records(csv_path: Path) -> Iterable[Dict[str, Any]]:
    logger.info("Reading CSV: %s", csv_path)
    usecols = {candidate for candidates in STANDARD_COLUMNS.values() for candidate in candidates}
    df = pd.read_csv(csv_path, dtype=str, usecols=lambda c: c in usecols)
    for row in df.to_dict(orient="records"):
        record = normalize_row(row)
        if record:
            yield record


def keep_by_year(record: Dict[str, Any], args: argparse.Namespace) -> bool:
    year = record.get("publication_year")
    if year is None:
        return False
    if args.year_eq is not None and year != args.year_eq:
        return False
    if args.year_lte is not None and year > args.year_lte:
        return False
    if args.year_gte is not None and year < args.year_gte:
        return False
    return True


def keep_by_journal(
    record: Dict[str, Any],
    include_journals: Optional[Sequence[str]] = None,
) -> bool:
    if not include_journals:
        return True
    journal = normalize_journal_name(record.get("journal", ""))
    allowed = {normalize_journal_name(name) for name in include_journals if str(name).strip()}
    if not allowed:
        return True
    return journal in allowed


def select_balanced_by_journal(
    records: Sequence[Dict[str, Any]],
    total: int,
    min_per_journal: int,
    seed: int = 42,
    max_journals: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Select records while maximizing journal diversity under a per-journal floor.

    The selector first chooses as many journals as possible with at least
    ``min_per_journal`` records, then allocates ``min_per_journal`` records to
    each selected journal and fills remaining slots by round-robin.
    """
    if total <= 0:
        return [], {"reason": "total <= 0"}
    if min_per_journal <= 0:
        raise ValueError("--balanced-min-per-journal must be > 0")

    rng = random.Random(seed)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        journal = str(record.get("journal", "")).strip() or "(unknown)"
        groups.setdefault(journal, []).append(record)

    for items in groups.values():
        rng.shuffle(items)

    eligible = [(journal, items) for journal, items in groups.items() if len(items) >= min_per_journal]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))

    journal_budget = total // min_per_journal
    if journal_budget <= 0:
        journal_budget = 1
    if max_journals is not None:
        journal_budget = min(journal_budget, max_journals)
    selected_groups = eligible[:journal_budget]

    selected: List[Dict[str, Any]] = []
    selected_by_journal: Dict[str, int] = {}
    used_offsets: Dict[str, int] = {}

    for journal, items in selected_groups:
        take = min(min_per_journal, len(items), total - len(selected))
        if take <= 0:
            break
        selected.extend(items[:take])
        selected_by_journal[journal] = take
        used_offsets[journal] = take

    # Fill remaining capacity round-robin from already selected journals so we
    # keep the journal set stable and retain at least min_per_journal per journal.
    while len(selected) < total and selected_groups:
        progressed = False
        for journal, items in selected_groups:
            offset = used_offsets.get(journal, 0)
            if offset < len(items) and len(selected) < total:
                selected.append(items[offset])
                used_offsets[journal] = offset + 1
                selected_by_journal[journal] = selected_by_journal.get(journal, 0) + 1
                progressed = True
        if not progressed:
            break

    # Best-effort fallback: if selected journals cannot fill the target, add
    # records from remaining journals. This may create journals below the floor,
    # but only when needed to approach the requested total.
    if len(selected) < total:
        already = {journal for journal, _ in selected_groups}
        fallback_groups = [(journal, items) for journal, items in eligible if journal not in already]
        fallback_groups.extend(
            (journal, items)
            for journal, items in groups.items()
            if journal not in already and len(items) < min_per_journal
        )
        fallback_groups.sort(key=lambda item: (-len(item[1]), item[0]))
        for journal, items in fallback_groups:
            for record in items:
                if len(selected) >= total:
                    break
                selected.append(record)
                selected_by_journal[journal] = selected_by_journal.get(journal, 0) + 1
            if len(selected) >= total:
                break

    summary = {
        "input_records": len(records),
        "requested_total": total,
        "selected_total": len(selected),
        "min_per_journal": min_per_journal,
        "seed": seed,
        "eligible_journals": len(eligible),
        "selected_journals": len(selected_by_journal),
        "selected_by_journal": dict(sorted(selected_by_journal.items(), key=lambda item: (-item[1], item[0]))),
        "all_journal_counts_top50": dict(
            sorted(
                ((journal, len(items)) for journal, items in groups.items()),
                key=lambda item: (-item[1], item[0]),
            )[:50]
        ),
    }
    return selected, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare temporal paper datasets from CSV sources")
    parser.add_argument("--inputs", nargs="+", required=True, help="Input CSV paths")
    parser.add_argument("--output", required=True, help="Output path (.json or .jsonl)")
    parser.add_argument("--year-eq", type=int, default=None, help="Keep only records with publication_year == N")
    parser.add_argument("--year-lte", type=int, default=None, help="Keep only records with publication_year <= N")
    parser.add_argument("--year-gte", type=int, default=None, help="Keep only records with publication_year >= N")
    parser.add_argument(
        "--include-journals",
        nargs="+",
        default=None,
        help="Optional exact-match journal whitelist, e.g. --include-journals Nature 'Nature Communications'",
    )
    parser.add_argument(
        "--balanced-total",
        type=int,
        default=None,
        help="If set, select this many records with journal-balanced sampling after filters.",
    )
    parser.add_argument(
        "--balanced-min-per-journal",
        type=int,
        default=5,
        help="Minimum records per selected journal for --balanced-total.",
    )
    parser.add_argument(
        "--balanced-max-journals",
        type=int,
        default=None,
        help="Optional cap on selected journals for --balanced-total.",
    )
    parser.add_argument("--random-seed", type=int, default=42, help="Random seed for balanced sampling")
    parser.add_argument("--balanced-summary", default=None, help="Optional JSON path for balanced sampling summary")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of records to keep")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    records: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for input_path in args.inputs:
        for record in iter_normalized_records(Path(input_path)):
            if not keep_by_year(record, args):
                continue
            if not keep_by_journal(record, args.include_journals):
                continue
            key = f"{record['title']}||{record.get('doi', '')}"
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if args.balanced_total is None and args.limit is not None and len(records) >= args.limit:
                break
        if args.balanced_total is None and args.limit is not None and len(records) >= args.limit:
            break

    balance_summary = None
    if args.balanced_total is not None:
        records, balance_summary = select_balanced_by_journal(
            records,
            total=args.balanced_total,
            min_per_journal=args.balanced_min_per_journal,
            seed=args.random_seed,
            max_journals=args.balanced_max_journals,
        )
        logger.info(
            "Balanced journal sampling selected %d records across %d journals",
            balance_summary["selected_total"],
            balance_summary["selected_journals"],
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".jsonl":
        with output_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    if args.balanced_summary and balance_summary is not None:
        summary_path = Path(args.balanced_summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(balance_summary, f, ensure_ascii=False, indent=2)

    logger.info("Prepared %d records -> %s", len(records), output_path)


if __name__ == "__main__":
    main()

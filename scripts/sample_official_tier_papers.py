"""Sample 2025 papers by external journal quality tiers.

This script intentionally requires an external journal-metrics table, such as a
JCR/CiteScore/SJR/CAS export. It does not derive official tiers from the paper
CSV itself.

Expected external table columns are flexible. The matcher recognizes common
aliases such as:
  journal/source_title/title, issn_l/issn-l/issn, official_tier/tier,
  jif/journal_impact_factor, jif_percentile, jif_quartile,
  citescore, citescore_percentile, citescore_quartile,
  sjr, sjr_quartile, cas_zone.

Two modes are provided:
  prepare-candidates: read raw publisher CSVs and build a tier-balanced
    candidate pool for cross-disciplinary classification.
  sample-classified: read classified cross-disciplinary JSONL and select the
    final balanced sample, for example 5 tiers x 4 journals x 5 papers = 100.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

PROJ_DIR = Path(__file__).resolve().parents[1]
if str(PROJ_DIR) not in sys.path:
    sys.path.insert(0, str(PROJ_DIR))

from scripts.prepare_temporal_papers import STANDARD_COLUMNS, normalize_row


logger = logging.getLogger("sample_official_tier_papers")


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
]


COLUMN_ALIASES = {
    "journal": [
        "journal",
        "journal_name",
        "source_title",
        "source title",
        "title",
        "full_journal_title",
        "full journal title",
        "journal_title",
        "journal title",
        "期刊",
        "期刊名称",
    ],
    "issn_l": ["issn_l", "issn-l", "issn l", "issnl", "issn_l_linking", "issn"],
    "issn": ["issn", "print_issn", "eissn", "electronic_issn", "issn1", "issn2"],
    "official_tier": ["official_tier", "tier", "quality_tier", "journal_tier", "等级", "档次"],
    "jif": ["jif", "journal_impact_factor", "impact_factor", "impact factor", "影响因子"],
    "jif_percentile": [
        "jif_percentile",
        "jif percentile",
        "jif_pct",
        "jcr_percentile",
        "jcr percentile",
    ],
    "jif_quartile": [
        "jif_quartile",
        "jif quartile",
        "jcr_quartile",
        "jcr quartile",
        "quartile",
        "jif_best_quartile",
    ],
    "jci": ["jci", "journal_citation_indicator", "journal citation indicator"],
    "jci_percentile": ["jci_percentile", "jci percentile"],
    "jci_quartile": ["jci_quartile", "jci quartile"],
    "citescore": ["citescore", "cite_score", "cite score"],
    "citescore_percentile": [
        "citescore_percentile",
        "citescore percentile",
        "cite_score_percentile",
        "cite score percentile",
    ],
    "citescore_quartile": [
        "citescore_quartile",
        "citescore quartile",
        "cite_score_quartile",
        "cite score quartile",
    ],
    "sjr": ["sjr", "scimago_journal_rank", "scimago journal rank"],
    "sjr_quartile": ["sjr_quartile", "sjr quartile", "sjr_best_quartile"],
    "cas_zone": ["cas_zone", "cas zone", "中科院分区", "中科院大类分区", "大类分区"],
}


def _norm_col(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", str(name).strip().casefold()).strip("_")


def _norm_journal(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().casefold())


def _norm_issn(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or text.lower() == "nan":
        return ""
    return re.sub(r"[^0-9X]", "", text)


def _split_issns(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return []
    parts = re.split(r"[;,|/\s]+", text)
    return [issn for part in parts if (issn := _norm_issn(part))]


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    num = _to_float(value)
    if num is None or math.isnan(num):
        return None
    return int(num)


def _clean_quartile(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"Q\s*([1-4])", text)
    return f"Q{match.group(1)}" if match else ""


def _percentile(value: Any) -> Optional[float]:
    num = _to_float(value)
    if num is None:
        return None
    if 0 <= num <= 1:
        num *= 100.0
    if 0 <= num <= 100:
        return num
    return None


def _cas_zone(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    match = re.search(r"([1-4])", text)
    return int(match.group(1)) if match else None


def _find_column(columns: Sequence[str], canonical: str) -> Optional[str]:
    norm_to_original = {_norm_col(col): col for col in columns}
    for alias in COLUMN_ALIASES.get(canonical, []):
        norm = _norm_col(alias)
        if norm in norm_to_original:
            return norm_to_original[norm]
    return None


def _derive_tier(row: Dict[str, Any]) -> Tuple[Optional[int], str, Optional[float]]:
    explicit = _to_int(row.get("official_tier"))
    if explicit is not None and 0 <= explicit <= 5:
        return explicit, "official_tier", None

    percentiles = [
        p
        for key in ("jif_percentile", "jci_percentile", "citescore_percentile")
        if (p := _percentile(row.get(key))) is not None
    ]
    if percentiles:
        p = max(percentiles)
        if p >= 90:
            return 5, "percentile>=90", p
        if p >= 75:
            return 4, "percentile>=75", p
        if p >= 50:
            return 3, "percentile>=50", p
        if p >= 25:
            return 2, "percentile>=25", p
        return 1, "percentile<25", p

    zone = _cas_zone(row.get("cas_zone"))
    if zone is not None:
        return {1: 5, 2: 4, 3: 2, 4: 1}.get(zone), "cas_zone", None

    quartiles = [
        _clean_quartile(row.get(key))
        for key in ("jif_quartile", "jci_quartile", "citescore_quartile", "sjr_quartile")
    ]
    quartiles = [q for q in quartiles if q]
    if quartiles:
        best = min(int(q[1]) for q in quartiles)
        return {1: 4, 2: 3, 3: 2, 4: 1}[best], "quartile", None

    return None, "unmatched", None


class OfficialJournalMatcher:
    def __init__(self, official_csv: str):
        self.official_csv = official_csv
        self.by_issn: Dict[str, Dict[str, Any]] = {}
        self.by_journal: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        path = Path(self.official_csv)
        if not path.exists():
            raise FileNotFoundError(f"Official journal metrics CSV not found: {path}")

        df = pd.read_csv(path, dtype=str)
        if df.empty:
            raise ValueError(f"Official journal metrics CSV is empty: {path}")

        colmap = {key: _find_column(df.columns, key) for key in COLUMN_ALIASES}
        if not colmap.get("journal") and not colmap.get("issn_l") and not colmap.get("issn"):
            raise ValueError(
                "Official CSV must contain at least one journal or ISSN column. "
                f"Detected columns: {list(df.columns)}"
            )

        matched_rows = 0
        for raw in df.to_dict(orient="records"):
            row: Dict[str, Any] = {}
            for key, col in colmap.items():
                if col:
                    row[key] = raw.get(col, "")

            tier, tier_source, percentile = _derive_tier(row)
            if tier is None or tier <= 0:
                continue

            metric = {
                "official_tier": tier,
                "official_tier_source": tier_source,
                "official_journal": str(row.get("journal") or "").strip(),
                "official_issn_l": str(row.get("issn_l") or row.get("issn") or "").strip(),
                "official_quality_percentile": percentile,
            }
            for key in OFFICIAL_FIELDS:
                if key in metric:
                    continue
                value = row.get(key)
                if key.endswith("quartile"):
                    metric[key] = _clean_quartile(value)
                elif key == "cas_zone":
                    metric[key] = _cas_zone(value)
                elif key in {"jif", "jif_percentile", "jci", "jci_percentile", "citescore", "citescore_percentile", "sjr"}:
                    metric[key] = _to_float(value)
                else:
                    metric[key] = value

            issns = []
            for key in ("issn_l", "issn"):
                issns.extend(_split_issns(row.get(key)))
            for issn in set(issns):
                self.by_issn.setdefault(issn, metric)

            journal_key = _norm_journal(metric["official_journal"])
            if journal_key:
                self.by_journal.setdefault(journal_key, metric)

            matched_rows += 1

        logger.info(
            "Loaded official journal metrics: %d tiered rows, %d ISSN keys, %d journal-name keys",
            matched_rows,
            len(self.by_issn),
            len(self.by_journal),
        )
        if matched_rows == 0:
            raise ValueError("No rows in official CSV could be assigned to official_tier 1-5")

    def match(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for issn in _split_issns(record.get("issn_l")):
            if issn in self.by_issn:
                return dict(self.by_issn[issn])
        journal_key = _norm_journal(record.get("journal"))
        if journal_key and journal_key in self.by_journal:
            return dict(self.by_journal[journal_key])
        return None


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


def _read_raw_records(
    inputs: Sequence[str],
    year: int,
    matcher: OfficialJournalMatcher,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()
    stats = {
        "raw_rows_seen": 0,
        "normalized_records": 0,
        "journal_records": 0,
        "official_matched_records": 0,
        "by_input": {},
        "unmatched_journals_top50": {},
    }
    unmatched_counts: Dict[str, int] = defaultdict(int)
    usecols = {candidate for candidates in STANDARD_COLUMNS.values() for candidate in candidates}

    for input_path in inputs:
        path = Path(input_path)
        label = path.stem
        stats["by_input"][label] = {"raw_rows_seen": 0, "official_matched_records": 0}
        for chunk in pd.read_csv(path, dtype=str, usecols=lambda col: col in usecols, chunksize=100000):
            stats["raw_rows_seen"] += len(chunk)
            stats["by_input"][label]["raw_rows_seen"] += len(chunk)
            for raw in chunk.to_dict(orient="records"):
                rec = normalize_row(raw)
                if not rec:
                    continue
                stats["normalized_records"] += 1
                if rec.get("publication_year") != year:
                    continue
                if str(rec.get("source_type", "")).strip().casefold() != "journal":
                    continue
                stats["journal_records"] += 1
                metric = matcher.match(rec)
                if not metric:
                    unmatched_counts[rec.get("journal", "")] += 1
                    continue
                rec.update(metric)
                rec["publisher_source"] = label
                key = f"{rec.get('doi','')}||{rec.get('title','')}"
                if key in seen:
                    continue
                seen.add(key)
                records.append(rec)
                stats["official_matched_records"] += 1
                stats["by_input"][label]["official_matched_records"] += 1

    stats["unmatched_journals_top50"] = dict(
        sorted(unmatched_counts.items(), key=lambda item: (-item[1], item[0]))[:50]
    )
    return records, stats


def _sample_by_tier_and_journal(
    records: Sequence[Dict[str, Any]],
    tiers: Sequence[int],
    target_per_tier: int,
    journals_per_tier: int,
    papers_per_journal: int,
    seed: int,
    strict: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rng = random.Random(seed)
    selected: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "requested": {
            "tiers": list(tiers),
            "target_per_tier": target_per_tier,
            "journals_per_tier": journals_per_tier,
            "papers_per_journal": papers_per_journal,
            "seed": seed,
            "strict": strict,
        },
        "tiers": {},
    }

    by_tier_journal: Dict[int, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        tier = _to_int(rec.get("official_tier"))
        journal = str(rec.get("journal", "")).strip() or "(unknown)"
        if tier in tiers:
            by_tier_journal[tier][journal].append(dict(rec))

    for tier in tiers:
        groups = by_tier_journal.get(tier, {})
        for rows in groups.values():
            rng.shuffle(rows)
        eligible = [(journal, rows) for journal, rows in groups.items() if len(rows) >= papers_per_journal]
        rng.shuffle(eligible)
        eligible.sort(key=lambda item: (-len(item[1]), item[0]))
        chosen = eligible[:journals_per_tier]

        tier_rows: List[Dict[str, Any]] = []
        by_journal: Dict[str, int] = {}
        for journal, rows in chosen:
            take = min(papers_per_journal, len(rows))
            tier_rows.extend(rows[:take])
            by_journal[journal] = take

        if len(tier_rows) < target_per_tier and not strict:
            already = {journal for journal, _ in chosen}
            fallback = [(journal, rows) for journal, rows in groups.items() if journal not in already]
            fallback.sort(key=lambda item: (-len(item[1]), item[0]))
            for journal, rows in fallback:
                for rec in rows:
                    if len(tier_rows) >= target_per_tier:
                        break
                    tier_rows.append(rec)
                    by_journal[journal] = by_journal.get(journal, 0) + 1
                if len(tier_rows) >= target_per_tier:
                    break

        if strict and len(tier_rows) < target_per_tier:
            raise SystemExit(
                f"Tier {tier} only produced {len(tier_rows)} records; need {target_per_tier}. "
                "Increase candidate pool or relax --strict."
            )

        selected.extend(tier_rows[:target_per_tier])
        summary["tiers"][str(tier)] = {
            "available_journals": len(groups),
            "eligible_journals": len(eligible),
            "selected_records": len(tier_rows[:target_per_tier]),
            "selected_journals": len(by_journal),
            "selected_by_journal": dict(sorted(by_journal.items(), key=lambda item: (-item[1], item[0]))),
            "top_available_journal_counts": dict(
                sorted(((j, len(r)) for j, r in groups.items()), key=lambda item: (-item[1], item[0]))[:30]
            ),
        }

    summary["selected_total"] = len(selected)
    summary["selected_by_tier"] = {
        str(tier): sum(1 for row in selected if _to_int(row.get("official_tier")) == tier)
        for tier in tiers
    }
    return selected, summary


def _parse_tiers(values: Sequence[str]) -> List[int]:
    tiers = []
    for value in values:
        for part in str(value).split(","):
            if part.strip():
                tiers.append(int(part))
    return sorted(set(tiers), reverse=True)


def _save_summary(path: str, summary: Dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_prepare_candidates(args: argparse.Namespace) -> None:
    matcher = OfficialJournalMatcher(args.official_journals)
    records, stats = _read_raw_records(args.inputs, args.year, matcher)
    tiers = _parse_tiers(args.tiers)
    selected, sample_summary = _sample_by_tier_and_journal(
        records=records,
        tiers=tiers,
        target_per_tier=args.candidate_per_tier,
        journals_per_tier=args.journals_per_tier,
        papers_per_journal=args.papers_per_journal,
        seed=args.seed,
        strict=args.strict,
    )
    _write_jsonl(args.output, selected)
    summary = {
        "mode": "prepare-candidates",
        "inputs": args.inputs,
        "official_journals": args.official_journals,
        "read_stats": stats,
        "sampling": sample_summary,
    }
    _save_summary(args.summary, summary)
    logger.info("Prepared %d official-tier candidate records -> %s", len(selected), args.output)


def cmd_sample_classified(args: argparse.Namespace) -> None:
    matcher = OfficialJournalMatcher(args.official_journals)
    records = []
    unmatched = 0
    for rec in _read_jsonl(args.input):
        metric = matcher.match(rec)
        if not metric:
            unmatched += 1
            continue
        enriched = dict(rec)
        enriched.update(metric)
        records.append(enriched)

    tiers = _parse_tiers(args.tiers)
    selected, sample_summary = _sample_by_tier_and_journal(
        records=records,
        tiers=tiers,
        target_per_tier=args.target_per_tier,
        journals_per_tier=args.journals_per_tier,
        papers_per_journal=args.papers_per_journal,
        seed=args.seed,
        strict=args.strict,
    )
    _write_jsonl(args.output, selected)
    summary = {
        "mode": "sample-classified",
        "input": args.input,
        "official_journals": args.official_journals,
        "classified_records": len(_read_jsonl(args.input)),
        "official_matched_records": len(records),
        "official_unmatched_records": unmatched,
        "sampling": sample_summary,
    }
    _save_summary(args.summary, summary)
    logger.info("Selected %d final official-tier records -> %s", len(selected), args.output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--official-journals", required=True, help="JCR/CiteScore/SJR/CAS CSV with official tiers or metrics")
    common.add_argument("--tiers", nargs="+", default=["5", "4", "3", "2", "1"], help="Tiers to sample")
    common.add_argument("--seed", type=int, default=42)
    common.add_argument("--strict", action="store_true", help="Fail if any tier cannot satisfy its quota")
    common.add_argument("--summary", required=True, help="Output summary JSON")
    common.add_argument("--output", required=True, help="Output JSONL")

    p0 = sub.add_parser("prepare-candidates", parents=[common])
    p0.add_argument("--inputs", nargs="+", required=True, help="Raw publisher CSVs")
    p0.add_argument("--year", type=int, default=2025)
    p0.add_argument("--candidate-per-tier", type=int, default=200)
    p0.add_argument("--journals-per-tier", type=int, default=10)
    p0.add_argument("--papers-per-journal", type=int, default=20)
    p0.set_defaults(func=cmd_prepare_candidates)

    p1 = sub.add_parser("sample-classified", parents=[common])
    p1.add_argument("--input", required=True, help="Classified cross-disciplinary JSONL")
    p1.add_argument("--target-per-tier", type=int, default=20)
    p1.add_argument("--journals-per-tier", type=int, default=4)
    p1.add_argument("--papers-per-journal", type=int, default=5)
    p1.set_defaults(func=cmd_sample_classified)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

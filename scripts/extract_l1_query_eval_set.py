"""Extract L1-only query-centric evaluation rows from classified papers.

This script is intentionally lighter than ``run.py batch``: it does not extract
L2/L3 queries, relations, or benchmark hypotheses. It only asks the LLM for one
macro-level research query per cross-disciplinary paper, then writes the same
query-eval JSON shape consumed by ``run_query_benchmark.py``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from crossdisc_extractor.utils import llm as llm_utils


logger = logging.getLogger("extract_l1_query_eval_set")


SYSTEM_PROMPT = """你是一名跨学科科研问题抽取专家。
你的任务是基于论文标题、摘要和学科信息，提取一个适合后续科研假设生成的 L1 层级宏观 query。

要求：
1. 只输出 JSON，不要解释。
2. query 应体现论文核心问题、主学科与辅学科之间的跨学科连接。
3. query 应是开放式科研问题，而不是简单复述论文标题。
4. query 应适合让大模型基于它生成新的科学假设。
5. 使用中文输出。

JSON 格式：
{
  "L1_query": "..."
}
"""


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _paper_id(row: Dict[str, Any]) -> str:
    doi = str(row.get("doi") or "").strip()
    title = str(row.get("title") or "").strip()
    key = doi or title
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                obj = json.loads(match.group(0))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
    return {}


def _fallback_query(row: Dict[str, Any]) -> str:
    title = str(row.get("title") or "").strip()
    primary = str(row.get("primary") or "").strip()
    secondary = row.get("secondary_list") or []
    if isinstance(secondary, str):
        secondary_text = secondary
    else:
        secondary_text = "、".join(str(x) for x in secondary if str(x).strip())
    if primary or secondary_text:
        return f"围绕论文《{title}》，如何整合{primary or '主学科'}与{secondary_text or '相关辅学科'}的方法或机制提出新的跨学科科学假设？"
    return f"围绕论文《{title}》，可以提出哪些具有新颖性、可验证性和跨学科价值的科学假设？"


def _build_user_prompt(row: Dict[str, Any]) -> str:
    secondary = row.get("secondary_list") or []
    if isinstance(secondary, list):
        secondary_text = "、".join(str(x) for x in secondary if str(x).strip())
    else:
        secondary_text = str(secondary or "")
    abstract = str(row.get("abstract") or "").strip()
    if len(abstract) > 3000:
        abstract = abstract[:3000]
    return "\n".join(
        [
            f"论文标题: {row.get('title', '')}",
            f"期刊: {row.get('journal', '')}",
            f"主学科: {row.get('primary', '')}",
            f"辅学科: {secondary_text}",
            f"跨学科评分: {row.get('crossdisc_score', '')}",
            f"跨学科理由: {row.get('crossdisc_reason', '')}",
            "",
            "摘要:",
            abstract,
            "",
            "请抽取一个 L1 层级宏观 query。",
        ]
    )


def _call_l1_query(row: Dict[str, Any], temperature: float, max_tokens: int) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(row)},
    ]
    raw = llm_utils.chat_completion_with_retry(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    obj = _extract_json(raw)
    query = str(obj.get("L1_query") or obj.get("query") or "").strip()
    return query or _fallback_query(row)


def _to_query_eval_row(row: Dict[str, Any], query: str) -> Dict[str, Any]:
    secondary = row.get("secondary_list") or []
    if isinstance(secondary, str):
        secondary = [x.strip() for x in re.split(r"[,，;；]", secondary) if x.strip()]
    return {
        "paper_id": _paper_id(row),
        "title": row.get("title", ""),
        "abstract": row.get("abstract", ""),
        "primary_discipline": row.get("primary", ""),
        "secondary_disciplines": secondary,
        "queries": {
            "L1": query,
            "L2": [],
            "L3": [],
        },
        "gt_terms": [],
        "gt_relations": [],
        "metadata": {
            "journal": row.get("journal", ""),
            "journal_id": row.get("journal_id", ""),
            "issn_l": row.get("issn_l", ""),
            "source_type": row.get("source_type", ""),
            "doi": row.get("doi", ""),
            "publication_date": row.get("publication_date", ""),
            "publication_year": row.get("publication_year"),
            "fwci": row.get("fwci"),
            "cited_by_count": row.get("cited_by_count"),
            "field": row.get("field", ""),
            "crossdisc_score": row.get("crossdisc_score"),
            "crossdisc_reason": row.get("crossdisc_reason", ""),
            "main_levels": row.get("main_levels", ""),
            "non_main_levels": row.get("non_main_levels", ""),
        },
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "paper_id",
        "title",
        "journal",
        "doi",
        "primary_discipline",
        "secondary_disciplines",
        "L1_query",
        "crossdisc_score",
        "cited_by_count",
        "field",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            meta = row.get("metadata") or {}
            writer.writerow(
                {
                    "paper_id": row.get("paper_id", ""),
                    "title": row.get("title", ""),
                    "journal": meta.get("journal", ""),
                    "doi": meta.get("doi", ""),
                    "primary_discipline": row.get("primary_discipline", ""),
                    "secondary_disciplines": "; ".join(row.get("secondary_disciplines") or []),
                    "L1_query": (row.get("queries") or {}).get("L1", ""),
                    "crossdisc_score": meta.get("crossdisc_score", ""),
                    "cited_by_count": meta.get("cited_by_count", ""),
                    "field": meta.get("field", ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Classified cross-disciplinary JSONL")
    parser.add_argument("--output", required=True, help="Output query-eval JSON")
    parser.add_argument("--output-jsonl", default=None, help="Optional JSONL mirror")
    parser.add_argument("--output-csv", default=None, help="Optional CSV table")
    parser.add_argument("--summary", default=None, help="Optional summary JSON")
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--model", default=None, help="Optional model for L1 query extraction")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--resume", action="store_true", help="Reuse existing output rows by paper_id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.model:
        llm_utils.MODEL_NAME = args.model

    rows = list(_read_jsonl(Path(args.input)))
    if args.max_items is not None:
        rows = rows[: args.max_items]

    existing_by_id: Dict[str, Dict[str, Any]] = {}
    out_path = Path(args.output)
    if args.resume and out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                existing_by_id = {str(x.get("paper_id")): x for x in existing if x.get("paper_id")}
        except Exception:
            existing_by_id = {}

    output_rows: List[Dict[str, Any]] = []
    failures = 0
    for i, row in enumerate(rows, start=1):
        pid = _paper_id(row)
        if pid in existing_by_id:
            output_rows.append(existing_by_id[pid])
            logger.info("[%d/%d] cache hit: %s", i, len(rows), row.get("title", "")[:80])
            continue
        try:
            query = _call_l1_query(row, temperature=args.temperature, max_tokens=args.max_tokens)
            logger.info("[%d/%d] L1 query extracted: %s", i, len(rows), row.get("title", "")[:80])
        except Exception as exc:
            failures += 1
            logger.warning("[%d/%d] L1 query extraction failed, fallback used: %s", i, len(rows), exc)
            query = _fallback_query(row)
        output_rows.append(_to_query_eval_row(row, query))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.output_jsonl:
        jsonl_path = Path(args.output_jsonl)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("w", encoding="utf-8") as f:
            for row in output_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.output_csv:
        _write_csv(Path(args.output_csv), output_rows)

    summary = {
        "input": args.input,
        "output": args.output,
        "model": args.model or llm_utils.MODEL_NAME,
        "input_records": len(rows),
        "output_records": len(output_rows),
        "failed_with_fallback": failures,
        "nonempty_l1_queries": sum(1 for row in output_rows if ((row.get("queries") or {}).get("L1") or "").strip()),
    }
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d L1 query-eval rows -> %s", len(output_rows), out_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

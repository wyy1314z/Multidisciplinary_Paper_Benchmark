"""Extract L1 query-only benchmark rows from classified cross-disciplinary papers."""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crossdisc_extractor.utils import llm as llm_utils


logger = logging.getLogger("extract_l1_queries")


SYSTEM_PROMPT = """你是一名跨学科科研问题设计专家。
请根据论文题目、摘要、主学科和辅助学科，抽取一个 L1 层级的宏观研究 query。

要求：
1. L1 query 必须是一个宽口径、跨学科的研究问题。
2. 只输出一个问题，不输出 L2/L3，不输出假设。
3. 问题应覆盖主学科和至少一个辅助学科的交叉点。
4. 使用中文输出，除非用户明确要求保留原文语言。
5. 严格输出 JSON：{"L1_query": "..."}
"""


def _paper_id(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _load_items(path: str) -> List[Dict[str, Any]]:
    src = Path(path)
    if src.suffix.lower() == ".jsonl":
        return list(_iter_jsonl(src))
    with src.open(encoding="utf-8") as f:
        return json.load(f)


def _load_existing_rows(*paths: Path) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            if path.suffix.lower() == ".jsonl":
                loaded = list(_iter_jsonl(path))
            else:
                with path.open(encoding="utf-8") as f:
                    loaded = json.load(f)
        except Exception as exc:
            logger.warning("Could not read existing rows from %s: %s", path, exc)
            continue
        if isinstance(loaded, dict):
            loaded = loaded.get("items", [])
        for row in loaded or []:
            if not isinstance(row, dict):
                continue
            if row.get("ok") is False:
                continue
            pid = str(row.get("paper_id") or "").strip()
            query = ((row.get("queries") or {}).get("L1") or "").strip()
            if pid and query:
                rows[pid] = row
    return rows


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    candidates.append(text)
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _parse_l1_query(text: str) -> str:
    obj = _extract_json_object(text)
    if obj:
        value = obj.get("L1_query") or obj.get("l1_query") or obj.get("query") or obj.get("一级")
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Fallback: keep the first question-like line if the model ignored JSON.
    for line in text.splitlines():
        line = line.strip().strip("-* ")
        if line and ("?" in line or "？" in line):
            return line
    return text.strip()


def _metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "journal": item.get("journal", ""),
        "journal_id": item.get("journal_id", ""),
        "issn_l": item.get("issn_l", ""),
        "source_type": item.get("source_type", ""),
        "doi": item.get("doi", ""),
        "publication_date": item.get("publication_date", ""),
        "publication_year": item.get("publication_year"),
        "fwci": item.get("fwci"),
        "cited_by_count": item.get("cited_by_count"),
        "field": item.get("field", ""),
        "crossdisc_score": item.get("crossdisc_score"),
        "crossdisc_reason": item.get("crossdisc_reason", ""),
    }


def _build_prompt(item: Dict[str, Any], language_mode: str) -> str:
    secondary_list = item.get("secondary_list") or []
    if not secondary_list and item.get("secondary"):
        secondary_list = [
            s.strip()
            for s in re.split(r"[,，;；]", str(item.get("secondary", "")))
            if s.strip()
        ]
    language_instruction = (
        "请使用中文输出。"
        if language_mode == "chinese"
        else "请优先使用论文原始语言输出；如果原文为英文，则输出英文 query。"
    )
    return "\n".join(
        [
            f"题目: {item.get('title', '')}",
            f"主学科: {item.get('primary', '')}",
            f"辅助学科: {', '.join(secondary_list) or '未提供'}",
            f"摘要: {item.get('abstract', '')}",
            "",
            language_instruction,
            "请抽取一个 L1 层级 query，并严格返回 JSON。",
        ]
    )


def _extract_one(item: Dict[str, Any], input_index: int, language_mode: str, max_tokens: int) -> Dict[str, Any]:
    title = str(item.get("title", "")).strip()
    pid = _paper_id(title)
    secondary_list = item.get("secondary_list") or []
    if not secondary_list and item.get("secondary"):
        secondary_list = [
            s.strip()
            for s in re.split(r"[,，;；]", str(item.get("secondary", "")))
            if s.strip()
        ]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_prompt(item, language_mode)},
    ]
    raw = llm_utils.chat_completion_with_retry(messages, temperature=0.1, max_tokens=max_tokens)
    query = _parse_l1_query(raw)
    if not query:
        raise RuntimeError("empty L1 query")

    return {
        "paper_id": pid,
        "input_index": input_index,
        "title": title,
        "abstract": item.get("abstract", ""),
        "primary_discipline": item.get("primary", ""),
        "secondary_disciplines": secondary_list,
        "queries": {
            "L1": query,
            "L2": [],
            "L3": [],
        },
        "gt_terms": [],
        "gt_relations": [],
        "metadata": _metadata(item),
        "l1_query_model": llm_utils.MODEL_NAME,
        "raw_l1_query_response": raw,
    }


def _write_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract L1-only query eval rows from classified papers")
    parser.add_argument("--input", required=True, help="Classified cross-disciplinary papers JSON/JSONL")
    parser.add_argument("--output", required=True, help="Final sorted query eval JSON output")
    parser.add_argument("--checkpoint", default=None, help="Append-only success checkpoint JSONL")
    parser.add_argument("--errors-output", default=None, help="Append-only error JSONL")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL") or llm_utils.MODEL_NAME)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--language-mode", choices=["chinese", "original"], default="chinese")
    parser.add_argument("--resume", action="store_true", help="Reuse existing output/checkpoint rows")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    llm_utils.MODEL_NAME = args.model

    items = _load_items(args.input)
    if args.max_items is not None:
        items = items[: args.max_items]

    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint or f"{args.output}.checkpoint.jsonl")
    errors_path = Path(args.errors_output or f"{args.output}.errors.jsonl")

    existing: Dict[str, Dict[str, Any]] = {}
    if args.resume:
        existing = _load_existing_rows(output_path, checkpoint_path)
        logger.info("Loaded %d existing successful rows for resume", len(existing))

    indexed_items: List[tuple[int, Dict[str, Any]]] = []
    for idx, item in enumerate(items):
        pid = _paper_id(str(item.get("title", "")).strip())
        if args.resume and pid in existing:
            continue
        indexed_items.append((idx, item))

    logger.info(
        "Extracting L1 queries: total=%d existing=%d remaining=%d model=%s",
        len(items),
        len(existing),
        len(indexed_items),
        llm_utils.MODEL_NAME,
    )

    new_rows: Dict[str, Dict[str, Any]] = {}
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.parent.mkdir(parents=True, exist_ok=True)

    if indexed_items:
        with checkpoint_path.open("a", encoding="utf-8") as ckpt, errors_path.open("a", encoding="utf-8") as err_f:
            with futures.ThreadPoolExecutor(max_workers=max(1, args.num_workers)) as executor:
                fut_to_idx = {
                    executor.submit(_extract_one, item, idx, args.language_mode, args.max_tokens): (idx, item)
                    for idx, item in indexed_items
                }
                for done_idx, fut in enumerate(futures.as_completed(fut_to_idx), start=1):
                    idx, item = fut_to_idx[fut]
                    title = str(item.get("title", "")).strip()
                    pid = _paper_id(title)
                    try:
                        row = fut.result()
                    except Exception as exc:
                        logger.warning("[%d/%d] failed: %s | %s", done_idx, len(indexed_items), title[:80], exc)
                        err_f.write(
                            json.dumps(
                                {
                                    "paper_id": pid,
                                    "input_index": idx,
                                    "title": title,
                                    "error": str(exc),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        err_f.flush()
                        continue
                    new_rows[pid] = row
                    ckpt.write(json.dumps(row, ensure_ascii=False) + "\n")
                    ckpt.flush()
                    logger.info("[%d/%d] ok: %s", done_idx, len(indexed_items), title[:80])

    by_pid = {**existing, **new_rows}
    sorted_rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        pid = _paper_id(str(item.get("title", "")).strip())
        row = by_pid.get(pid)
        if row:
            row.setdefault("input_index", idx)
            sorted_rows.append(row)

    _write_json(output_path, sorted_rows)
    logger.info("Saved %d L1 query rows -> %s", len(sorted_rows), output_path)


if __name__ == "__main__":
    main()

"""Generate free-text hypotheses from query-centric evaluation inputs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from crossdisc_extractor.utils import llm as llm_utils


logger = logging.getLogger("run_query_benchmark")


SYSTEM_PROMPT_LAYERED = """你是一名擅长交叉学科科研假设生成的专家。
请根据给定的研究 query，生成具有科学性、可行性和新颖性的研究假设。

输出要求：
1. 优先给出分层假设，使用 [L1]、[L2]、[L3] 标记不同层次。
2. 每个层次尽量写成 1-3 条清晰的推理链式假设。
3. 每条假设要包含关键实体、作用关系和预期机制。
4. 使用自然语言即可，不必输出 JSON。
5. 不要解释你的思考过程，不要输出额外前言。
"""


SYSTEM_PROMPT_L1_SINGLE = """你是一名擅长交叉学科科研假设生成的专家。
请根据给定的 L1 research query，生成具有科学性、可行性和新颖性的顶层科研假设。

输出要求：
1. 只输出 1 条 [L1] 层级的科研假设，不要输出 [L2] 或 [L3]。
2. 该假设必须是一个完整的顶层假设，不能写成多个编号假设或多个并列假设。
3. 假设必须围绕同一个核心因果链或机制链展开。
4. 必须包含关键实体和作用关系。
5. 不要输出推理过程、解释文字、Markdown 代码块或 JSON。

输出格式：
[L1] 假设：<一条完整的顶层科研假设>
关键实体：<实体1、实体2、实体3>
作用关系：<一句话描述实体之间的作用关系>
"""


SYSTEM_PROMPT_SINGLE_LEVEL = """你是一名擅长交叉学科科研假设生成的专家。
请根据给定的 research query，生成与指定层级严格对应的一条科研假设。

输出要求：
1. 只输出 1 条与指定层级完全对应的科研假设。
2. 只输出当前层级，不要输出其他层级内容。
3. 该假设必须是一个完整的单条假设，不能写成多个编号假设或多个并列假设。
4. 假设必须围绕同一个核心因果链或机制链展开。
5. 必须包含关键实体和作用关系。
6. 不要输出推理过程、解释文字、Markdown 代码块或 JSON。

输出格式：
[<LEVEL>] 假设：<一条完整的科研假设>
关键实体：<实体1、实体2、实体3>
作用关系：<一句话描述实体之间的作用关系>
"""


def _resolve_hypothesis_format(prompt_level: str, hypothesis_format: str) -> str:
    if hypothesis_format != "auto":
        return hypothesis_format
    return "l1_single" if prompt_level == "L1" else "layered"


def _system_prompt_for(prompt_level: str, hypothesis_format: str) -> str:
    if hypothesis_format == "l1_single":
        return SYSTEM_PROMPT_L1_SINGLE
    if hypothesis_format == "single_level":
        return SYSTEM_PROMPT_SINGLE_LEVEL.replace("<LEVEL>", prompt_level)
    return SYSTEM_PROMPT_LAYERED


def _load_queries(path: str) -> List[Dict[str, Any]]:
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


def _load_existing_results(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _get_queries(item: Dict[str, Any]) -> Dict[str, Any]:
    queries = item.get("queries")
    if isinstance(queries, dict):
        return queries
    query = item.get("query")
    if isinstance(query, dict):
        return query
    return {}


def _as_query_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if value:
        return [str(value)]
    return []


def _paper_id_for(item: Dict[str, Any]) -> str:
    return str(item.get("paper_id") or item.get("doi") or item.get("title") or "")


def _metadata_for(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    keys = (
        "journal",
        "doi",
        "publication_date",
        "publication_year",
        "primary_discipline",
        "secondary_disciplines",
    )
    return {key: item.get(key) for key in keys if key in item}


def _build_user_prompt(item: Dict[str, Any], prompt_level: str, hypothesis_format: str) -> str:
    queries = _get_queries(item)
    primary = item.get("primary_discipline", "")
    secondary = ", ".join(item.get("secondary_disciplines", []))
    title = item.get("title", "")

    lines = [
        f"论文标题: {title}",
        f"主学科: {primary}",
        f"辅助学科: {secondary or '（未提供）'}",
    ]
    if prompt_level == "L1":
        lines.append(f"L1 Query: {queries.get('L1', '')}")
    elif prompt_level == "L2":
        lines.append(f"L1 Query: {queries.get('L1', '')}")
        lines.append("L2 Queries:")
        for q in _as_query_list(queries.get("L2")):
            lines.append(f"- {q}")
    elif prompt_level == "L3":
        lines.append(f"L1 Query: {queries.get('L1', '')}")
        lines.append("L3 Queries:")
        for q in _as_query_list(queries.get("L3")):
            lines.append(f"- {q}")
    else:
        lines.append(f"L1 Query: {queries.get('L1', '')}")
        lines.append("L2 Queries:")
        for q in _as_query_list(queries.get("L2")):
            lines.append(f"- {q}")
        lines.append("L3 Queries:")
        for q in _as_query_list(queries.get("L3")):
            lines.append(f"- {q}")

    lines.append("")
    if hypothesis_format == "l1_single":
        lines.append(
            "请只基于上述 L1 Query 生成 1 条 [L1] 层级科研假设；"
            "不要输出 [L2] 或 [L3]，不要编号，不要分条。"
        )
    elif hypothesis_format == "single_level":
        if prompt_level == "L1":
            lines.append(
                "请只基于上述 L1 Query 生成 1 条 [L1] 层级科研假设；"
                "不要输出 [L2] 或 [L3]，不要编号，不要分条。"
            )
        elif prompt_level == "L2":
            lines.append(
                "请只基于上述 L2 Query 生成 1 条 [L2] 层级科研假设；"
                "不要输出 [L1] 或 [L3]，不要编号，不要分条。"
            )
        elif prompt_level == "L3":
            lines.append(
                "请只基于上述 L3 Query 生成 1 条 [L3] 层级科研假设；"
                "不要输出 [L1] 或 [L2]，不要编号，不要分条。"
            )
        else:
            lines.append("请只生成与指定层级严格对应的单条科研假设。")
    else:
        lines.append("请基于上述 query 生成分层科研假设。")
    return "\n".join(lines)


def _sanitize_model_name(model_name: str) -> str:
    return model_name.replace("/", "_").replace(":", "_")


def _looks_like_unavailable_model_error(error: str) -> bool:
    normalized = error.lower()
    markers = (
        "无可用渠道",
        "no available channel",
        "no longer available",
        "model_not_found",
        "model not found",
        "does not exist",
        "invalid model",
        "unsupported model",
        "not supported",
    )
    return any(marker in normalized for marker in markers)


def _normalize_result_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "paper_id": str(row.get("paper_id", "")),
        "method_name": row.get("method_name", ""),
        "prompt_level": row.get("prompt_level", ""),
        "hypothesis_format": row.get("hypothesis_format", ""),
        "query": row.get("query", ""),
        "free_text_hypotheses": row.get("free_text_hypotheses", []) or [],
        "error": row.get("error", ""),
        "metadata": row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate hypotheses for query-centric benchmark evaluation")
    parser.add_argument("--input", required=True, help="Query eval JSON built by build_query_eval_set.py")
    parser.add_argument("--output-dir", required=True, help="Output directory for model result JSON files")
    parser.add_argument("--models", required=True, help="Comma-separated model names")
    parser.add_argument("--prompt-level", choices=["L1", "L2", "L3", "all"], default="L1")
    parser.add_argument(
        "--hypothesis-format",
        choices=["auto", "l1_single", "single_level", "layered"],
        default="auto",
        help="auto uses l1_single for --prompt-level L1 and layered otherwise",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-items", type=int, default=None, help="Generate only the first N queries")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=1500,
        help="Per-request timeout in seconds passed to chat_completion_with_retry",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=0,
        help="Write partial results every N newly generated items; 0 disables mid-run checkpoints",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Reuse existing output JSON in --output-dir and skip papers already present",
    )
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        help="Skip a model after this many consecutive failures; set 0 to disable",
    )
    args = parser.parse_args()
    if args.hypothesis_format == "l1_single" and args.prompt_level != "L1":
        parser.error("--hypothesis-format l1_single can only be used with --prompt-level L1")
    if args.hypothesis_format == "single_level" and args.prompt_level == "all":
        parser.error("--hypothesis-format single_level requires --prompt-level to be L1, L2, or L3")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    items = _load_queries(args.input)
    if args.max_items is not None:
        items = items[: args.max_items]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    effective_format = _resolve_hypothesis_format(args.prompt_level, args.hypothesis_format)
    system_prompt = _system_prompt_for(args.prompt_level, effective_format)

    model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    for model_name in model_names:
        out_path = output_dir / f"{_sanitize_model_name(model_name)}.json"
        existing_results = _load_existing_results(out_path) if args.skip_existing else []
        existing_by_paper = {
            str(row.get("paper_id", "")): _normalize_result_row(row)
            for row in existing_results
            if row.get("paper_id")
        }
        logger.info(
            "Generating hypotheses with model=%s prompt_level=%s hypothesis_format=%s existing=%d",
            model_name,
            args.prompt_level,
            effective_format,
            len(existing_by_paper),
        )
        llm_utils.MODEL_NAME = model_name
        results: List[Dict[str, Any]] = []
        consecutive_errors = 0
        generated_since_checkpoint = 0
        for idx, item in enumerate(items, start=1):
            paper_id = _paper_id_for(item)
            if paper_id in existing_by_paper:
                logger.info("[%s] [%d/%d] skip existing %s", model_name, idx, len(items), paper_id)
                results.append(existing_by_paper[paper_id])
                consecutive_errors = 0
                continue

            prompt = _build_user_prompt(item, args.prompt_level, effective_format)
            queries = _get_queries(item)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
            try:
                response = llm_utils.chat_completion_with_retry(
                    messages,
                    temperature=args.temperature,
                    timeout=args.request_timeout,
                )
                error = ""
                consecutive_errors = 0
            except Exception as e:
                response = f"[ERROR] {e}"
                error = str(e)
                consecutive_errors += 1
                logger.warning("[%s] [%d/%d] generation failed for %s: %s",
                               model_name, idx, len(items), paper_id, e)

            results.append(
                {
                    "paper_id": paper_id,
                    "method_name": f"{model_name}-{args.prompt_level}",
                    "prompt_level": args.prompt_level,
                    "hypothesis_format": effective_format,
                    "query": queries.get(args.prompt_level, queries.get("L1", "")),
                    "free_text_hypotheses": [response],
                    "error": error,
                    "metadata": _metadata_for(item),
                }
            )
            generated_since_checkpoint += 1

            if args.checkpoint_every > 0 and generated_since_checkpoint >= args.checkpoint_every:
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                logger.info(
                    "[%s] checkpoint saved %d records -> %s",
                    model_name,
                    len(results),
                    out_path,
                )
                generated_since_checkpoint = 0

            if error and _looks_like_unavailable_model_error(error):
                logger.error(
                    "[%s] looks unavailable on this gateway; skip remaining %d items. Error: %s",
                    model_name,
                    len(items) - idx,
                    error,
                )
                break

            if (
                error
                and args.max_consecutive_errors > 0
                and consecutive_errors >= args.max_consecutive_errors
            ):
                logger.error(
                    "[%s] reached %d consecutive failures; skip remaining %d items. Last error: %s",
                    model_name,
                    consecutive_errors,
                    len(items) - idx,
                    error,
                )
                break

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Saved %d generated records -> %s", len(results), out_path)


if __name__ == "__main__":
    main()

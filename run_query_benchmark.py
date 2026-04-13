"""Generate free-text hypotheses from query-centric evaluation inputs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from crossdisc_extractor.utils import llm as llm_utils


logger = logging.getLogger("run_query_benchmark")


SYSTEM_PROMPT = """你是一名擅长交叉学科科研假设生成的专家。
请根据给定的研究 query，生成具有科学性、可行性和新颖性的研究假设。

输出要求：
1. 优先给出分层假设，使用 [L1]、[L2]、[L3] 标记不同层次。
2. 每个层次尽量写成 1-3 条清晰的推理链式假设。
3. 每条假设要包含关键实体、作用关系和预期机制。
4. 使用自然语言即可，不必输出 JSON。
5. 不要解释你的思考过程，不要输出额外前言。
"""


def _load_queries(path: str) -> List[Dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def _build_user_prompt(item: Dict[str, Any], prompt_level: str) -> str:
    queries = item.get("queries", {})
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
        for q in queries.get("L2", []):
            lines.append(f"- {q}")
    elif prompt_level == "L3":
        lines.append(f"L1 Query: {queries.get('L1', '')}")
        lines.append("L3 Queries:")
        for q in queries.get("L3", []):
            lines.append(f"- {q}")
    else:
        lines.append(f"L1 Query: {queries.get('L1', '')}")
        lines.append("L2 Queries:")
        for q in queries.get("L2", []):
            lines.append(f"- {q}")
        lines.append("L3 Queries:")
        for q in queries.get("L3", []):
            lines.append(f"- {q}")

    lines.append("")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate hypotheses for query-centric benchmark evaluation")
    parser.add_argument("--input", required=True, help="Query eval JSON built by build_query_eval_set.py")
    parser.add_argument("--output-dir", required=True, help="Output directory for model result JSON files")
    parser.add_argument("--models", required=True, help="Comma-separated model names")
    parser.add_argument("--prompt-level", choices=["L1", "L2", "L3", "all"], default="L1")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-items", type=int, default=None, help="Generate only the first N queries")
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        help="Skip a model after this many consecutive failures; set 0 to disable",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    items = _load_queries(args.input)
    if args.max_items is not None:
        items = items[: args.max_items]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    for model_name in model_names:
        logger.info("Generating hypotheses with model=%s prompt_level=%s", model_name, args.prompt_level)
        llm_utils.MODEL_NAME = model_name
        results: List[Dict[str, Any]] = []
        consecutive_errors = 0
        for idx, item in enumerate(items, start=1):
            prompt = _build_user_prompt(item, args.prompt_level)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            try:
                response = llm_utils.chat_completion_with_retry(messages, temperature=args.temperature)
                error = ""
                consecutive_errors = 0
            except Exception as e:
                response = f"[ERROR] {e}"
                error = str(e)
                consecutive_errors += 1
                logger.warning("[%s] [%d/%d] generation failed for %s: %s",
                               model_name, idx, len(items), item.get("paper_id"), e)

            results.append(
                {
                    "paper_id": item.get("paper_id", ""),
                    "method_name": f"{model_name}-{args.prompt_level}",
                    "prompt_level": args.prompt_level,
                    "query": item.get("queries", {}).get("L1", ""),
                    "free_text_hypotheses": [response],
                    "error": error,
                    "metadata": item.get("metadata", {}),
                }
            )

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

        out_path = output_dir / f"{_sanitize_model_name(model_name)}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Saved %d generated records -> %s", len(results), out_path)


if __name__ == "__main__":
    main()

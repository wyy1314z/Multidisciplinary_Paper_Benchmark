"""Evaluation functions: LLM-based knowledge path matching and accuracy calculation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from .client import UniChatClient

logger = logging.getLogger(__name__)


def read_prompt(prompt_path: str) -> str:
    """Read a prompt template from a text file."""
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return path.read_text(encoding="utf-8")


def _load_processed_statements(output_path: str) -> List[str]:
    """Load already-processed problem statements for checkpoint resumption."""
    if not Path(output_path).exists():
        return []
    seen: List[str] = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "problem_statement" in data:
                    seen.append(data["problem_statement"])
            except json.JSONDecodeError:
                continue
    return seen


def check_knowledge_match(
    data: Dict[str, Any],
    client: UniChatClient,
    *,
    provider: str,
    model: str,
    system_prompt: str,
) -> Optional[str]:
    """Call LLM to judge whether knowledge paths match a problem statement."""
    user_input = json.dumps(data, ensure_ascii=False)
    ans = client.chat(
        content=user_input,
        model=model,
        provider=provider,
        system_instruction=system_prompt,
    )
    if not ans or not isinstance(ans, str):
        logger.warning("Model returned empty or non-string: %s", ans)
        return None
    return ans.strip()


def process_llm_judge(raw: str) -> Optional[Any]:
    """Parse LLM judge output, handling JSON, Markdown fences, trailing commas, etc."""
    # Direct parse
    try:
        obj = json.loads(raw)
        return obj.get("results", obj)
    except (json.JSONDecodeError, ValueError):
        pass

    # Cleaned parse
    s = raw.strip()
    s = re.sub(r"^```json", "", s, flags=re.I)
    s = re.sub(r"^```", "", s)
    s = re.sub(r"```$", "", s)
    s = re.sub(r",\s*([\]}])", r"\1", s)
    s = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", s)
    s = s.strip()
    try:
        obj = json.loads(s)
        return obj.get("results", obj)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("JSON parse error: %s | raw: %s", e, raw[:500])
        return None


def judge_classify_true_or_false(
    input_path: str,
    output_path: str,
    prompt_path: str,
    *,
    provider: str = "openrouter",
    model: str = "gpt-4o-mini",
) -> None:
    """Read problems from JSONL, call LLM judge, write results to output JSONL.

    Supports checkpoint resumption via already-processed problem statements.
    """
    system_prompt = read_prompt(prompt_path)
    client = UniChatClient(default_provider=provider)
    processed = _load_processed_statements(output_path)

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(output_path, "a", encoding="utf-8") as fout:
        for line in tqdm(lines, desc="Evaluating"):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)

            sample = {
                "problem_statement": data.get("problem_statement"),
                "golden_answer": data.get("golden_answer"),
                "knowlege_paths": data.get("knowlege_paths"),
            }

            if not sample["problem_statement"]:
                continue
            if sample["problem_statement"] in processed:
                continue

            raw = check_knowledge_match(
                sample, client, provider=provider, model=model, system_prompt=system_prompt
            )
            if raw is None:
                continue

            parsed = process_llm_judge(raw)
            if parsed is None:
                continue

            out_item = {**data, "is_match": parsed}
            fout.write(json.dumps(out_item, ensure_ascii=False) + "\n")


def _is_truthy(x: Any) -> bool:
    return str(x).lower() == "true"


def calculate_accuracy(path: str) -> Dict[str, Any]:
    """Compute per-level and total accuracy from evaluation JSONL output.

    Returns:
        Dictionary with counts and accuracy for each level and total.
    """
    count: Dict[str, Any] = {
        "total": 0, "total_true": 0, "total_acc": 0.0,
        "level1_total": 0, "level1_true": 0, "level1_acc": 0.0,
        "level2_total": 0, "level2_true": 0, "level2_acc": 0.0,
        "level3_total": 0, "level3_true": 0, "level3_acc": 0.0,
    }

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if "is_match" not in data:
                continue

            total_true = True
            items = data["is_match"]

            if isinstance(items, dict) and "results" in items:
                items = items["results"]
            if not isinstance(items, list):
                continue

            count["total"] += 1

            for item in items:
                imz = (item or {}).get("is_matchz", {})
                for level in ("level1", "level2", "level3"):
                    count[f"{level}_total"] += 1
                    if level in imz:
                        if _is_truthy(imz[level]):
                            count[f"{level}_true"] += 1
                        else:
                            total_true = False
                    else:
                        total_true = False

            if total_true:
                count["total_true"] += 1

    for key in ("total", "level1", "level2", "level3"):
        total_key = f"{key}_total" if key != "total" else "total"
        true_key = f"{key}_true" if key != "total" else "total_true"
        acc_key = f"{key}_acc" if key != "total" else "total_acc"
        if count[total_key] > 0:
            count[acc_key] = round(count[true_key] / count[total_key], 4)

    logger.info("Accuracy results: %s", count)
    return count

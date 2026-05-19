#!/usr/bin/env python3
"""Generate computer158 hypotheses with lightweight multi-agent frameworks.

This runner is intentionally strict about the input contract:

- It reuses the *same input content* as the existing single-model
  `run_query_benchmark.py` flow for computer158.
- No abstract, introduction, retrieval corpus, KG, author KB, or web search
  is injected into the agent prompts.
- The framework-specific prompts are role instructions layered on top of the
  exact same benchmark brief.

The output schema is aligned with:

- `paper_id`
- `method_name`
- `prompt_level`
- `hypothesis_format`
- `query`
- `free_text_hypotheses`
- `error`
- `metadata`
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


logger = logging.getLogger("run_multiagent_query_benchmark")


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


FRAMEWORK_SCREENING: Dict[str, Dict[str, Any]] = {
    "sciagents": {
        "selected": True,
        "source_dir": "benchmark_baseline/SciAgentsDiscovery-main",
        "topology": "Ontologist -> Scientist -> Critic -> Formatter",
        "reason": "保留多角色协作与 gap-bridging 机制，同时禁止外部 KG / 检索输入。",
    },
    "moose_chem": {
        "selected": True,
        "source_dir": "benchmark_baseline/MOOSE-Chem-main",
        "topology": "Inspiration Extractor -> Composer -> Ranker -> Formatter",
        "reason": "保留灵感抽取与组合机制，但仅从同一份 query brief 中抽取 inspirations。",
    },
    "infal": {
        "selected": True,
        "source_dir": "benchmark_baseline/InfAL-main",
        "topology": "Generator -> Optimizer -> Discriminator -> Formatter",
        "reason": "保留 inference-time adversarial refinement，但 seed idea 仅来自相同输入 brief。",
    },
    "virsci": {
        "selected": True,
        "source_dir": "benchmark_baseline/Virtual-Scientists-main",
        "topology": "Scientist A -> Scientist B -> Reviewer -> Arbiter -> Formatter",
        "reason": "保留 team-based debate/fusion 机制，但不接 AMiner / FAISS / author KB。",
    },
    "ai_scientist": {
        "selected": False,
        "source_dir": "benchmark_baseline/AI-Scientist-main",
        "topology": "Agentic pipeline with code execution",
        "reason": "原始系统偏模板+代码执行，不是当前任务里最合适的同输入多智能体基线。",
    },
}


def _as_query_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if value:
        return [str(value)]
    return []


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


def _paper_id_for(item: Dict[str, Any]) -> str:
    return str(item.get("paper_id") or item.get("doi") or item.get("title") or "")


def _metadata_for(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        base = dict(metadata)
    else:
        base = {}
    keys = (
        "journal",
        "doi",
        "publication_date",
        "publication_year",
        "primary_discipline",
        "secondary_disciplines",
    )
    for key in keys:
        if key in item and key not in base:
            base[key] = item.get(key)
    return base


def _resolve_hypothesis_format(prompt_level: str) -> str:
    return "l1_single" if prompt_level == "L1" else "single_level"


def _system_prompt_for(prompt_level: str) -> str:
    if prompt_level == "L1":
        return SYSTEM_PROMPT_L1_SINGLE
    return SYSTEM_PROMPT_SINGLE_LEVEL.replace("<LEVEL>", prompt_level)


def _single_model_input_brief(item: Dict[str, Any], prompt_level: str) -> str:
    """Replicate the content structure from run_query_benchmark.py."""
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
        raise ValueError(f"Unsupported prompt level: {prompt_level}")

    lines.append("")
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
    else:
        lines.append(
            "请只基于上述 L3 Query 生成 1 条 [L3] 层级科研假设；"
            "不要输出 [L1] 或 [L2]，不要编号，不要分条。"
        )
    return "\n".join(lines)


def _selected_query_text(item: Dict[str, Any], prompt_level: str) -> str:
    queries = _get_queries(item)
    return str(queries.get(prompt_level, ""))


def _sanitize_model_name(model_name: str) -> str:
    return model_name.replace("/", "_").replace(":", "_")


def _looks_like_mock(text: str) -> bool:
    s = (text or "").lower()
    return "mock evaluation with random scores" in s or "innovation_score" in s


def _json_from_text(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        pass

    for left, right in (("{", "}"), ("[", "]")):
        start = text.find(left)
        end = text.rfind(right)
        if start >= 0 and end > start:
            chunk = text[start:end + 1]
            try:
                return json.loads(chunk)
            except Exception:
                continue
    return None


def _compact_trace(traces: Iterable[Tuple[str, str]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for stage, text in traces:
        result.append(
            {
                "stage": stage,
                "chars": len(text or ""),
                "preview": (text or "").strip().replace("\n", " ")[:160],
            }
        )
    return result


def _format_hypothesis(
    call_llm: Callable[..., str],
    prompt_level: str,
    brief: str,
    candidate: str,
    timeout: int,
) -> str:
    system = _system_prompt_for(prompt_level)
    user = (
        "你是最终格式化 agent。你必须只基于给定候选假设与原始输入，"
        "把结果改写成与 benchmark 单模型输出严格兼容的最终格式。\n\n"
        "限制：\n"
        "1. 不能引入外部事实、外部论文、外部数据。\n"
        "2. 只能输出 1 条当前层级假设。\n"
        "3. 不要输出 JSON，不要解释过程。\n\n"
        f"原始 benchmark 输入:\n{brief}\n\n"
        f"候选假设:\n{candidate}\n"
    )
    return call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        timeout=timeout,
    ).strip()


def _run_sciagents(
    call_llm: Callable[..., str],
    prompt_level: str,
    brief: str,
    timeout: int,
) -> Tuple[str, List[Tuple[str, str]]]:
    traces: List[Tuple[str, str]] = []

    onto_prompt = (
        "You are the Ontologist agent in a same-input benchmark.\n"
        "Work only from the benchmark input below. Do not use any external facts, "
        "retrieval, knowledge graph, or domain memory beyond what can be inferred "
        "from the provided title, disciplines, and query.\n\n"
        f"Benchmark Input:\n{brief}\n\n"
        "Return compact JSON with keys: concepts, relationships, gaps."
    )
    onto_resp = call_llm([{"role": "user", "content": onto_prompt}], temperature=0.2, timeout=timeout)
    traces.append(("ontologist", onto_resp))

    sci_prompt = (
        "You are the Scientist agent.\n"
        "Using only the original benchmark input and the ontological analysis below, "
        f"draft exactly 3 candidate {prompt_level} hypotheses.\n"
        "Each candidate must focus on a single coherent causal or mechanism chain.\n"
        "Return compact JSON with key candidates, where each candidate contains "
        "hypothesis, mechanism, and testable_prediction.\n\n"
        f"Benchmark Input:\n{brief}\n\n"
        f"Ontological Analysis:\n{onto_resp}"
    )
    sci_resp = call_llm([{"role": "user", "content": sci_prompt}], temperature=0.6, timeout=timeout)
    traces.append(("scientist", sci_resp))

    critic_prompt = (
        "You are the Critic agent.\n"
        "Review the candidate hypotheses below for level alignment, specificity, "
        "scientific coherence, and testability. Pick the single best candidate and refine it.\n"
        "Return compact JSON with keys selected_hypothesis and reason.\n\n"
        f"Benchmark Input:\n{brief}\n\n"
        f"Candidates:\n{sci_resp}"
    )
    critic_resp = call_llm([{"role": "user", "content": critic_prompt}], temperature=0.2, timeout=timeout)
    traces.append(("critic", critic_resp))

    obj = _json_from_text(critic_resp)
    candidate = critic_resp.strip()
    if isinstance(obj, dict):
        candidate = str(obj.get("selected_hypothesis") or obj.get("best_hypothesis") or candidate)

    final_text = _format_hypothesis(call_llm, prompt_level, brief, candidate, timeout)
    traces.append(("formatter", final_text))
    return final_text, traces


def _run_moose_chem(
    call_llm: Callable[..., str],
    prompt_level: str,
    brief: str,
    timeout: int,
) -> Tuple[str, List[Tuple[str, str]]]:
    traces: List[Tuple[str, str]] = []

    inspiration_prompt = (
        "You are the Inspiration Extractor agent.\n"
        "Using only the benchmark input below, extract 4-6 concise inspiration fragments "
        "that could later be recombined into new hypotheses. Do not use external literature.\n"
        'Return compact JSON: {"inspirations": ["...", "..."]}\n\n'
        f"Benchmark Input:\n{brief}"
    )
    inspiration_resp = call_llm(
        [{"role": "user", "content": inspiration_prompt}],
        temperature=0.2,
        timeout=timeout,
    )
    traces.append(("inspiration_extractor", inspiration_resp))

    compose_prompt = (
        "You are the Composer agent.\n"
        f"Using only the benchmark input and the inspiration fragments below, draft exactly 3 candidate {prompt_level} hypotheses.\n"
        "Each candidate should explicitly recombine at least two fragments.\n"
        'Return compact JSON: {"candidates": [{"hypothesis":"...", "combined_fragments":[0,2], "why_non_obvious":"..."}]}\n\n'
        f"Benchmark Input:\n{brief}\n\n"
        f"Inspirations:\n{inspiration_resp}"
    )
    compose_resp = call_llm([{"role": "user", "content": compose_prompt}], temperature=0.6, timeout=timeout)
    traces.append(("composer", compose_resp))

    rank_prompt = (
        "You are the Ranker agent.\n"
        "Choose the single strongest candidate based on novelty, coherence, and level alignment.\n"
        'Return compact JSON: {"best_hypothesis":"...", "reason":"..."}\n\n'
        f"Benchmark Input:\n{brief}\n\n"
        f"Candidates:\n{compose_resp}"
    )
    rank_resp = call_llm([{"role": "user", "content": rank_prompt}], temperature=0.2, timeout=timeout)
    traces.append(("ranker", rank_resp))

    obj = _json_from_text(rank_resp)
    candidate = rank_resp.strip()
    if isinstance(obj, dict):
        candidate = str(obj.get("best_hypothesis") or obj.get("selected_hypothesis") or candidate)

    final_text = _format_hypothesis(call_llm, prompt_level, brief, candidate, timeout)
    traces.append(("formatter", final_text))
    return final_text, traces


def _run_infal(
    call_llm: Callable[..., str],
    prompt_level: str,
    brief: str,
    timeout: int,
) -> Tuple[str, List[Tuple[str, str]]]:
    traces: List[Tuple[str, str]] = []

    generator_prompt = (
        "You are the Generator agent.\n"
        f"Using only the benchmark input below, draft one initial {prompt_level} hypothesis candidate.\n"
        "The hypothesis should be bold but still grounded in the provided query.\n\n"
        f"Benchmark Input:\n{brief}"
    )
    generator_resp = call_llm(
        [{"role": "user", "content": generator_prompt}],
        temperature=0.7,
        timeout=timeout,
    )
    traces.append(("generator", generator_resp))

    optimizer_prompt = (
        "You are the Optimizer agent.\n"
        "Refine the initial hypothesis in two directions:\n"
        "1. novelty_optimized\n"
        "2. feasibility_optimized\n"
        "Use only the original benchmark input. Return compact JSON with both keys.\n\n"
        f"Benchmark Input:\n{brief}\n\n"
        f"Initial Hypothesis:\n{generator_resp}"
    )
    optimizer_resp = call_llm([{"role": "user", "content": optimizer_prompt}], temperature=0.4, timeout=timeout)
    traces.append(("optimizer", optimizer_resp))

    discriminator_prompt = (
        "You are the Discriminator agent.\n"
        "Compare the optimized variants below and select or fuse them into one best final candidate.\n"
        'Return compact JSON: {"selected_hypothesis":"...", "reason":"..."}\n\n'
        f"Benchmark Input:\n{brief}\n\n"
        f"Optimized Variants:\n{optimizer_resp}"
    )
    discriminator_resp = call_llm(
        [{"role": "user", "content": discriminator_prompt}],
        temperature=0.2,
        timeout=timeout,
    )
    traces.append(("discriminator", discriminator_resp))

    obj = _json_from_text(discriminator_resp)
    candidate = discriminator_resp.strip()
    if isinstance(obj, dict):
        candidate = str(obj.get("selected_hypothesis") or obj.get("best_hypothesis") or candidate)

    final_text = _format_hypothesis(call_llm, prompt_level, brief, candidate, timeout)
    traces.append(("formatter", final_text))
    return final_text, traces


def _run_virsci(
    call_llm: Callable[..., str],
    prompt_level: str,
    brief: str,
    timeout: int,
) -> Tuple[str, List[Tuple[str, str]]]:
    traces: List[Tuple[str, str]] = []

    proposer_a_prompt = (
        "You are Scientist A in a virtual team.\n"
        f"Using only the benchmark input below, propose one strong {prompt_level} hypothesis that emphasizes novelty.\n\n"
        f"Benchmark Input:\n{brief}"
    )
    proposer_a_resp = call_llm(
        [{"role": "user", "content": proposer_a_prompt}],
        temperature=0.7,
        timeout=timeout,
    )
    traces.append(("scientist_a", proposer_a_resp))

    proposer_b_prompt = (
        "You are Scientist B in a virtual team.\n"
        f"Using only the benchmark input below, propose one different {prompt_level} hypothesis that emphasizes feasibility and mechanism clarity.\n\n"
        f"Benchmark Input:\n{brief}"
    )
    proposer_b_resp = call_llm(
        [{"role": "user", "content": proposer_b_prompt}],
        temperature=0.6,
        timeout=timeout,
    )
    traces.append(("scientist_b", proposer_b_resp))

    reviewer_prompt = (
        "You are the Reviewer agent.\n"
        "Compare the two candidate hypotheses below. Identify the strongest components of each, "
        "their weaknesses, and what a final fused hypothesis should preserve.\n"
        'Return compact JSON with keys strengths_a, strengths_b, fusion_plan.\n\n'
        f"Benchmark Input:\n{brief}\n\n"
        f"Scientist A:\n{proposer_a_resp}\n\n"
        f"Scientist B:\n{proposer_b_resp}"
    )
    reviewer_resp = call_llm([{"role": "user", "content": reviewer_prompt}], temperature=0.2, timeout=timeout)
    traces.append(("reviewer", reviewer_resp))

    arbiter_prompt = (
        "You are the Final Arbiter agent.\n"
        f"Fuse the best parts of the two candidates into one final {prompt_level} hypothesis.\n"
        'Return compact JSON: {"selected_hypothesis":"...", "reason":"..."}\n\n'
        f"Benchmark Input:\n{brief}\n\n"
        f"Scientist A:\n{proposer_a_resp}\n\n"
        f"Scientist B:\n{proposer_b_resp}\n\n"
        f"Reviewer Notes:\n{reviewer_resp}"
    )
    arbiter_resp = call_llm([{"role": "user", "content": arbiter_prompt}], temperature=0.3, timeout=timeout)
    traces.append(("arbiter", arbiter_resp))

    obj = _json_from_text(arbiter_resp)
    candidate = arbiter_resp.strip()
    if isinstance(obj, dict):
        candidate = str(obj.get("selected_hypothesis") or obj.get("best_hypothesis") or candidate)

    final_text = _format_hypothesis(call_llm, prompt_level, brief, candidate, timeout)
    traces.append(("formatter", final_text))
    return final_text, traces


FRAMEWORK_RUNNERS: Dict[str, Callable[..., Tuple[str, List[Tuple[str, str]]]]] = {
    "sciagents": _run_sciagents,
    "moose_chem": _run_moose_chem,
    "infal": _run_infal,
    "virsci": _run_virsci,
}


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
    parser = argparse.ArgumentParser(description="Generate multi-agent hypotheses for query-centric benchmark evaluation")
    parser.add_argument("--input", help="computer158 JSON dataset")
    parser.add_argument("--output-dir", help="Output directory for result JSON file")
    parser.add_argument(
        "--framework",
        choices=sorted(FRAMEWORK_RUNNERS.keys()),
        help="Selected lightweight multi-agent framework",
    )
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.5"), help="Backbone model name")
    parser.add_argument("--prompt-level", choices=["L1", "L2", "L3"], default="L1")
    parser.add_argument("--temperature", type=float, default=0.2, help="Reserved for parity; stage prompts use fixed role temperatures")
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
    parser.add_argument("--skip-existing", action="store_true", help="Reuse existing output JSON and skip processed papers")
    parser.add_argument("--preflight-only", action="store_true", help="Run a single connectivity test and exit")
    parser.add_argument("--list-frameworks", action="store_true", help="Print framework screening table and exit")
    args = parser.parse_args()

    if args.list_frameworks:
        for name, meta in FRAMEWORK_SCREENING.items():
            marker = "selected" if meta["selected"] else "excluded"
            print(f"{name}\t{marker}\t{meta['topology']}\t{meta['reason']}")
        return

    if not args.input or not args.output_dir or not args.framework:
        parser.error("--input, --output-dir, and --framework are required unless --list-frameworks is used")

    if args.framework not in FRAMEWORK_RUNNERS:
        raise SystemExit(f"Unsupported framework: {args.framework}")

    framework_meta = FRAMEWORK_SCREENING.get(args.framework, {})
    if framework_meta and not framework_meta.get("selected", False):
        raise SystemExit(f"Framework {args.framework} is screened out for the strict same-input setting.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Refusing to run to avoid mock outputs.")

    os.environ["OPENAI_MODEL"] = args.model

    from crossdisc_extractor.utils import llm as llm_utils

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_slug = _sanitize_model_name(args.model)
    output_path = output_dir / f"{model_slug}.json"

    items = _load_queries(args.input)
    if args.max_items is not None:
        items = items[: args.max_items]

    existing_rows: List[Dict[str, Any]] = []
    existing_ids: set[str] = set()
    if args.skip_existing and output_path.exists():
        existing_rows = [_normalize_result_row(row) for row in _load_existing_results(output_path)]
        existing_ids = {str(row.get("paper_id", "")) for row in existing_rows if row.get("paper_id")}
        logger.info("Loaded %d existing rows from %s", len(existing_rows), output_path)

    def call_llm(messages: List[Dict[str, str]], temperature: float, timeout: int) -> str:
        return llm_utils.chat_completion_with_retry(
            messages,
            temperature=temperature,
            timeout=timeout,
        )

    # Preflight probe before the expensive loop.
    probe_messages = [
        {
            "role": "system",
            "content": "You are a concise assistant.",
        },
        {
            "role": "user",
            "content": "Reply with exactly: READY",
        },
    ]
    probe = call_llm(probe_messages, temperature=0.0, timeout=min(args.request_timeout, 120))
    if _looks_like_mock(probe):
        raise SystemExit("Detected mock placeholder output during preflight. Refusing to continue.")
    if "ready" not in probe.lower():
        logger.warning("Preflight returned unexpected text: %s", probe[:200])
    if args.preflight_only:
        print(probe.strip())
        return

    runner = FRAMEWORK_RUNNERS[args.framework]
    hypothesis_format = _resolve_hypothesis_format(args.prompt_level)

    rows: List[Dict[str, Any]] = list(existing_rows)
    generated_since_checkpoint = 0
    processed_count = 0

    for idx, item in enumerate(items, start=1):
        paper_id = _paper_id_for(item)
        if args.skip_existing and paper_id in existing_ids:
            logger.info("Skip existing %s", paper_id)
            continue

        brief = _single_model_input_brief(item, args.prompt_level)
        query = _selected_query_text(item, args.prompt_level)
        metadata = _metadata_for(item)
        metadata.update(
            {
                "generation_family": "multi_agent",
                "framework_name": args.framework,
                "framework_source_dir": framework_meta.get("source_dir", ""),
                "agent_topology": framework_meta.get("topology", ""),
                "backbone_model": args.model,
                "used_input_fields": (
                    ["title", "primary_discipline", "secondary_disciplines", "query.L1"]
                    if args.prompt_level == "L1"
                    else (
                        ["title", "primary_discipline", "secondary_disciplines", "query.L1", "query.L2"]
                        if args.prompt_level == "L2"
                        else ["title", "primary_discipline", "secondary_disciplines", "query.L1", "query.L3"]
                    )
                ),
                "input_policy": "same_as_single_model_query_benchmark",
            }
        )

        error = ""
        hypotheses: List[str] = []
        trace_summary: List[Dict[str, Any]] = []
        try:
            final_text, traces = runner(
                call_llm=call_llm,
                prompt_level=args.prompt_level,
                brief=brief,
                timeout=args.request_timeout,
            )
            if _looks_like_mock(final_text):
                raise RuntimeError("Detected mock placeholder output during generation.")
            hypotheses = [final_text.strip()] if final_text.strip() else []
            trace_summary = _compact_trace(traces)
        except Exception as exc:
            error = str(exc)
            hypotheses = [f"[ERROR] {exc}"]

        if trace_summary:
            metadata["agent_trace_summary"] = trace_summary

        row = {
            "paper_id": paper_id,
            "method_name": f"{args.framework}-{args.model}-{args.prompt_level}",
            "prompt_level": args.prompt_level,
            "hypothesis_format": hypothesis_format,
            "query": query,
            "free_text_hypotheses": hypotheses,
            "error": error,
            "metadata": metadata,
        }
        rows.append(row)
        processed_count += 1
        generated_since_checkpoint += 1
        logger.info("[%d/%d] %s -> %s", idx, len(items), paper_id, "error" if error else "ok")

        if args.checkpoint_every and generated_since_checkpoint >= args.checkpoint_every:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            generated_since_checkpoint = 0
            logger.info("Checkpoint saved to %s", output_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    logger.info(
        "Completed framework=%s level=%s model=%s processed=%d output=%s",
        args.framework,
        args.prompt_level,
        args.model,
        processed_count,
        output_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()

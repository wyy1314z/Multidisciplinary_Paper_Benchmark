#!/usr/bin/env python3
"""
baseline/run_single_paper_demo.py

用同一篇论文调用所有 baseline，生成真实的假设内容并保存/展示。
聚焦于"假设内容本身的差异"，而非评估指标。

用法:
    # 用 paper_1.json 第一篇论文运行所有 6 个非 CrossDisc baseline
    python -m baseline.run_single_paper_demo

    # 指定论文索引（paper_1.json 中第 6 篇）
    python -m baseline.run_single_paper_demo --paper-index 6

    # 只跑部分 baseline
    python -m baseline.run_single_paper_demo --baselines ideabench,sciagents

    # 结果保存在 baseline/outputs/demo_hypotheses.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
from typing import Any, Dict, List

# ── 各 baseline 的 prompt 直接内联，避免复杂依赖 ─────────────────────────

PROMPTS = {

"IdeaBench": {
    "ref": "IdeaBench, 2024",
    "desc": "给定 background abstract，以 biomedical researcher 身份生成自由文本假设段落",
    "system": (
        "You are a biomedical researcher. You are tasked with creating a "
        "hypothesis or research idea given some background knowledge."
    ),
    "user": (
        "Here is the background information:\n\n"
        "Title: {title}\n\nAbstract: {abstract}\n\n"
        "Using this information, reason over it and come up with a novel "
        "hypothesis. Please avoid copying ideas directly, rather use the "
        "insights to inspire a novel hypothesis in the form of a brief "
        "and concise paragraph."
    ),
    "temperature": 0.7,
},

"VanillaLLM": {
    "ref": "Si et al. (Stanford), 2024",
    "desc": "Zero-shot 直接生成假设列表，要求 specific + testable",
    "system": (
        "You are a scientific research expert. Given a paper's title and "
        "abstract, generate novel, specific, and testable research hypotheses "
        "that could extend or build upon this work.\n\n"
        "Requirements:\n"
        "- Each hypothesis should be specific and falsifiable\n"
        "- Hypotheses should go beyond what is stated in the abstract\n"
        "- Consider cross-disciplinary connections where relevant"
    ),
    "user": (
        "Paper Title: {title}\n\n"
        "Abstract: {abstract}\n\n"
        "Primary Discipline: {primary}\n"
        "Related Disciplines: {secondary}\n\n"
        "Please generate 3 novel research hypotheses based on this paper."
    ),
    "temperature": 0.7,
},

"AI-Scientist": {
    "ref": "Sakana AI, 2024 (arXiv: 2408.06292)",
    "desc": "以 AI 研究员身份生成结构化 idea，含 hypothesis + experiment + 自评分",
    "system": (
        "You are an ambitious AI research scientist. Your goal is to propose "
        "novel, creative, and feasible research ideas that could lead to "
        "impactful publications.\n\nYou think like a top researcher: you "
        "identify gaps in existing work, propose specific hypotheses, and "
        "design concrete experiments to test them."
    ),
    "user": (
        "Based on the following paper, propose 3 novel research ideas that "
        "extend or build upon this work.\n\n"
        "Paper Title: {title}\n"
        "Abstract: {abstract}\n"
        "Primary Field: {primary}\n"
        "Related Fields: {secondary}\n\n"
        "For each idea, provide:\n"
        "1. A short name\n"
        "2. A paper-style title\n"
        "3. A specific, testable hypothesis\n"
        "4. A brief experiment design\n"
        "5. Self-assessment scores (1-10) for Interestingness, Feasibility, "
        "and Novelty"
    ),
    "temperature": 0.7,
},

"SciMON": {
    "ref": "AI2 / Northwestern, 2024 (arXiv: 2305.14259)",
    "desc": "Novelty-optimized 假设生成，显式要求与已有工作不同",
    "system": (
        "You are a scientific inspiration machine. Your goal is to generate "
        "novel research hypotheses that are DIFFERENT from existing work but "
        "grounded in real scientific knowledge.\n\n"
        "Key principle: Novelty-Optimized Generation — your hypotheses must "
        "NOT simply restate or incrementally extend the input paper. Instead, "
        "find unexpected connections, propose paradigm shifts, or suggest "
        "cross-domain transfers."
    ),
    "user": (
        "Seed Paper:\n"
        "Title: {title}\n"
        "Abstract: {abstract}\n\n"
        "Related Fields: {primary}, {secondary}\n\n"
        "Generate 3 novel scientific hypotheses INSPIRED BY (but distinct "
        "from) the seed paper above. Each hypothesis should:\n"
        "1. Be grounded in real scientific concepts\n"
        "2. Be clearly DIFFERENT from what the seed paper already proposes\n"
        "3. Suggest a specific, testable prediction\n"
        "4. Ideally connect ideas from different fields"
    ),
    "temperature": 0.8,
},

"MOOSE-Chem": {
    "ref": "UIUC, 2024",
    "desc": "两阶段：先提取灵感片段(inspiration)，再组合生成假设",
    "system": "",
    "user": "",
    "two_stage": True,
    "stage1_user": (
        "You are a scientific literature analyst. Extract 4-5 key scientific "
        "findings, methods, and insights from the following paper as concise "
        "'inspiration fragments'.\n\n"
        "Title: {title}\n"
        "Abstract: {abstract}\n\n"
        "List each inspiration as a single sentence, numbered."
    ),
    "stage2_user": (
        "You are a creative scientist who generates novel hypotheses by "
        "combining insights from different sources.\n\n"
        "Inspiration fragments from a paper in {primary}:\n{inspirations}\n\n"
        "Related Fields: {secondary}\n\n"
        "Task: Combine these inspirations in UNEXPECTED ways to generate 3 "
        "novel, testable scientific hypotheses. For each hypothesis, state "
        "which inspirations you combined and why the combination is non-obvious."
    ),
    "temperature": 0.7,
},

"SciAgents": {
    "ref": "MIT, 2024 (arXiv: 2409.05556)",
    "desc": "Multi-agent: Ontologist(概念)→Scientist(假设)→Critic(评审精炼)",
    "system": "",
    "user": "",
    "multi_agent": True,
    "agent1_user": (
        "You are the Ontologist agent. Analyze this paper and identify:\n"
        "1. Key domain concepts (5-8 specific terms)\n"
        "2. Relationships between concepts\n"
        "3. Knowledge gaps or unexplored connections\n\n"
        "Title: {title}\n"
        "Abstract: {abstract}\n"
        "Primary Field: {primary}\n"
        "Related Fields: {secondary}"
    ),
    "agent2_user": (
        "You are the Scientist agent. Based on the Ontologist's analysis "
        "below, propose 3 novel hypotheses that bridge the identified "
        "knowledge gaps.\n\n"
        "Ontological Analysis:\n{ontology}\n\n"
        "Original Paper Title: {title}\n\n"
        "Each hypothesis should connect concepts from different domains "
        "and be experimentally testable."
    ),
    "agent3_user": (
        "You are the Critic agent. Evaluate and REFINE the hypotheses below "
        "for scientific rigor, novelty, and feasibility. Output an improved "
        "version of each hypothesis.\n\n"
        "Paper: {title}\n\n"
        "Proposed Hypotheses:\n{hypotheses}\n\n"
        "For each, provide a refined version that is more specific and testable."
    ),
    "temperature": 0.7,
},
}


def _wrap(text, width=92, indent="      "):
    lines = textwrap.wrap(str(text), width=width - len(indent))
    return "\n".join(indent + l for l in lines)


def load_paper(input_path: str, index: int) -> Dict[str, Any]:
    with open(input_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == index:
                return json.loads(line.strip())
    raise IndexError(f"paper index {index} out of range")


def call_llm(system: str, user: str, temperature: float = 0.7) -> str:
    from crossdisc_extractor.utils.llm import chat_completion_with_retry
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return chat_completion_with_retry(messages, temperature=temperature)


def run_baseline(name: str, cfg: dict, paper: dict) -> dict:
    """运行单个 baseline，返回 {method, hypotheses_text, raw_response, elapsed}。"""
    title = paper["title"]
    abstract = paper["abstract"]
    primary = paper.get("primary_discipline", "N/A")
    secondary = paper.get("secondary_disciplines", [])
    sec_str = ", ".join(secondary) if isinstance(secondary, list) else str(secondary)

    fmt = dict(title=title, abstract=abstract, primary=primary, secondary=sec_str)

    t0 = time.time()

    if cfg.get("two_stage"):
        # MOOSE-Chem: two-stage
        s1_resp = call_llm("", cfg["stage1_user"].format(**fmt), cfg["temperature"])
        fmt["inspirations"] = s1_resp
        s2_resp = call_llm("", cfg["stage2_user"].format(**fmt), cfg["temperature"])
        raw = f"=== Stage 1 (Inspirations) ===\n{s1_resp}\n\n=== Stage 2 (Hypotheses) ===\n{s2_resp}"
        hyp_text = s2_resp

    elif cfg.get("multi_agent"):
        # SciAgents: 3-agent
        a1_resp = call_llm("", cfg["agent1_user"].format(**fmt), 0.3)
        fmt["ontology"] = a1_resp
        a2_resp = call_llm("", cfg["agent2_user"].format(**fmt), cfg["temperature"])
        fmt["hypotheses"] = a2_resp
        a3_resp = call_llm("", cfg["agent3_user"].format(**fmt), 0.3)
        raw = (f"=== Agent 1: Ontologist ===\n{a1_resp}\n\n"
               f"=== Agent 2: Scientist ===\n{a2_resp}\n\n"
               f"=== Agent 3: Critic ===\n{a3_resp}")
        hyp_text = a3_resp

    else:
        # Standard single-call
        user_msg = cfg["user"].format(**fmt)
        resp = call_llm(cfg["system"], user_msg, cfg["temperature"])
        raw = resp
        hyp_text = resp

    elapsed = time.time() - t0

    return {
        "method": name,
        "ref": cfg.get("ref", ""),
        "desc": cfg.get("desc", ""),
        "hypotheses_text": hyp_text.strip(),
        "raw_response": raw.strip(),
        "elapsed": round(elapsed, 1),
    }


def run_crossdisc(paper: dict) -> dict:
    """运行 CrossDisc 完整管线。"""
    from crossdisc_extractor.extractor_multi_stage import run_pipeline_for_item

    t0 = time.time()
    try:
        final, raw_all, introduction = run_pipeline_for_item(
            title=paper["title"],
            abstract=paper["abstract"],
            primary=paper.get("primary_discipline", ""),
            secondary_list=paper.get("secondary_disciplines", []),
            pdf_url="",
        )
        parsed = final.model_dump() if hasattr(final, "model_dump") else {}
        hyp_data = parsed.get("假设", {})

        # 构建展示文本
        lines = []
        for level, cn_key, sum_key in [("L1", "一级", "一级总结"),
                                        ("L2", "二级", "二级总结"),
                                        ("L3", "三级", "三级总结")]:
            paths = hyp_data.get(cn_key, [])
            summaries = hyp_data.get(sum_key, [])
            for i, path in enumerate(paths):
                lines.append(f"── {level} 假设路径 {i+1} ──")
                if isinstance(path, list):
                    for step in path:
                        if isinstance(step, dict):
                            h = step.get("head", step.get("头实体", ""))
                            r = step.get("relation", step.get("关系", ""))
                            tail = step.get("tail", step.get("尾实体", ""))
                            claim = step.get("claim", step.get("科学主张", ""))
                            lines.append(f"  {h} --[{r}]--> {tail}")
                            if claim:
                                lines.append(f"    claim: {claim}")
                summary = summaries[i] if i < len(summaries) else ""
                if summary:
                    lines.append(f"  Summary: {summary}")
                lines.append("")

        hyp_text = "\n".join(lines) if lines else str(hyp_data)
        raw = json.dumps(parsed, ensure_ascii=False, indent=2)

    except Exception as e:
        hyp_text = f"[ERROR] {e}"
        raw = str(e)

    elapsed = time.time() - t0

    return {
        "method": "CrossDisc",
        "ref": "Our method (multi-stage structured pipeline)",
        "desc": "概念抽取→关系抽取→查询生成→L1/L2/L3 结构化假设路径",
        "hypotheses_text": hyp_text.strip(),
        "raw_response": raw.strip(),
        "elapsed": round(elapsed, 1),
    }


def display_results(paper: dict, results: List[dict]):
    print()
    print("=" * 94)
    print("  同一篇论文 → 7 种方法生成的假设内容对比")
    print("=" * 94)
    print()
    print(f"  论文标题: {paper['title']}")
    print(f"  主学科:   {paper.get('primary_discipline', 'N/A')}")
    print(f"  摘要:")
    print(_wrap(paper["abstract"], indent="    "))
    print()
    print("─" * 94)

    for r in results:
        method = r["method"]
        ref = r["ref"]
        desc = r["desc"]
        elapsed = r["elapsed"]
        hyp = r["hypotheses_text"]

        print()
        print(f"  ┌─ {method}  ({ref})")
        print(f"  │  {desc}")
        print(f"  │  耗时: {elapsed}s")
        print(f"  │")
        # 按行展示假设内容
        for line in hyp.split("\n"):
            line = line.strip()
            if line:
                print(f"  │  {line}")
        print(f"  └{'─' * 90}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="用同一篇论文调用所有 baseline，对比生成的假设内容"
    )
    parser.add_argument("--input", default="data/paper_1.json",
                        help="Input JSONL file")
    parser.add_argument("--paper-index", type=int, default=0,
                        help="论文在 JSONL 中的行号 (0-based)")
    parser.add_argument("--title", default=None,
                        help="直接指定论文标题（跳过 --input 文件）")
    parser.add_argument("--abstract", default=None,
                        help="直接指定论文摘要（跳过 --input 文件）")
    parser.add_argument("--primary", default="",
                        help="主学科")
    parser.add_argument("--secondary", default="",
                        help="辅学科（逗号分隔）")
    parser.add_argument("--baselines", default=None,
                        help="Comma-separated baseline names (default: all 6)")
    parser.add_argument("--include-crossdisc", action="store_true",
                        help="同时运行 CrossDisc 完整管线")
    parser.add_argument("--output", default="baseline/outputs/demo_hypotheses.json",
                        help="保存结果的 JSON 路径")
    args = parser.parse_args()

    # 加载论文
    if args.title and args.abstract:
        paper = {
            "title": args.title,
            "abstract": args.abstract,
            "primary_discipline": args.primary or "Computational Biology",
            "secondary_disciplines": [
                s.strip() for s in args.secondary.split(",") if s.strip()
            ] if args.secondary else [],
        }
    else:
        paper_raw = load_paper(args.input, args.paper_index)
        paper = {
            "title": paper_raw["title"],
            "abstract": paper_raw["abstract"],
            "primary_discipline": paper_raw.get("main_discipline", ""),
            "secondary_disciplines": [
                f.strip() for f in paper_raw.get("field", "").split("|") if f.strip()
            ],
        }

    # 选择 baseline
    if args.baselines:
        selected = [b.strip() for b in args.baselines.split(",")]
    else:
        selected = list(PROMPTS.keys())

    # 运行
    results = []
    for name in selected:
        if name == "CrossDisc":
            # CrossDisc 单独处理
            continue
        if name not in PROMPTS:
            print(f"  [WARN] Unknown baseline: {name}, skipping")
            continue
        print(f"  Running {name}...", end="", flush=True)
        try:
            r = run_baseline(name, PROMPTS[name], paper)
            results.append(r)
            print(f" done ({r['elapsed']}s)")
        except Exception as e:
            print(f" FAILED: {e}")
            results.append({
                "method": name,
                "ref": PROMPTS[name].get("ref", ""),
                "desc": PROMPTS[name].get("desc", ""),
                "hypotheses_text": f"[ERROR] {e}",
                "raw_response": str(e),
                "elapsed": 0,
            })

    # 运行 CrossDisc
    if args.include_crossdisc or "CrossDisc" in selected:
        print(f"  Running CrossDisc (full pipeline)...", end="", flush=True)
        try:
            r = run_crossdisc(paper)
            results.append(r)
            print(f" done ({r['elapsed']}s)")
        except Exception as e:
            print(f" FAILED: {e}")
            results.append({
                "method": "CrossDisc",
                "ref": "Our method",
                "desc": "概念抽取→关系抽取→查询生成→L1/L2/L3 结构化假设路径",
                "hypotheses_text": f"[ERROR] {e}",
                "raw_response": str(e),
                "elapsed": 0,
            })

    # 展示
    display_results(paper, results)

    # 保存
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    save_data = {
        "paper": paper,
        "results": results,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存到 {args.output}")


if __name__ == "__main__":
    main()

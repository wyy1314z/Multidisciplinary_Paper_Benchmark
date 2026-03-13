#!/usr/bin/env python3
"""
baseline/evaluate_batch.py

对 batch_results.json 中所有假设进行评估。

评估维度:
  A) 文本相似度: ROUGE-1/2/L (假设 vs 原文 abstract)
  B) LLM-as-Judge: novelty / specificity / feasibility / relevance / cross_disciplinary (1-10)
  C) 结构化指标: 仅 P5 有 (chain_coherence / entity_grounding / relation_diversity / level_coverage)

用法:
    nohup python -m baseline.evaluate_batch \
        --input baseline/outputs/batch_results.json \
        --output baseline/outputs/eval_results.json \
        > baseline/outputs/eval_run.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# =====================================================================
#  A) ROUGE 文本相似度 (hypothesis vs abstract)
# =====================================================================

def compute_rouge(hypothesis: str, reference: str) -> Dict[str, float]:
    """计算 ROUGE-1/2/L F1。"""
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
        scores = scorer.score(reference, hypothesis)
        return {
            "rouge1": round(scores["rouge1"].fmeasure, 4),
            "rouge2": round(scores["rouge2"].fmeasure, 4),
            "rougeL": round(scores["rougeL"].fmeasure, 4),
        }
    except Exception as e:
        log(f"    [WARN] ROUGE failed: {e}")
        return {"rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}


# =====================================================================
#  B) LLM-as-Judge 多维度评分
# =====================================================================

LLM_JUDGE_SYSTEM = """你是一名严格的科学假设评估专家。请对给定的假设从5个维度进行1-10分的评分。
评分标准:
- novelty (新颖性): 假设是否提出了超越原文已有结论的新观点或新机制？
- specificity (具体性): 假设是否包含具体的变量、机制或可操作的实验方案？
- feasibility (可行性): 假设是否在现有技术和资源条件下可验证？
- relevance (相关性): 假设与原文研究方向是否密切相关？
- cross_disciplinary (跨学科性): 假设是否融合了多个学科的视角或方法？

只输出 JSON，不要输出其他任何内容。"""

LLM_JUDGE_USER = """论文标题: {title}
论文摘要: {abstract}

待评估假设:
{hypothesis}

请输出 JSON 格式的评分:
{{"novelty": <1-10>, "specificity": <1-10>, "feasibility": <1-10>, "relevance": <1-10>, "cross_disciplinary": <1-10>}}"""


def llm_judge(title: str, abstract: str, hypothesis: str) -> Dict[str, float]:
    """用 LLM 对假设进行 5 维度打分。"""
    from crossdisc_extractor.utils.llm import chat_completion_with_retry

    # 截断过长的假设文本（避免 token 超限）
    if len(hypothesis) > 3000:
        hypothesis = hypothesis[:3000] + "\n...(truncated)"

    prompt = LLM_JUDGE_USER.format(
        title=title, abstract=abstract, hypothesis=hypothesis,
    )
    try:
        resp = chat_completion_with_retry(
            [
                {"role": "system", "content": LLM_JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        # 清理 markdown code block
        cleaned = resp.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()
        scores = json.loads(cleaned)
        return {k: float(v) for k, v in scores.items() if isinstance(v, (int, float))}
    except Exception as e:
        log(f"    [WARN] LLM judge failed: {e}")
        return {
            "novelty": 0.0, "specificity": 0.0, "feasibility": 0.0,
            "relevance": 0.0, "cross_disciplinary": 0.0,
        }


# =====================================================================
#  C) 结构化路径指标（仅 P5）
# =====================================================================

def compute_structural_metrics(hypotheses_text: str) -> Optional[Dict[str, float]]:
    """
    从 P5 的 hypotheses_text 中解析结构化路径并计算指标。
    P5 的输出格式: ── L1 假设路径 1 ──\n  head --[rel]--> tail\n  ...
    """
    # 检测是否是 P5 结构化输出
    if "假设路径" not in hypotheses_text:
        return None

    paths_by_level: Dict[str, List[List[Dict]]] = {"L1": [], "L2": [], "L3": []}
    current_level = None
    current_path: List[Dict] = []

    for line in hypotheses_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 检测路径头
        match = re.match(r"── (L[123]) 假设路径 (\d+) ──", line)
        if match:
            if current_path and current_level:
                paths_by_level[current_level].append(current_path)
            current_level = match.group(1)
            current_path = []
            continue

        # 检测 step: head --[rel]--> tail
        step_match = re.match(r"(.+?)\s*--\[(.+?)\]-->\s*(.+)", line)
        if step_match and current_level:
            current_path.append({
                "head": step_match.group(1).strip(),
                "relation": step_match.group(2).strip(),
                "tail": step_match.group(3).strip(),
            })

    # 最后一条路径
    if current_path and current_level:
        paths_by_level[current_level].append(current_path)

    all_steps = []
    for paths in paths_by_level.values():
        for path in paths:
            all_steps.extend(path)

    if not all_steps:
        return None

    scores: Dict[str, float] = {}

    # 层级覆盖
    scores["has_L1"] = 1.0 if paths_by_level["L1"] else 0.0
    scores["has_L2"] = 1.0 if paths_by_level["L2"] else 0.0
    scores["has_L3"] = 1.0 if paths_by_level["L3"] else 0.0
    scores["level_coverage"] = round(
        (scores["has_L1"] + scores["has_L2"] + scores["has_L3"]) / 3, 4
    )

    # 路径数量
    total_paths = sum(len(ps) for ps in paths_by_level.values())
    scores["total_paths"] = float(total_paths)

    # 平均路径长度
    path_lengths = [len(p) for ps in paths_by_level.values() for p in ps]
    scores["avg_path_length"] = round(float(np.mean(path_lengths)), 2) if path_lengths else 0.0

    # 链式连贯性
    coherent_hops = 0
    total_hops = 0
    for paths in paths_by_level.values():
        for path in paths:
            for i in range(len(path) - 1):
                total_hops += 1
                tail_i = path[i].get("tail", "").strip()
                head_next = path[i + 1].get("head", "").strip()
                if tail_i and tail_i == head_next:
                    coherent_hops += 1
    scores["chain_coherence"] = round(coherent_hops / max(total_hops, 1), 4)

    # 关系多样性
    relations = set()
    for step in all_steps:
        rel = step.get("relation", "").strip()
        if rel:
            relations.add(rel)
    scores["relation_diversity"] = round(len(relations) / max(total_paths, 1), 4)

    # 实体 grounding (非空且非通用词)
    generic = {"前提", "结论", "结果", "方法", "分析", "研究", "问题", "目标",
               "关键前提", "关键中介", "关键结果"}
    grounded = 0
    total_ent = 0
    for step in all_steps:
        for field in ("head", "tail"):
            ent = step.get(field, "").strip()
            total_ent += 1
            if ent and ent not in generic:
                grounded += 1
    scores["entity_grounding_rate"] = round(grounded / max(total_ent, 1), 4)

    return scores


# =====================================================================
#  单条评估
# =====================================================================

def evaluate_one(
    paper: dict,
    result: dict,
    use_rouge: bool = True,
    use_llm_judge: bool = True,
) -> Dict[str, Any]:
    """对单个方法的单篇论文输出进行评估。"""
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    method = result.get("method", "unknown")
    hyp_text = result.get("hypotheses_text", "")

    eval_result: Dict[str, Any] = {
        "method": method,
        "elapsed": result.get("elapsed", 0),
        "hypothesis_length": len(hyp_text),
    }

    # 跳过错误输出
    if hyp_text.startswith("[ERROR]"):
        eval_result["error"] = True
        return eval_result

    eval_result["error"] = False

    # A) ROUGE
    if use_rouge and abstract:
        eval_result["rouge"] = compute_rouge(hyp_text, abstract)

    # B) LLM-as-Judge
    if use_llm_judge:
        eval_result["llm_judge"] = llm_judge(title, abstract, hyp_text)

    # C) 结构化指标
    struct = compute_structural_metrics(hyp_text)
    if struct is not None:
        eval_result["structural"] = struct

    return eval_result


# =====================================================================
#  聚合与展示
# =====================================================================

def aggregate_by_method(
    all_evals: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """按方法名聚合所有评估结果，计算均值。"""
    method_scores: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for entry in all_evals:
        for ev in entry.get("evaluations", []):
            method = ev.get("method", "unknown")
            if ev.get("error"):
                continue

            # ROUGE
            rouge = ev.get("rouge", {})
            for k, v in rouge.items():
                method_scores[method][f"rouge_{k}"].append(v)

            # LLM judge
            judge = ev.get("llm_judge", {})
            for k, v in judge.items():
                method_scores[method][f"judge_{k}"].append(v)

            # Structural
            struct = ev.get("structural", {})
            for k, v in struct.items():
                method_scores[method][f"struct_{k}"].append(v)

            # General
            method_scores[method]["hypothesis_length"].append(ev.get("hypothesis_length", 0))
            method_scores[method]["elapsed"].append(ev.get("elapsed", 0))

    aggregated = {}
    for method, scores_dict in method_scores.items():
        agg = {}
        for k, vals in scores_dict.items():
            agg[k] = round(float(np.mean(vals)), 4) if vals else 0.0
        agg["n_papers"] = max(len(v) for v in scores_dict.values()) if scores_dict else 0
        aggregated[method] = agg

    return aggregated


def print_table(aggregated: Dict[str, Dict[str, float]]):
    """打印对比表。"""
    if not aggregated:
        print("No results.")
        return

    # 定义展示顺序
    method_order = [
        "IdeaBench", "VanillaLLM", "AI-Scientist", "SciMON", "MOOSE-Chem", "SciAgents",
        "P1", "P2", "P3", "P4", "P5",
    ]
    methods = [m for m in method_order if m in aggregated]
    methods += [m for m in aggregated if m not in methods]

    # LLM Judge 维度
    judge_keys = ["judge_novelty", "judge_specificity", "judge_feasibility",
                  "judge_relevance", "judge_cross_disciplinary"]
    rouge_keys = ["rouge_rouge1", "rouge_rouge2", "rouge_rougeL"]
    struct_keys = ["struct_level_coverage", "struct_chain_coherence",
                   "struct_entity_grounding_rate", "struct_relation_diversity",
                   "struct_total_paths", "struct_avg_path_length"]

    print()
    print("=" * 110)
    print("  假设生成评估结果汇总 (6 篇论文 × 11 种方法)")
    print("=" * 110)

    # --- LLM Judge ---
    print()
    print("  ┌─ LLM-as-Judge 多维度评分 (1-10, 越高越好)")
    print(f"  │ {'Method':<18}", end="")
    short_names = {"judge_novelty": "Novel", "judge_specificity": "Specif",
                   "judge_feasibility": "Feasib", "judge_relevance": "Relev",
                   "judge_cross_disciplinary": "Cross"}
    for k in judge_keys:
        print(f"{short_names.get(k, k):<10}", end="")
    print(f"{'AVG':<10}")
    print(f"  │ {'─'*16}  ", end="")
    for _ in judge_keys:
        print(f"{'─'*8}  ", end="")
    print(f"{'─'*8}")

    for method in methods:
        agg = aggregated[method]
        vals = [agg.get(k, 0) for k in judge_keys]
        avg = round(np.mean(vals), 2) if vals else 0
        print(f"  │ {method:<18}", end="")
        for v in vals:
            print(f"{v:<10.2f}", end="")
        print(f"{avg:<10.2f}")
    print("  └─")

    # --- ROUGE ---
    print()
    print("  ┌─ ROUGE (文本相似度, 假设 vs 原文 abstract)")
    print(f"  │ {'Method':<18}", end="")
    for k in rouge_keys:
        print(f"{k.replace('rouge_', ''):<12}", end="")
    print()

    for method in methods:
        agg = aggregated[method]
        print(f"  │ {method:<18}", end="")
        for k in rouge_keys:
            v = agg.get(k, 0)
            print(f"{v:<12.4f}", end="")
        print()
    print("  └─")

    # --- Structural (P5 only) ---
    has_struct = any(aggregated[m].get("struct_level_coverage", 0) > 0 for m in methods)
    if has_struct:
        print()
        print("  ┌─ 结构化指标 (仅 P5)")
        p5_methods = [m for m in methods if aggregated[m].get("struct_level_coverage", 0) > 0]
        print(f"  │ {'Method':<18}", end="")
        short_struct = {"struct_level_coverage": "LvlCov", "struct_chain_coherence": "Chain",
                        "struct_entity_grounding_rate": "Grounding", "struct_relation_diversity": "RelDiv",
                        "struct_total_paths": "#Paths", "struct_avg_path_length": "AvgLen"}
        for k in struct_keys:
            print(f"{short_struct.get(k, k):<12}", end="")
        print()
        for method in p5_methods:
            agg = aggregated[method]
            print(f"  │ {method:<18}", end="")
            for k in struct_keys:
                v = agg.get(k, 0)
                print(f"{v:<12.4f}", end="")
            print()
        print("  └─")

    # --- General ---
    print()
    print("  ┌─ 通用指标")
    print(f"  │ {'Method':<18}{'AvgLen(chars)':<16}{'AvgTime(s)':<14}{'#Papers':<10}")
    for method in methods:
        agg = aggregated[method]
        print(f"  │ {method:<18}{agg.get('hypothesis_length', 0):<16.0f}"
              f"{agg.get('elapsed', 0):<14.1f}{agg.get('n_papers', 0):<10.0f}")
    print("  └─")
    print()


# =====================================================================
#  Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="评估 batch_results.json 中所有假设"
    )
    parser.add_argument("--input", default="baseline/outputs/batch_results.json",
                        help="batch_results.json 路径")
    parser.add_argument("--output", default="baseline/outputs/eval_results.json",
                        help="评估结果输出路径")
    parser.add_argument("--no-rouge", action="store_true",
                        help="跳过 ROUGE 计算")
    parser.add_argument("--no-llm-judge", action="store_true",
                        help="跳过 LLM-as-Judge")
    args = parser.parse_args()

    # 加载
    log(f"加载 {args.input}")
    with open(args.input, encoding="utf-8") as f:
        batch_data = json.load(f)

    total_items = sum(len(entry["results"]) for entry in batch_data)
    log(f"共 {len(batch_data)} 篇论文, {total_items} 个假设待评估")
    log(f"ROUGE: {'ON' if not args.no_rouge else 'OFF'}")
    log(f"LLM-as-Judge: {'ON' if not args.no_llm_judge else 'OFF'}")
    log("")

    # 逐篇评估
    all_evals = []
    total_t0 = time.time()
    item_count = 0

    for paper_idx, entry in enumerate(batch_data):
        tag = entry["tag"]
        paper = entry["paper"]
        results = entry["results"]

        log(f"{'═'*80}")
        log(f"[{paper_idx+1}/{len(batch_data)}] {tag}: {paper['title'][:55]}...")
        log(f"{'═'*80}")

        evaluations = []
        for r in results:
            method = r["method"]
            item_count += 1
            log(f"  [{item_count}/{total_items}] Evaluating {method}...")

            ev = evaluate_one(
                paper, r,
                use_rouge=not args.no_rouge,
                use_llm_judge=not args.no_llm_judge,
            )
            evaluations.append(ev)

            # 简要打印结果
            if ev.get("llm_judge"):
                j = ev["llm_judge"]
                scores_str = " ".join(f"{k[:3]}={v:.0f}" for k, v in j.items())
                log(f"    LLM Judge: {scores_str}")
            if ev.get("rouge"):
                rg = ev["rouge"]
                log(f"    ROUGE: R1={rg.get('rouge1',0):.3f} R2={rg.get('rouge2',0):.3f} RL={rg.get('rougeL',0):.3f}")

        all_evals.append({
            "tag": tag,
            "paper": {"title": paper["title"], "primary_discipline": paper.get("primary_discipline", "")},
            "evaluations": evaluations,
        })

        # 每篇论文完成后保存中间结果
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_evals, f, ensure_ascii=False, indent=2)

        log(f"[{paper_idx+1}/{len(batch_data)}] 完成")
        log("")

    total_elapsed = time.time() - total_t0
    log(f"全部评估完成! 总耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")

    # 聚合
    aggregated = aggregate_by_method(all_evals)

    # 打印表格
    print_table(aggregated)

    # 保存最终结果 (含聚合)
    final_output = {
        "per_paper": all_evals,
        "aggregated": aggregated,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    log(f"结果已保存到 {args.output}")


if __name__ == "__main__":
    main()

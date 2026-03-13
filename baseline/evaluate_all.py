"""
baseline/evaluate_all.py — 统一评估框架。

对所有 baseline 的输出同时计算：
A) IdeaBench 风格指标（自由文本）：BERTScore, ROUGE, BLEU, LLM-overlap
B) 我们的指标（结构化路径）：chain_coherence, info_novelty, rao_stirling, ...
C) 通用维度：novelty, specificity, feasibility (LLM-as-judge)

用法:
    python -m baseline.evaluate_all \
        --results baseline/outputs/all_results.json \
        --output baseline/outputs/eval_comparison.json
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("baseline.evaluate")

# ---------------------------------------------------------------------------
#  A) IdeaBench 风格指标（自由文本假设 vs 原文 abstract）
# ---------------------------------------------------------------------------

def compute_text_similarity_metrics(
    hypothesis: str,
    reference: str,
) -> Dict[str, float]:
    """
    IdeaBench 风格：BERTScore + ROUGE + BLEU。
    如果依赖库不可用则优雅降级。
    """
    scores: Dict[str, float] = {}

    # BERTScore
    try:
        from bert_score import BERTScorer
        scorer = BERTScorer(model_type="microsoft/deberta-xlarge-mnli", lang="en")
        P, R, F1 = scorer.score([hypothesis], [reference])
        scores["bertscore_p"] = round(P[0].item(), 4)
        scores["bertscore_r"] = round(R[0].item(), 4)
        scores["bertscore_f1"] = round(F1[0].item(), 4)
    except ImportError:
        # 降级：用 sentence-transformers cosine similarity
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            embs = model.encode([hypothesis, reference])
            cos = float(np.dot(embs[0], embs[1]) / (
                np.linalg.norm(embs[0]) * np.linalg.norm(embs[1]) + 1e-9
            ))
            scores["bertscore_f1"] = round(cos, 4)
        except ImportError:
            scores["bertscore_f1"] = 0.0

    # ROUGE
    try:
        import evaluate
        rouge = evaluate.load("rouge")
        result = rouge.compute(predictions=[hypothesis], references=[reference])
        scores["rouge1"] = round(result.get("rouge1", 0.0), 4)
        scores["rouge2"] = round(result.get("rouge2", 0.0), 4)
        scores["rougeL"] = round(result.get("rougeL", 0.0), 4)
    except (ImportError, Exception):
        scores["rouge1"] = 0.0
        scores["rouge2"] = 0.0
        scores["rougeL"] = 0.0

    # BLEU
    try:
        import evaluate
        bleu = evaluate.load("bleu")
        result = bleu.compute(predictions=[hypothesis], references=[reference])
        scores["bleu"] = round(result.get("bleu", 0.0), 4)
    except (ImportError, Exception):
        scores["bleu"] = 0.0

    return scores


# ---------------------------------------------------------------------------
#  B) LLM-as-Judge 多维评估（通用，适用于所有 baseline）
# ---------------------------------------------------------------------------

LLM_JUDGE_PROMPT = """你是一名科学假设评估专家。请对以下假设进行多维度评分（1-10分）。

论文标题：{title}
论文摘要：{abstract}

待评估假设：
{hypothesis}

请从以下维度评分，并输出 JSON：
{{
  "novelty": <1-10, 假设的新颖性，是否超越了原文已有结论>,
  "specificity": <1-10, 假设的具体性，是否可操作、可检验>,
  "feasibility": <1-10, 假设的可行性，是否在现有技术条件下可验证>,
  "relevance": <1-10, 与原文研究方向的相关性>,
  "cross_disciplinary": <1-10, 跨学科整合程度，是否融合了多个学科视角>
}}

只输出 JSON，不要输出其他内容。"""

def llm_judge_hypothesis(
    title: str,
    abstract: str,
    hypothesis: str,
) -> Dict[str, float]:
    """用 LLM 对假设进行多维度打分。"""
    from crossdisc_extractor.utils.llm import chat_completion_with_retry

    prompt = LLM_JUDGE_PROMPT.format(
        title=title, abstract=abstract, hypothesis=hypothesis,
    )
    try:
        resp = chat_completion_with_retry(
            [{"role": "user", "content": prompt}], temperature=0.0,
        )
        cleaned = resp.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        scores = json.loads(cleaned)
        return {k: float(v) for k, v in scores.items() if isinstance(v, (int, float))}
    except Exception as e:
        logger.warning("LLM judge failed: %s", e)
        return {
            "novelty": 0.0, "specificity": 0.0, "feasibility": 0.0,
            "relevance": 0.0, "cross_disciplinary": 0.0,
        }


# ---------------------------------------------------------------------------
#  C) 结构化路径指标（仅 CrossDisc 有，其他 baseline 为 N/A）
# ---------------------------------------------------------------------------

def compute_structural_metrics(
    structured_paths: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, float]:
    """计算结构化假设路径的客观指标。"""
    scores: Dict[str, float] = {}

    all_steps = []
    for level, paths in structured_paths.items():
        for path_obj in paths:
            steps = path_obj.get("steps", [])
            all_steps.extend(steps)

    if not all_steps:
        return {
            "chain_coherence": 0.0,
            "entity_grounding_rate": 0.0,
            "avg_path_length": 0.0,
            "relation_diversity": 0.0,
            "has_L1": 0.0, "has_L2": 0.0, "has_L3": 0.0,
        }

    # 层级覆盖
    scores["has_L1"] = 1.0 if structured_paths.get("L1") else 0.0
    scores["has_L2"] = 1.0 if structured_paths.get("L2") else 0.0
    scores["has_L3"] = 1.0 if structured_paths.get("L3") else 0.0

    # 平均路径长度
    path_lengths = []
    for level, paths in structured_paths.items():
        for p in paths:
            path_lengths.append(len(p.get("steps", [])))
    scores["avg_path_length"] = round(float(np.mean(path_lengths)), 2) if path_lengths else 0.0

    # 关系多样性
    relation_types = set()
    for step in all_steps:
        rt = (step.get("relation_type") or step.get("relation") or "").strip().lower()
        if rt:
            relation_types.add(rt)
    total_paths = sum(len(ps) for ps in structured_paths.values())
    scores["relation_diversity"] = round(len(relation_types) / max(total_paths, 1), 4)

    # 链式连贯性（step_i.tail == step_{i+1}.head）
    coherent_hops = 0
    total_hops = 0
    for level, paths in structured_paths.items():
        for p in paths:
            steps = p.get("steps", [])
            for i in range(len(steps) - 1):
                total_hops += 1
                tail_i = (steps[i].get("tail") or "").strip().lower()
                head_next = (steps[i + 1].get("head") or "").strip().lower()
                if tail_i and tail_i == head_next:
                    coherent_hops += 1
    scores["chain_coherence"] = round(coherent_hops / max(total_hops, 1), 4)

    # 实体 grounding rate（head/tail 非空且非通用词）
    generic_words = {"前提", "结论", "结果", "方法", "分析", "研究", "问题", "目标"}
    grounded = 0
    total_entities = 0
    for step in all_steps:
        for field in ("head", "tail"):
            ent = (step.get(field) or "").strip()
            total_entities += 1
            if ent and ent not in generic_words:
                grounded += 1
    scores["entity_grounding_rate"] = round(grounded / max(total_entities, 1), 4)

    return scores


# ---------------------------------------------------------------------------
#  D) 汇总评估
# ---------------------------------------------------------------------------

def evaluate_single_output(
    output: Dict[str, Any],
    paper: Dict[str, Any],
    use_llm_judge: bool = True,
) -> Dict[str, Any]:
    """对单个 baseline 的单篇论文输出进行全面评估。"""
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    method = output.get("method_name", "unknown")

    result = {
        "paper_id": output.get("paper_id"),
        "method": method,
        "elapsed_seconds": output.get("elapsed_seconds", 0),
    }

    # --- 自由文本指标 ---
    free_hyps = output.get("free_text_hypotheses", [])
    if free_hyps and abstract:
        # 取最佳假设（最长的非 error 假设）
        valid_hyps = [h for h in free_hyps if not h.startswith("[ERROR]")]
        if valid_hyps:
            best_hyp = max(valid_hyps, key=len)
            result["text_metrics"] = compute_text_similarity_metrics(best_hyp, abstract)
            if use_llm_judge:
                result["llm_judge"] = llm_judge_hypothesis(title, abstract, best_hyp)
            result["num_hypotheses"] = len(valid_hyps)
            result["avg_hypothesis_length"] = round(
                np.mean([len(h) for h in valid_hyps]), 1
            )
        else:
            result["text_metrics"] = {}
            result["llm_judge"] = {}
            result["num_hypotheses"] = 0

    # --- 结构化路径指标（仅 CrossDisc 有） ---
    struct_paths = output.get("structured_paths", {})
    if struct_paths:
        result["structural_metrics"] = compute_structural_metrics(struct_paths)
        # 统计路径数量
        for level in ("L1", "L2", "L3"):
            paths = struct_paths.get(level, [])
            result[f"{level}_path_count"] = len(paths)
    else:
        result["structural_metrics"] = None

    return result


def evaluate_all_outputs(
    all_outputs: List[Dict[str, Any]],
    papers: Dict[str, Dict[str, Any]],
    use_llm_judge: bool = True,
) -> List[Dict[str, Any]]:
    """批量评估所有 baseline 的所有输出。"""
    results = []
    for output in all_outputs:
        pid = output.get("paper_id", "")
        paper = papers.get(pid, {})
        if not paper:
            logger.warning("Paper %s not found, skipping", pid)
            continue
        r = evaluate_single_output(output, paper, use_llm_judge=use_llm_judge)
        results.append(r)
    return results


def aggregate_by_method(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """按 method 聚合，计算各指标的均值。"""
    from collections import defaultdict

    method_scores: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for r in results:
        method = r.get("method", "unknown")

        # 文本指标
        tm = r.get("text_metrics", {})
        for k, v in (tm or {}).items():
            method_scores[method][f"text_{k}"].append(v)

        # LLM judge
        lj = r.get("llm_judge", {})
        for k, v in (lj or {}).items():
            method_scores[method][f"judge_{k}"].append(v)

        # 结构化指标
        sm = r.get("structural_metrics")
        if sm:
            for k, v in sm.items():
                method_scores[method][f"struct_{k}"].append(v)

        # 通用
        if r.get("elapsed_seconds"):
            method_scores[method]["elapsed_seconds"].append(r["elapsed_seconds"])
        if r.get("num_hypotheses"):
            method_scores[method]["num_hypotheses"].append(r["num_hypotheses"])

    # 计算均值
    aggregated = {}
    for method, scores_dict in method_scores.items():
        agg = {}
        for k, vals in scores_dict.items():
            agg[k] = round(float(np.mean(vals)), 4) if vals else 0.0
        aggregated[method] = agg

    return aggregated


def print_comparison_table(aggregated: Dict[str, Dict[str, Any]]):
    """打印对比表格。"""
    if not aggregated:
        print("No results to display.")
        return

    methods = sorted(aggregated.keys())
    # 收集所有指标
    all_metrics = set()
    for scores in aggregated.values():
        all_metrics.update(scores.keys())
    all_metrics = sorted(all_metrics)

    # 分组打印
    groups = {
        "Text Similarity (IdeaBench-style)": [m for m in all_metrics if m.startswith("text_")],
        "LLM Judge (multi-dim)": [m for m in all_metrics if m.startswith("judge_")],
        "Structural (CrossDisc-only)": [m for m in all_metrics if m.startswith("struct_")],
        "General": [m for m in all_metrics if not any(m.startswith(p) for p in ("text_", "judge_", "struct_"))],
    }

    print("\n" + "=" * 80)
    print("  BASELINE COMPARISON RESULTS")
    print("=" * 80)

    for group_name, metrics in groups.items():
        if not metrics:
            continue
        print(f"\n--- {group_name} ---")
        # Header
        header = f"{'Metric':<35}" + "".join(f"{m:<20}" for m in methods)
        print(header)
        print("-" * len(header))
        for metric in metrics:
            row = f"{metric:<35}"
            for method in methods:
                val = aggregated[method].get(metric)
                if val is not None:
                    row += f"{val:<20.4f}"
                else:
                    row += f"{'N/A':<20}"
            print(row)

    print("\n" + "=" * 80)


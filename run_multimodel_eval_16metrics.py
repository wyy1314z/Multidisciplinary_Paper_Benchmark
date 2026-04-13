"""
run_multimodel_eval_16metrics.py — 多模型 16 指标评测脚本

将 model_results/ 中 13 个模型的自由文本假设：
  1. 用 LLM 解析为结构化推理路径 (head→relation→tail)
  2. 复用 evaluate_benchmark.py 的 16 指标评估引擎
  3. 按 (model, prompt_level) 聚合结果
  4. 输出 summary JSON 供雷达图使用

Usage:
    python run_multimodel_eval_16metrics.py \
        --model-results-dir outputs/multimodel_eval_v7/model_results \
        --benchmark outputs/multimodel_eval_v7/benchmark_dataset.json \
        --test-data outputs/multimodel_eval_v7/test_extraction.json \
        --output-dir outputs/multimodel_eval_v7 \
        --taxonomy data/msc_converted.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("multimodel_eval")


def _sanitize_model_name(model_name: str) -> str:
    return model_name.replace("/", "_").replace(":", "_")


# ---------------------------------------------------------------------------
# LLM 调用: 文本→结构化路径解析
# ---------------------------------------------------------------------------

PARSE_PROMPT = """\
你是一个科研假设分析专家。请将以下假设文本拆解为结构化的推理路径。

假设文本中可能包含 L1（宏观）、L2（中层）、L3（深层）三个层次的假设。
请从文本中识别出不同层次的假设，每条假设提取为一条推理路径。
每条路径由 2-5 个步骤组成，每步包含:
- step: 步骤编号 (从1开始)
- head: 起始概念/实体
- relation: 关系类型 (如: enables, causes, inhibits, transforms, requires 等)
- tail: 目标概念/实体
- claim: 该步骤的推理声明 (一句话总结)

请严格按以下 JSON 格式输出，不要输出其他内容:
```json
{
  "L1": [
    [{"step": 1, "head": "概念A", "relation": "enables", "tail": "概念B", "claim": "A使得B成为可能"},
     {"step": 2, "head": "概念B", "relation": "causes", "tail": "概念C", "claim": "B导致了C"}]
  ],
  "L2": [
    [{"step": 1, "head": "...", "relation": "...", "tail": "...", "claim": "..."}]
  ],
  "L3": [
    [{"step": 1, "head": "...", "relation": "...", "tail": "...", "claim": "..."}]
  ]
}
```

如果某个层次在文本中没有出现，对应的列表为空 []。
如果文本只有一个整体假设（没有明确分层），全部归入 L1。

假设文本:
{text}
"""


def _parse_cache_path(cache_dir: str, text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{h}.json")


def parse_hypothesis_to_paths(
    text: str,
    cache_dir: Optional[str] = None,
) -> Dict[str, List[List[Dict]]]:
    """用 LLM 将自由文本假设解析为结构化路径。"""

    if not text or text.startswith("[ERROR]"):
        return {}

    # Check cache
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = _parse_cache_path(cache_dir, text)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    from crossdisc_extractor.utils.llm import chat_completion_with_retry

    prompt = PARSE_PROMPT.replace("{text}", text[:6000])
    messages = [{"role": "user", "content": prompt}]

    try:
        resp = chat_completion_with_retry(messages, temperature=0.0)
        # Extract JSON from response
        resp = resp.strip()
        # Try to find JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", resp, re.DOTALL)
        if json_match:
            resp = json_match.group(1)
        elif not resp.startswith("{"):
            # Try to find first { ... }
            brace_start = resp.find("{")
            brace_end = resp.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                resp = resp[brace_start : brace_end + 1]

        parsed = json.loads(resp)

        # Validate structure
        result: Dict[str, List[List[Dict]]] = {}
        for level in ["L1", "L2", "L3"]:
            paths = parsed.get(level, [])
            if not isinstance(paths, list):
                paths = []
            valid_paths = []
            for path in paths:
                if isinstance(path, list) and all(isinstance(s, dict) for s in path):
                    # Ensure each step has required fields
                    for i, step in enumerate(path):
                        step.setdefault("step", i + 1)
                        step.setdefault("head", "")
                        step.setdefault("relation", "")
                        step.setdefault("tail", "")
                        step.setdefault("claim", "")
                    valid_paths.append(path)
            result[level] = valid_paths

        # Save cache
        if cache_dir:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    except Exception as e:
        logger.warning("解析假设文本失败: %s (text[:80]=%s)", e, text[:80])
        return {}


# ---------------------------------------------------------------------------
# Build paper metadata map from extraction or query-eval JSON
# ---------------------------------------------------------------------------

def build_paper_map(test_data_path: str, input_mode: str = "auto") -> Dict[str, Dict[str, Any]]:
    """构建 paper_id → 元数据 映射。

    Supported input modes:
    - extraction: raw extraction result items containing parsed/meta/查询/概念
    - query_eval: query-centric rows built by scripts/build_query_eval_set.py
    - auto: infer from the first item
    """
    with open(test_data_path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        return {}

    if input_mode == "auto":
        first = items[0]
        if "parsed" in first:
            input_mode = "extraction"
        elif "queries" in first:
            input_mode = "query_eval"
        else:
            raise ValueError("无法自动识别 test-data 格式，请显式指定 --input-mode")

    paper_map = {}
    for item in items:
        if input_mode == "query_eval":
            title = item.get("title", "")
            pid = item.get("paper_id") or hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
            queries = item.get("queries", {})
            paper_map[pid] = {
                "title": title,
                "abstract": item.get("abstract", ""),
                "primary": item.get("primary_discipline", ""),
                "secondary_list": item.get("secondary_disciplines", []),
                "l1_query": queries.get("L1", ""),
                "l2_queries": queries.get("L2", []),
                "l3_queries": queries.get("L3", []),
                "gt_terms": item.get("gt_terms", []),
                "gt_relations": item.get("gt_relations", []),
                "metadata": item.get("metadata", {}),
            }
            continue

        parsed = item.get("parsed", {})
        meta = parsed.get("meta", {})
        title = meta.get("title", item.get("title", ""))
        pid = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]

        queries = parsed.get("查询", {})
        concepts = parsed.get("概念", {})

        gt_terms = []
        for c in concepts.get("主学科", []):
            t = (c.get("normalized") or c.get("term", "")).strip()
            if t:
                gt_terms.append(t)
        for disc, clist in concepts.get("辅学科", {}).items():
            for c in clist:
                t = (c.get("normalized") or c.get("term", "")).strip()
                if t:
                    gt_terms.append(t)

        gt_relations = parsed.get("跨学科关系", [])

        paper_map[pid] = {
            "title": title,
            "abstract": item.get("abstract", ""),
            "primary": meta.get("primary", ""),
            "secondary_list": meta.get("secondary_list", []),
            "l1_query": queries.get("一级", ""),
            "l2_queries": queries.get("二级", []),
            "l3_queries": queries.get("三级", []),
            "gt_terms": gt_terms,
            "gt_relations": gt_relations,
            "metadata": {
                "journal": meta.get("journal", item.get("journal", "")),
                "fwci": meta.get("fwci", item.get("fwci")),
                "cited_by_count": meta.get("cited_by_count", item.get("cited_by_count")),
            },
        }

    logger.info("论文元数据映射: %d 篇", len(paper_map))
    return paper_map


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="多模型 16 指标评测")
    parser.add_argument("--model-results-dir", required=True, help="模型结果目录")
    parser.add_argument("--benchmark", required=True, help="Benchmark GT 数据集 (构建 KG)")
    parser.add_argument("--test-data", required=True, help="test_extraction.json (论文元数据)")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--taxonomy", default=None, help="学科分类树 JSON")
    parser.add_argument("--input-mode", choices=["auto", "extraction", "query_eval"], default="auto")
    parser.add_argument("--max-items", type=int, default=None, help="每个模型最多评测 N 条")
    parser.add_argument("--include-models", nargs="*", default=None, help="只评测这些模型名")
    parser.add_argument("--skip-models", nargs="*", default=[], help="跳过的模型名")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    parse_cache_dir = os.path.join(args.output_dir, "parse_cache")
    os.makedirs(parse_cache_dir, exist_ok=True)

    # 1. 构建全局知识图谱
    logger.info("=" * 70)
    logger.info("Step 1: 构建全局知识图谱 (GlobalKG)")
    from crossdisc_extractor.benchmark.evaluate_benchmark import (
        GlobalKG,
        evaluate_single_path,
        normalize_paths_structure,
        structural_diversity,
        hierarchical_depth_progression,
    )

    kg = GlobalKG(args.benchmark, taxonomy_path=args.taxonomy)

    # 2. 加载论文元数据
    logger.info("Step 2: 加载论文元数据")
    paper_map = build_paper_map(args.test_data, input_mode=args.input_mode)

    # 3. 遍历模型结果
    model_files = sorted(glob.glob(os.path.join(args.model_results_dir, "*.json")))
    logger.info("Step 3: 开始评测 %d 个模型", len(model_files))

    all_results: List[Dict[str, Any]] = []
    included_models = (
        {_sanitize_model_name(model_name) for model_name in args.include_models}
        if args.include_models
        else None
    )
    skipped_models = {_sanitize_model_name(model_name) for model_name in (args.skip_models or [])}

    for model_file in model_files:
        model_name = os.path.basename(model_file).replace(".json", "")
        if included_models is not None and model_name not in included_models:
            logger.info("[%s] 跳过 (不在 include-models 中)", model_name)
            continue
        if model_name in skipped_models:
            logger.info("[%s] 跳过 (用户指定)", model_name)
            continue

        with open(model_file, encoding="utf-8") as f:
            records = json.load(f)

        # Skip models with all errors
        valid_records = [r for r in records if not r.get("error")]
        if not valid_records:
            logger.warning("[%s] 所有 %d 条记录均失败，跳过", model_name, len(records))
            continue

        logger.info("=" * 70)
        logger.info("[%s] 开始评测: %d/%d 条有效记录", model_name, len(valid_records), len(records))

        if args.max_items:
            valid_records = valid_records[: args.max_items]

        for rec_idx, record in enumerate(valid_records):
            pid = record.get("paper_id", "")
            method = record.get("method_name", "")
            hyp_text = (record.get("free_text_hypotheses") or [""])[0]

            paper = paper_map.get(pid)
            if not paper:
                logger.warning("[%s] paper_id=%s 未找到元数据，跳过", model_name, pid)
                continue

            logger.info("-" * 50)
            logger.info("[%s] [%d/%d] %s | %s | '%s'",
                        model_name, rec_idx + 1, len(valid_records),
                        method, pid, paper["title"][:40])

            # 3a. 解析文本 → 结构化路径
            t0 = time.time()
            parsed_paths = parse_hypothesis_to_paths(hyp_text, cache_dir=parse_cache_dir)
            parse_time = time.time() - t0

            total_paths = sum(len(v) for v in parsed_paths.values())
            logger.info("[%s] 解析完成: L1=%d L2=%d L3=%d (%.1fs)",
                        model_name,
                        len(parsed_paths.get("L1", [])),
                        len(parsed_paths.get("L2", [])),
                        len(parsed_paths.get("L3", [])),
                        parse_time)

            if total_paths == 0:
                logger.warning("[%s] 未解析出任何路径，跳过评测", model_name)
                all_results.append({
                    "model": model_name,
                    "method": method,
                    "paper_id": pid,
                    "title": paper["title"],
                    "parse_error": True,
                    "scores": {},
                })
                continue

            # 3b. 检索 GT 参考路径
            l1_query = paper["l1_query"] or f"关于 {paper['primary']} 的 {paper['title']} 的跨学科研究假设"
            gt_set = kg.retrieve_relevant_paths(paper["primary"], l1_query, k=3)
            logger.info("[%s] GT 参考路径: %d 条", model_name, len(gt_set))

            if not gt_set:
                logger.warning("[%s] 无 GT 参考路径，跳过", model_name)
                continue

            # 3c. 逐 level 评估
            item_scores: Dict[str, list] = defaultdict(list)

            for level in ["L1", "L2", "L3"]:
                level_paths = parsed_paths.get(level, [])
                if not level_paths:
                    continue

                for pi, path in enumerate(level_paths):
                    try:
                        s = evaluate_single_path(
                            path,
                            gt_set,
                            l1_query,
                            paper["primary"],
                            level,
                            gen_query=l1_query,
                            kg=kg,
                            gt_terms=paper.get("gt_terms"),
                            gt_relations=paper.get("gt_relations"),
                            gt_evidence_paths=None,
                            abstract=paper["abstract"],
                            _item_id=f"{model_name}_{pid}",
                            _path_idx=pi,
                        )
                        for k, v in s.items():
                            item_scores[f"{level}_{k}"].append(v)
                    except Exception as e:
                        logger.error("[%s] 评估失败 %s[%d]: %s", model_name, level, pi, e)

            # Structural diversity (per-level)
            for lvl in ["L1", "L2", "L3"]:
                lvl_paths = parsed_paths.get(lvl, [])
                if lvl_paths:
                    sd = structural_diversity(lvl_paths)
                    for sdk, sdv in sd.items():
                        item_scores[f"{lvl}_{sdk}"].append(sdv)

            # Hierarchical depth progression
            hdp = hierarchical_depth_progression(
                parsed_paths.get("L1", []),
                parsed_paths.get("L2", []),
                parsed_paths.get("L3", []),
            )
            for hdp_k, hdp_v in hdp.items():
                item_scores[f"depth_{hdp_k}"].append(hdp_v)

            # Average scores
            avg_scores = {k: float(np.mean(v)) if v else 0.0 for k, v in item_scores.items()}

            all_results.append({
                "model": model_name,
                "method": method,
                "paper_id": pid,
                "title": paper["title"],
                "parse_error": False,
                "scores": avg_scores,
            })

            # Log summary
            key_metrics = ["L1_consistency_f1", "L1_innovation", "L1_factual_precision",
                           "L1_rao_stirling", "L1_chain_coherence", "L1_testability"]
            parts = [f"{m.replace('L1_','')}={avg_scores.get(m, 0):.3f}" for m in key_metrics if m in avg_scores]
            logger.info("[%s] 评分摘要: %s", model_name, "  ".join(parts))

    # 4. 保存详细结果
    detail_path = os.path.join(args.output_dir, "multimodel_16metrics_results.json")
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info("详细结果已保存: %s", detail_path)

    # 5. 聚合: 按 (model, method) 分组
    agg: Dict[str, Dict[str, Dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for r in all_results:
        if r.get("parse_error"):
            continue
        model = r["model"]
        method = r["method"]
        for k, v in r["scores"].items():
            agg[model][method][k].append(v)

    summary: Dict[str, Dict[str, Dict[str, float]]] = {}
    for model, methods in sorted(agg.items()):
        summary[model] = {}
        for method, metrics in sorted(methods.items()):
            summary[model][method] = {
                k: round(float(np.mean(v)), 4) for k, v in sorted(metrics.items())
            }

    # Also compute per-model overall average (across all methods)
    model_overall: Dict[str, Dict[str, float]] = {}
    for model, methods in summary.items():
        all_metric_vals: Dict[str, list] = defaultdict(list)
        for method, scores in methods.items():
            for k, v in scores.items():
                all_metric_vals[k].append(v)
        model_overall[model] = {
            k: round(float(np.mean(v)), 4) for k, v in sorted(all_metric_vals.items())
        }

    final_summary = {
        "by_model_method": summary,
        "by_model_overall": model_overall,
    }

    summary_path = os.path.join(args.output_dir, "multimodel_16metrics_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
    logger.info("聚合摘要已保存: %s", summary_path)

    # 6. Print summary table
    print("\n" + "=" * 90)
    print("多模型 16 指标评测结果总览")
    print("=" * 90)

    # Core 6 metrics for display
    display_metrics = [
        "L1_innovation", "L1_testability", "L1_consistency_f1",
        "L1_rao_stirling", "L1_factual_precision", "L1_atypical_combination",
    ]
    short_names = ["innov", "test", "cons_f1", "rao_stir", "fact_prec", "atyp_comb"]

    header = f"{'Model':<30s}" + "".join(f"{n:>10s}" for n in short_names)
    print(header)
    print("-" * 90)

    for model in sorted(model_overall.keys()):
        vals = model_overall[model]
        row = f"{model:<30s}"
        for m in display_metrics:
            v = vals.get(m, 0.0)
            row += f"{v:>10.4f}"
        print(row)

    print("=" * 90)
    print(f"\n评测完成。共 {len(all_results)} 条记录, {len(model_overall)} 个有效模型。")


if __name__ == "__main__":
    main()

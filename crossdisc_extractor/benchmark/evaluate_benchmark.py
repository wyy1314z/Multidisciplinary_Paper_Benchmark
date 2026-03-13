"""
evaluate_benchmark.py — Multi-dimensional hypothesis evaluation.

v2 changes:
- Replaced Jaccard bridging with Rao-Stirling diversity + embedding distance
- Added relation-aware Path Consistency (Precision / Recall / F1)
- Added Information-Theoretic Novelty (surprisal)
- Added Reasoning Chain Coherence
- Added Structural Diversity (Torrance-inspired)
- Added Hierarchical Depth Progression
- Added Testability Score (LLM)
- Added Coverage into final scoring
- Improved GT retrieval with jieba (optional BM25 fallback)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import random
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from crossdisc_extractor.benchmark.eval_prompts import PROMPT_EVAL_DEEP, PROMPT_EVAL_L1, PROMPT_TESTABILITY
from crossdisc_extractor.benchmark.metrics import (
    _build_discipline_paths,
    _load_taxonomy,
    atypical_combination_index,
    build_cooccurrence_from_kg,
    concept_coverage,
    embedding_bridging_score,
    enhanced_path_consistency,
    hierarchical_depth_progression,
    information_theoretic_novelty,
    path_semantic_alignment,
    rao_stirling_diversity,
    reasoning_chain_coherence,
    relation_precision,
    structural_diversity,
)
from crossdisc_extractor.utils.llm import chat_completion_with_retry

logger = logging.getLogger("eval_kg")

# ---------------------------------------------------------------------------
# Optional: jieba for Chinese tokenization
# ---------------------------------------------------------------------------
try:
    import jieba

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# Default taxonomy path
import os

_DEFAULT_TAXONOMY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "msc_converted.json",
)


# ===========================================================================
#  Utility: Stable path hash
# ===========================================================================

def _path_hash(path: List[Dict]) -> str:
    """以路径内容的 MD5 作为稳定缓存键。"""
    content = json.dumps(path, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ===========================================================================
#  Tokenization — improved Chinese support
# ===========================================================================

def _tokenize_for_bridging(text: str) -> set:
    """
    中英文混合文本的分词：
    - 有 jieba: 使用 jieba 词级分词（保留语义单元）
    - 无 jieba: 英文按词切分 + 中文逐字切分（降级方案）
    """
    text = (text or "").lower().strip()
    if _HAS_JIEBA:
        tokens = set(jieba.cut(text))
        tokens.discard("")
        tokens.discard(" ")
        return tokens
    # fallback
    en_tokens = set(re.findall(r"[a-z0-9]+", text))
    zh_tokens = set(re.findall(r"[\u4e00-\u9fff]", text))
    return en_tokens | zh_tokens


def _text_to_vector(text: str) -> Counter:
    """Tokenize and count for cosine similarity."""
    if _HAS_JIEBA:
        words = list(jieba.cut(text.lower()))
        return Counter(w for w in words if w.strip())
    return Counter(re.findall(r"\w+", text.lower()))


def _cosine_sim(vec1: Counter, vec2: Counter) -> float:
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(vec1[x] ** 2 for x in vec1)
    sum2 = sum(vec2[x] ** 2 for x in vec2)
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    if not denominator:
        return 0.0
    return numerator / denominator


# ===========================================================================
#  Graph Metric Evaluator (enhanced)
# ===========================================================================

class GraphMetricEvaluator:
    """基于图结构的客观评测指标计算器（v2: 关系感知 + 多维度）。"""

    @staticmethod
    def calculate_path_consistency(gen_path: List[Dict], gt_paths: List[Dict]) -> float:
        """Legacy path consistency (head,tail matching). Kept for backward compat."""
        if not gen_path:
            return 0.0
        gt_triples: set = set()
        for gt_item in gt_paths:
            for step in gt_item.get("path", []):
                h = (step.get("head") or "").strip().lower()
                t = (step.get("tail") or "").strip().lower()
                gt_triples.add((h, t))
        if not gt_triples:
            return 0.0
        matched_steps = 0.0
        for step in gen_path:
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            if (h, t) in gt_triples:
                matched_steps += 1
            elif (t, h) in gt_triples:
                matched_steps += 0.5
        return matched_steps / len(gen_path)

    @staticmethod
    def calculate_enhanced_consistency(gen_path: List[Dict], gt_paths: List[Dict]) -> Dict[str, float]:
        """Relation-aware path consistency with P/R/F1."""
        return enhanced_path_consistency(gen_path, gt_paths)

    @staticmethod
    def calculate_bridging_score(gen_path: List[Dict]) -> float:
        """Legacy Jaccard bridging (kept for backward compat)."""
        if not gen_path:
            return 0.0
        start_node = (gen_path[0].get("head") or "").strip()
        end_node = (gen_path[-1].get("tail") or "").strip()
        start_terms = _tokenize_for_bridging(start_node)
        end_terms = _tokenize_for_bridging(end_node)
        if not start_terms or not end_terms:
            return 0.0
        intersection = len(start_terms & end_terms)
        union = len(start_terms | end_terms)
        if union == 0:
            return 0.0
        return 1.0 - (intersection / union)

    @staticmethod
    def calculate_embedding_bridging(gen_path: List[Dict]) -> float:
        """Embedding-based semantic bridging distance."""
        return embedding_bridging_score(gen_path)

    @staticmethod
    def calculate_chain_coherence(gen_path: List[Dict]) -> float:
        """Per-hop reasoning chain coherence."""
        result = reasoning_chain_coherence(gen_path)
        return result["overall_coherence"]

    @staticmethod
    def calculate_info_novelty(
        gen_path: List[Dict], all_kg_triples: Counter, total_triples: int
    ) -> float:
        """Information-theoretic novelty (normalized surprisal)."""
        result = information_theoretic_novelty(gen_path, all_kg_triples, total_triples)
        return result["normalized_novelty"]


# ===========================================================================
#  Path structure normalization
# ===========================================================================

def normalize_paths_structure(raw_data: List[Any]) -> List[List[Dict[str, Any]]]:
    """
    规范化路径数据结构。兼容嵌套列表 / 扁平列表两种格式。
    """
    if not raw_data:
        return []
    if isinstance(raw_data[0], list):
        return raw_data
    if isinstance(raw_data[0], dict):
        paths: list = []
        current_path: list = []
        for step in raw_data:
            step_num = step.get("step")
            if step_num == 1 and current_path:
                paths.append(current_path)
                current_path = []
            current_path.append(step)
        if current_path:
            paths.append(current_path)
        return paths
    return []


# ===========================================================================
#  Global Knowledge Graph
# ===========================================================================

class GlobalKG:
    """基于 Benchmark 数据集构建的全局知识图谱（按学科索引路径）。"""

    def __init__(self, benchmark_path: str, taxonomy_path: Optional[str] = None):
        self.paths_by_discipline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.path_vectors: Dict[str, Counter] = {}
        self.all_triples: Counter = Counter()
        self.total_triples: int = 0
        self.all_flat_paths: List[List[Dict[str, Any]]] = []
        self.node_disciplines: Dict[str, str] = {}

        # Taxonomy for Rao-Stirling
        tax_path = taxonomy_path or _DEFAULT_TAXONOMY
        try:
            taxonomy = _load_taxonomy(tax_path)
            self.disc_paths = _build_discipline_paths(taxonomy)
            self.max_depth = max((len(p) for p in self.disc_paths.values()), default=1)
        except Exception:
            self.disc_paths = {}
            self.max_depth = 1

        # Co-occurrence for atypical combination
        self.cooccurrence: Counter = Counter()
        self.cooc_mu: float = 0.0
        self.cooc_sigma: float = 0.0

        self.load_benchmark(benchmark_path)

    def load_benchmark(self, path: str):
        logger.info("正在加载 Benchmark 数据集构建知识图谱: %s", path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for item in data:
            if "parsed" in item:
                parsed = item["parsed"]
                meta = parsed.get("meta", {})
                primary = meta.get("primary", "unknown")
                hyp = parsed.get("假设", {})
                paths_dict = {
                    "L1": hyp.get("一级", []),
                    "L2": hyp.get("二级", []),
                    "L3": hyp.get("三级", []),
                }
                item_id = str(hash(meta.get("title", "")))
                abstract = item.get("abstract", "")

                # Collect node disciplines from concepts
                concepts = parsed.get("概念", {})
                for c in concepts.get("主学科", []):
                    ent = (c.get("normalized") or c.get("term", "")).strip().lower()
                    if ent:
                        self.node_disciplines[ent] = primary
                for disc, clist in concepts.get("辅学科", {}).items():
                    for c in clist:
                        ent = (c.get("normalized") or c.get("term", "")).strip().lower()
                        if ent:
                            self.node_disciplines[ent] = disc
            else:
                primary = item["input"].get("primary_discipline", "unknown")
                gt = item.get("ground_truth", {})
                paths_dict = gt.get("hypothesis_paths", {})
                item_id = item["id"]
                abstract = item["input"].get("abstract", "")

            for level in ["L1", "L2", "L3"]:
                raw_paths = paths_dict.get(level, [])
                normalized_paths = normalize_paths_structure(raw_paths)
                for p in normalized_paths:
                    path_obj = {
                        "path": p,
                        "level": level,
                        "source_id": item_id,
                        "context": abstract,
                    }
                    self.paths_by_discipline[primary].append(path_obj)
                    self.all_flat_paths.append(p)

                    cache_key = _path_hash(p)
                    path_obj["_cache_key"] = cache_key
                    self.path_vectors[cache_key] = _text_to_vector(
                        json.dumps(p, ensure_ascii=False)
                    )

                    # Build triple index for info novelty
                    for step in p:
                        h = (step.get("head") or "").strip().lower()
                        r = (step.get("relation") or "").strip().lower()
                        t = (step.get("tail") or "").strip().lower()
                        if h and t:
                            self.all_triples[(h, r, t)] += 1
                            self.total_triples += 1

                    count += 1

        # Build co-occurrence for atypical combination
        self.cooccurrence, self.cooc_mu, self.cooc_sigma = build_cooccurrence_from_kg(
            self.all_flat_paths
        )

        logger.info("KG 构建完成。共索引 %d 条路径，覆盖 %d 个学科。", count, len(self.paths_by_discipline))

    def retrieve_relevant_paths(self, discipline: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        candidates = self.paths_by_discipline.get(discipline, [])
        if not candidates:
            all_paths = [p for paths in self.paths_by_discipline.values() for p in paths]
            if not all_paths:
                return []
            return random.sample(all_paths, min(k, len(all_paths)))

        query_vec = _text_to_vector(query)
        scored_candidates = []
        for cand in candidates:
            cache_key = cand.get("_cache_key") or _path_hash(cand["path"])
            cand_vec = self.path_vectors.get(cache_key)
            if not cand_vec:
                cand_vec = _text_to_vector(json.dumps(cand["path"], ensure_ascii=False))
            score = _cosine_sim(query_vec, cand_vec)
            scored_candidates.append((score, cand))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in scored_candidates[:k]]


# ===========================================================================
#  Formatting helpers
# ===========================================================================

def format_path_for_prompt(path_obj: List[Dict[str, Any]]) -> str:
    lines = []
    for step in path_obj:
        lines.append(
            f"  Step {step.get('step')}: {step.get('head')} "
            f"--[{step.get('relation')}]--> {step.get('tail')} "
            f"(Claim: {step.get('claim')})"
        )
    return "\n".join(lines)


def format_gt_set(gt_paths: List[Dict[str, Any]]) -> str:
    out = []
    for i, item in enumerate(gt_paths, 1):
        p_str = format_path_for_prompt(item["path"])
        out.append(f"参考路径 #{i} (Level {item['level']}):\n{p_str}")
    return "\n\n".join(out)


# ===========================================================================
#  LLM score parsing
# ===========================================================================

def parse_llm_score(response: str, fields: Optional[List[str]] = None) -> Dict[str, float]:
    """Parse LLM JSON response. *fields* lists expected score keys."""
    if fields is None:
        fields = ["innovation_score", "feasibility_score", "scientificity_score"]
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        data = json.loads(cleaned)
        return {k.replace("_score", ""): float(data.get(k, 0)) for k in fields}
    except Exception as e:
        logger.warning("解析评分失败: %s. Response: %s", e, response[:200])
        return {k.replace("_score", ""): 0.0 for k in fields}


# ===========================================================================
#  Single-path evaluation
# ===========================================================================

def evaluate_single_path(
    path: List[Dict[str, Any]],
    gt_paths: List[Dict[str, Any]],
    query: str,
    discipline: str,
    level: str,
    gen_query: str = "",
    kg: Optional[GlobalKG] = None,
    gt_terms: Optional[List[str]] = None,
    gt_relations: Optional[List[Dict[str, Any]]] = None,
    gt_evidence_paths: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """Evaluate a single hypothesis path with graph + LLM + GT-aware metrics."""

    scores: Dict[str, float] = {}

    # ── Graph metrics (objective) ──────────────────────────────────────

    # Legacy consistency (backward compat)
    scores["consistency"] = GraphMetricEvaluator.calculate_path_consistency(path, gt_paths)

    # Enhanced consistency (P/R/F1)
    enhanced = GraphMetricEvaluator.calculate_enhanced_consistency(path, gt_paths)
    scores["consistency_precision"] = enhanced["consistency_precision"]
    scores["consistency_recall"] = enhanced["consistency_recall"]
    scores["consistency_f1"] = enhanced["consistency_f1"]

    # Bridging — legacy + embedding-based
    scores["bridging"] = GraphMetricEvaluator.calculate_bridging_score(path)
    scores["embedding_bridging"] = GraphMetricEvaluator.calculate_embedding_bridging(path)

    # Chain coherence
    scores["chain_coherence"] = GraphMetricEvaluator.calculate_chain_coherence(path)

    # Information-theoretic novelty
    if kg is not None:
        scores["info_novelty"] = GraphMetricEvaluator.calculate_info_novelty(
            path, kg.all_triples, kg.total_triples
        )
        # Atypical combination
        scores["atypical_combination"] = atypical_combination_index(
            path, kg.cooccurrence, kg.cooc_mu, kg.cooc_sigma
        )
        # Rao-Stirling diversity
        scores["rao_stirling"] = rao_stirling_diversity(
            path, kg.node_disciplines, kg.disc_paths, kg.max_depth
        )
    else:
        scores["info_novelty"] = 0.0
        scores["atypical_combination"] = 0.0
        scores["rao_stirling"] = 0.0

    # ── Evidence-grounded GT metrics (v3) ──────────────────────────────

    if gt_terms:
        cc = concept_coverage(path, gt_terms)
        scores["concept_recall"] = cc["concept_recall"]
        scores["concept_precision"] = cc["concept_precision"]
        scores["concept_f1"] = cc["concept_f1"]
    else:
        scores["concept_recall"] = 0.0
        scores["concept_precision"] = 0.0
        scores["concept_f1"] = 0.0

    if gt_relations:
        rp = relation_precision(path, gt_relations)
        scores["relation_precision"] = rp["relation_precision"]
        scores["relation_type_accuracy"] = rp["relation_type_accuracy"]
        scores["evidence_coverage"] = rp["evidence_coverage"]
    else:
        scores["relation_precision"] = 0.0
        scores["relation_type_accuracy"] = 0.0
        scores["evidence_coverage"] = 0.0

    if gt_evidence_paths:
        pa = path_semantic_alignment(path, gt_evidence_paths)
        scores["path_alignment_best"] = pa["best_alignment"]
        scores["path_alignment_mean"] = pa["mean_alignment"]
    else:
        scores["path_alignment_best"] = 0.0
        scores["path_alignment_mean"] = 0.0

    # ── LLM evaluation (subjective) ───────────────────────────────────

    path_str = format_path_for_prompt(path)
    gt_str = format_gt_set(gt_paths)

    if level == "L1":
        sys_prompt = PROMPT_EVAL_L1.format(
            query=query, discipline=discipline, gt_paths=gt_str, gen_path=path_str
        )
    else:
        sys_prompt = PROMPT_EVAL_DEEP.format(
            level_name="中层" if level == "L2" else "深层",
            level=level,
            query=query,
            gen_query=gen_query,
            gt_paths=gt_str,
            gen_path=path_str,
        )

    messages = [{"role": "user", "content": sys_prompt}]
    try:
        resp = chat_completion_with_retry(messages, temperature=0.0)
        llm_scores = parse_llm_score(resp)
    except Exception as e:
        logger.error("LLM 评估请求失败: %s", e)
        llm_scores = {"innovation": 0.0, "feasibility": 0.0, "scientificity": 0.0}

    scores.update(llm_scores)

    # ── Testability (LLM) ─────────────────────────────────────────────

    try:
        test_prompt = PROMPT_TESTABILITY.format(hypothesis_path=path_str)
        test_msgs = [{"role": "user", "content": test_prompt}]
        test_resp = chat_completion_with_retry(test_msgs, temperature=0.0)
        test_scores = parse_llm_score(
            test_resp,
            fields=["specificity", "measurability", "falsifiability", "resource_feasibility"],
        )
        scores["testability"] = float(np.mean(list(test_scores.values())))
    except Exception as e:
        logger.warning("Testability 评估失败: %s", e)
        scores["testability"] = 0.0

    return scores


# ===========================================================================
#  Main evaluation loop
# ===========================================================================

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Evaluate Hypotheses using KG-based Ground Truth (v2)")
    parser.add_argument("--benchmark", required=True, help="Benchmark dataset JSON (用于构建 KG)")
    parser.add_argument("--predictions", required=True, help="Predictions JSON (待评估文件)")
    parser.add_argument("--output", default="eval_results.json", help="评估结果输出路径")
    parser.add_argument("--max-items", type=int, default=None, help="仅评估前 N 条")
    parser.add_argument("--taxonomy", default=None, help="学科分类树 JSON 路径")
    args = parser.parse_args()

    # 1. 构建全局知识图谱
    kg = GlobalKG(args.benchmark, taxonomy_path=args.taxonomy)

    # 2. 加载预测结果
    with open(args.predictions, encoding="utf-8") as f:
        predictions = json.load(f)

    if args.max_items:
        predictions = predictions[: args.max_items]

    results = []

    # 3. 逐条评估
    for item in tqdm(predictions, desc="Evaluating"):
        if "parsed" in item:
            parsed = item["parsed"]
            meta = parsed.get("meta", {})
            title = meta.get("title", "")
            primary_disc = meta.get("primary", "unknown")
            item_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
            hyp = parsed.get("假设", {})
            query_data = parsed.get("查询", {})
            pred_paths_dict = {
                "L1": hyp.get("一级", []),
                "L2": hyp.get("二级", []),
                "L3": hyp.get("三级", []),
            }
            l1_query_from_data = query_data.get("一级", "")
            l2_queries_from_data = query_data.get("二级", [])
            l3_queries_from_data = query_data.get("三级", [])
        else:
            item_id = item.get("id", "unknown")
            input_info = item.get("input", {})
            title = input_info.get("title", "")
            primary_disc = input_info.get("primary_discipline", "unknown")
            pred_paths_dict = item.get("ground_truth", {}).get("hypothesis_paths", {})
            l1_query_from_data = ""
            l2_queries_from_data = []
            l3_queries_from_data = []

        l1_query = l1_query_from_data or f"关于 {primary_disc} 的 {title} 的跨学科研究假设"
        gt_set = kg.retrieve_relevant_paths(primary_disc, l1_query, k=3)

        if not gt_set:
            logger.warning("ID %s: 未找到任何相关 GT 路径 (学科: %s)", item_id, primary_disc)
            continue

        # Extract evidence-grounded GT if available (v3 format)
        gt_data = item.get("ground_truth", {})
        gt_terms_list: Optional[List[str]] = None
        gt_relations_list: Optional[List[Dict[str, Any]]] = None
        gt_evidence_paths: Optional[List[Dict[str, Any]]] = None

        if gt_data.get("terms"):
            gt_terms_list = [
                (t.get("normalized") or t.get("term", "")).strip()
                for t in gt_data["terms"]
                if (t.get("normalized") or t.get("term", "")).strip()
            ]
        if gt_data.get("relations"):
            gt_relations_list = gt_data["relations"]
        if gt_data.get("paths"):
            gt_evidence_paths = gt_data["paths"]

        item_scores: Dict[str, list] = defaultdict(list)

        # --- L1 ---
        l1_paths = normalize_paths_structure(pred_paths_dict.get("L1", []))
        for path in l1_paths:
            s = evaluate_single_path(
                path, gt_set, l1_query, primary_disc, "L1", kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
            )
            for k, v in s.items():
                item_scores[f"L1_{k}"].append(v)

        # --- L2 ---
        l2_paths = normalize_paths_structure(pred_paths_dict.get("L2", []))
        for i, path in enumerate(l2_paths):
            gen_query = l2_queries_from_data[i] if i < len(l2_queries_from_data) else l1_query
            s = evaluate_single_path(
                path, gt_set, l1_query, primary_disc, "L2", gen_query=gen_query, kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
            )
            for k, v in s.items():
                item_scores[f"L2_{k}"].append(v)

        # --- L3 ---
        l3_paths = normalize_paths_structure(pred_paths_dict.get("L3", []))
        for i, path in enumerate(l3_paths):
            gen_query = l3_queries_from_data[i] if i < len(l3_queries_from_data) else l1_query
            s = evaluate_single_path(
                path, gt_set, l1_query, primary_disc, "L3", gen_query=gen_query, kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
            )
            for k, v in s.items():
                item_scores[f"L3_{k}"].append(v)

        # --- Structural Diversity (per-level) ---
        for lvl_key, lvl_paths in [("L1", l1_paths), ("L2", l2_paths), ("L3", l3_paths)]:
            sd = structural_diversity(lvl_paths)
            item_scores[f"{lvl_key}_fluency"].append(sd["fluency"])
            item_scores[f"{lvl_key}_flexibility"].append(sd["flexibility"])
            item_scores[f"{lvl_key}_pairwise_diversity"].append(sd["pairwise_diversity"])
            item_scores[f"{lvl_key}_entity_coverage"].append(sd["entity_coverage"])

        # --- Hierarchical Depth Progression ---
        hdp = hierarchical_depth_progression(l1_paths, l2_paths, l3_paths)
        for hdp_key, hdp_val in hdp.items():
            item_scores[f"depth_{hdp_key}"].append(hdp_val)

        # Compute averages
        avg_scores = {k: float(np.mean(v)) if v else 0.0 for k, v in item_scores.items()}
        results.append({"id": item_id, "scores": avg_scores})

    # 4. 汇总输出
    print("\n=== Evaluation Summary (v2) ===")
    final_metrics: Dict[str, list] = defaultdict(list)
    for r in results:
        for k, v in r["scores"].items():
            final_metrics[k].append(v)

    # Group and print
    for metric in sorted(final_metrics.keys()):
        vals = final_metrics[metric]
        mean = np.mean(vals)
        std = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
        print(f"  {metric}: {mean:.4f} ± {std:.4f}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed results saved to {args.output}")


if __name__ == "__main__":
    main()

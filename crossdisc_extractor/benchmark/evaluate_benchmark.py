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
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from crossdisc_extractor.benchmark.eval_prompts import (
    PROMPT_EVAL_DEEP,
    PROMPT_EVAL_L1,
    PROMPT_FEASIBILITY,
    PROMPT_TESTABILITY,
)
from crossdisc_extractor.benchmark.metrics import (
    _build_discipline_paths,
    _load_taxonomy,
    atypical_combination_index,
    build_cooccurrence_from_kg,
    causal_direction_accuracy,
    concept_coverage,
    discipline_balance,
    disciplinary_leap_index,
    embedding_bridging_score,
    enhanced_path_consistency,
    factual_precision,
    hallucination_rate,
    hierarchical_depth_progression,
    information_theoretic_novelty,
    novelty_convention_balance,
    path_semantic_alignment,
    rao_stirling_diversity,
    reasoning_chain_coherence,
    relation_precision,
    remote_association_index,
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
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
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


def _normalize_evidence_reference_paths(
    raw_paths: List[Any],
    *,
    item_id: str,
    abstract: str,
    discipline: str,
) -> List[Dict[str, Any]]:
    """Normalize evidence-grounded GT paths to the evaluator reference shape."""
    normalized: List[Dict[str, Any]] = []
    for idx, raw_path in enumerate(raw_paths or []):
        if not isinstance(raw_path, dict):
            continue
        steps = raw_path.get("path", [])
        if not isinstance(steps, list) or not steps:
            continue
        normalized.append({
            "path": steps,
            "level": raw_path.get("level", "EVIDENCE"),
            "source": raw_path.get("source", "evidence_gt"),
            "source_id": raw_path.get("source_id", item_id),
            "context": abstract,
            "discipline": discipline,
            "disciplines_crossed": raw_path.get("disciplines_crossed", []),
            "support_level": raw_path.get("support_level", "inferred"),
            "total_evidence_confidence": raw_path.get("total_evidence_confidence", 0.0),
        })
    return normalized


def _normalize_legacy_reference_paths(
    legacy_paths: Dict[str, Any],
    *,
    item_id: str,
    abstract: str,
    discipline: str,
) -> List[Dict[str, Any]]:
    """Normalize LLM-generated legacy paths for explicit ablation-only use."""
    normalized: List[Dict[str, Any]] = []
    for level in ["L1", "L2", "L3"]:
        raw_paths = (legacy_paths or {}).get(level, [])
        for path in normalize_paths_structure(raw_paths):
            normalized.append({
                "path": path,
                "level": level,
                "source": "legacy_llm",
                "source_id": item_id,
                "context": abstract,
                "discipline": discipline,
                "support_level": "llm_generated",
                "uses_llm_generated_gt": True,
            })
    return normalized


def _legacy_paths_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Read legacy LLM paths from explicit non-GT locations, with old-schema fallback."""
    model_outputs = item.get("model_outputs", {})
    supplementary = item.get("supplementary", {})
    gt = item.get("ground_truth", {})
    return (
        model_outputs.get("legacy_llm_hypothesis_paths")
        or supplementary.get("legacy_paths_for_ablation")
        or gt.get("hypothesis_paths_legacy")
        or gt.get("hypothesis_paths")
        or {}
    )


def _reference_paths_from_item(
    item: Dict[str, Any],
    *,
    reference_source: str,
    allow_legacy_llm_gt: bool,
) -> Tuple[List[Dict[str, Any]], str, str, str]:
    """Return normalized reference paths plus primary/id/abstract metadata."""
    if "parsed" in item:
        parsed = item["parsed"]
        meta = parsed.get("meta", {})
        primary = meta.get("primary", "unknown")
        item_id = str(hash(meta.get("title", "")))
        abstract = item.get("abstract", "")
        if reference_source == "legacy_llm":
            if not allow_legacy_llm_gt:
                raise ValueError("legacy_llm reference requires allow_legacy_llm_gt=True")
            hyp = parsed.get("假设", {})
            paths = _normalize_legacy_reference_paths(
                {"L1": hyp.get("一级", []), "L2": hyp.get("二级", []), "L3": hyp.get("三级", [])},
                item_id=item_id,
                abstract=abstract,
                discipline=primary,
            )
        else:
            paths = []
        return paths, primary, item_id, abstract

    primary = item.get("input", {}).get("primary_discipline", "unknown")
    item_id = item.get("id", "unknown")
    abstract = item.get("input", {}).get("abstract", "")
    gt = item.get("ground_truth", {})

    if reference_source == "evidence":
        paths = _normalize_evidence_reference_paths(
            gt.get("paths", []),
            item_id=item_id,
            abstract=abstract,
            discipline=primary,
        )
    elif reference_source == "legacy_llm":
        if not allow_legacy_llm_gt:
            raise ValueError("legacy_llm reference requires allow_legacy_llm_gt=True")
        paths = _normalize_legacy_reference_paths(
            _legacy_paths_from_item(item),
            item_id=item_id,
            abstract=abstract,
            discipline=primary,
        )
    else:
        raise ValueError(f"Unsupported reference source: {reference_source}")

    return paths, primary, item_id, abstract


def _prediction_paths_from_item(
    item: Dict[str, Any],
    prediction_source: str,
    allow_legacy_llm_gt: bool,
) -> Dict[str, Any]:
    """Read model outputs for evaluation without treating ground_truth as predictions."""
    if "parsed" in item:
        parsed = item["parsed"]
        hyp = parsed.get("假设", {})
        return {
            "L1": hyp.get("一级", []),
            "L2": hyp.get("二级", []),
            "L3": hyp.get("三级", []),
        }

    if prediction_source in {"model_outputs", "legacy_llm"}:
        legacy_paths = _legacy_paths_from_item(item)
        if legacy_paths:
            return legacy_paths
        if prediction_source == "legacy_llm" and not allow_legacy_llm_gt:
            raise ValueError("legacy_llm prediction fallback requires --allow-legacy-llm-gt")

    if prediction_source == "ground_truth_legacy":
        if not allow_legacy_llm_gt:
            raise ValueError("ground_truth_legacy prediction source requires --allow-legacy-llm-gt")
        return item.get("ground_truth", {}).get("hypothesis_paths", {})

    return {}


# ===========================================================================
#  Global Knowledge Graph
# ===========================================================================

class GlobalKG:
    """基于 Benchmark 数据集构建的全局知识图谱（按学科索引路径）。"""

    def __init__(
        self,
        benchmark_path: str,
        taxonomy_path: Optional[str] = None,
        reference_source: str = "evidence",
        allow_legacy_llm_gt: bool = False,
    ):
        if reference_source == "legacy_llm" and not allow_legacy_llm_gt:
            raise ValueError("legacy_llm reference source is ablation-only; pass allow_legacy_llm_gt=True")
        self.paths_by_discipline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.path_vectors: Dict[str, Counter] = {}
        self.all_triples: Counter = Counter()
        self.total_triples: int = 0
        self.all_flat_paths: List[List[Dict[str, Any]]] = []
        self.node_disciplines: Dict[str, str] = {}
        self.reference_source = reference_source
        self.allow_legacy_llm_gt = allow_legacy_llm_gt

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
        logger.info(
            "Reference source: %s (allow_legacy_llm_gt=%s)",
            self.reference_source,
            self.allow_legacy_llm_gt,
        )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for item in data:
            paths, primary, item_id, abstract = _reference_paths_from_item(
                item,
                reference_source=self.reference_source,
                allow_legacy_llm_gt=self.allow_legacy_llm_gt,
            )

            if "parsed" in item:
                parsed = item["parsed"]
                meta = parsed.get("meta", {})
                primary = meta.get("primary", primary)
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
                gt = item.get("ground_truth", {})
                for term in gt.get("terms", []) or []:
                    ent = (term.get("normalized") or term.get("term", "")).strip()
                    disc = (term.get("discipline") or "").strip()
                    if ent and disc:
                        self.node_disciplines.setdefault(ent, disc)
                        self.node_disciplines.setdefault(ent.lower(), disc)

            for path_obj in paths:
                p = path_obj.get("path", [])
                if not p:
                    continue
                path_obj.setdefault("source_id", item_id)
                path_obj.setdefault("context", abstract)
                path_obj.setdefault("discipline", primary)
                path_obj.setdefault("source", self.reference_source)
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
                    r = (step.get("relation") or step.get("relation_type") or "").strip().lower()
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
        out.append(f"参考路径 #{i} (Level {item.get('level', 'GT')}):\n{p_str}")
    return "\n\n".join(out)


def _terms_from_gt_data(gt_data: Dict[str, Any]) -> List[str]:
    return [
        (t.get("normalized") or t.get("term", "")).strip()
        for t in gt_data.get("terms", [])
        if (t.get("normalized") or t.get("term", "")).strip()
    ]


def _terms_from_reference_paths(ref_paths: List[Dict[str, Any]]) -> List[str]:
    terms: set = set()
    for ref_path in ref_paths:
        for step in ref_path.get("path", []):
            h = (step.get("head") or "").strip()
            t = (step.get("tail") or "").strip()
            if h:
                terms.add(h)
            if t:
                terms.add(t)
    return sorted(terms)


def _relations_from_reference_paths(ref_paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    for ref_path in ref_paths:
        source = ref_path.get("source", "reference_path")
        source_paper = ref_path.get("source_paper") or ref_path.get("source_id", "")
        for step in ref_path.get("path", []):
            h = (step.get("head") or "").strip()
            t = (step.get("tail") or "").strip()
            if not h or not t:
                continue
            rel = (step.get("relation_type") or step.get("relation") or "").strip()
            relations.append({
                "head": h,
                "tail": t,
                "relation_type": rel,
                "evidence_sentence": step.get("evidence") or step.get("claim", ""),
                "support_level": step.get("support_level", "unknown"),
                "source": source,
                "source_paper": source_paper,
            })
    return relations


def build_reference_evidence(
    gt_data: Dict[str, Any],
    benchmark_gt_paths: List[Dict[str, Any]],
    web_ref_paths: List[Dict[str, Any]],
    use_benchmark_gt: bool,
    use_web_search: bool,
) -> Dict[str, Any]:
    """Build the reference material used by all GT/web-aware submetrics."""
    reference_paths: List[Dict[str, Any]] = []
    terms: List[str] = []
    relations: List[Dict[str, Any]] = []
    evidence_paths: List[Dict[str, Any]] = []

    if use_benchmark_gt:
        reference_paths.extend(benchmark_gt_paths)
        terms.extend(_terms_from_gt_data(gt_data))
        terms.extend(_terms_from_reference_paths(benchmark_gt_paths))
        relations.extend(gt_data.get("relations", []) or [])
        relations.extend(_relations_from_reference_paths(benchmark_gt_paths))
        evidence_paths.extend(gt_data.get("paths", []) or [])
        evidence_paths.extend(benchmark_gt_paths)

    if use_web_search:
        reference_paths.extend(web_ref_paths)
        terms.extend(_terms_from_reference_paths(web_ref_paths))
        relations.extend(_relations_from_reference_paths(web_ref_paths))
        evidence_paths.extend(web_ref_paths)

    terms = sorted({t for t in terms if t})

    return {
        "reference_paths": reference_paths,
        "gt_terms": terms or None,
        "gt_relations": relations or None,
        "gt_evidence_paths": evidence_paths or None,
        "source_counts": {
            "benchmark_gt_paths": len(benchmark_gt_paths) if use_benchmark_gt else 0,
            "web_ref_paths": len(web_ref_paths) if use_web_search else 0,
            "reference_paths": len(reference_paths),
            "terms": len(terms),
            "relations": len(relations),
            "evidence_paths": len(evidence_paths),
        },
    }


def _runtime_kg_context(
    kg: Optional[GlobalKG],
    reference_paths: List[Dict[str, Any]],
    use_kg_background: bool = True,
) -> Optional[Dict[str, Any]]:
    if kg is None:
        return None

    node_disciplines = dict(kg.node_disciplines) if use_kg_background else {}
    web_flat_paths: List[List[Dict[str, Any]]] = []
    all_triples = kg.all_triples.copy() if use_kg_background else Counter()
    total_triples = kg.total_triples if use_kg_background else 0

    for ref_path in reference_paths:
        steps = ref_path.get("path", [])
        discipline = ref_path.get("discipline")
        if discipline:
            for step in steps:
                for field in ("head", "tail"):
                    ent = (step.get(field) or "").strip()
                    if ent:
                        node_disciplines.setdefault(ent, discipline)
                        node_disciplines.setdefault(ent.lower(), discipline)

        # Benchmark paths are already indexed in GlobalKG.  Web paths are
        # per-evaluation evidence, so we add them only to this runtime view.
        if ref_path.get("source") == "web_search" and steps:
            web_flat_paths.append(steps)
            for step in steps:
                h = (step.get("head") or "").strip().lower()
                r = (step.get("relation") or step.get("relation_type") or "").strip().lower()
                t = (step.get("tail") or "").strip().lower()
                if h and t:
                    all_triples[(h, r, t)] += 1
                    total_triples += 1

    if web_flat_paths or not use_kg_background:
        cooccurrence, cooc_mu, cooc_sigma = build_cooccurrence_from_kg(
            (kg.all_flat_paths if use_kg_background else []) + web_flat_paths
        )
    else:
        cooccurrence = kg.cooccurrence
        cooc_mu = kg.cooc_mu
        cooc_sigma = kg.cooc_sigma

    return {
        "node_disciplines": node_disciplines,
        "all_triples": all_triples,
        "total_triples": total_triples,
        "cooccurrence": cooccurrence,
        "cooc_mu": cooc_mu,
        "cooc_sigma": cooc_sigma,
        "disc_paths": kg.disc_paths,
        "max_depth": kg.max_depth,
    }


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

def _fmt_path_short(path: List[Dict[str, Any]]) -> str:
    """Return a compact one-line preview of a hypothesis path."""
    return " -> ".join(
        f"{s.get('head', '?')}--[{s.get('relation', '?')}]-->{s.get('tail', '?')}"
        for s in path
    )


def _fast_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").strip().lower(), (b or "").strip().lower()).ratio()


def _fast_entities(path: List[Dict[str, Any]]) -> List[str]:
    entities: List[str] = []
    for step in path:
        for key in ("head", "tail"):
            value = (step.get(key) or "").strip()
            if value:
                entities.append(value)
    return sorted(set(entities))


def _fast_claim_supported(step: Dict[str, Any], abstract: str, gt_terms: Optional[List[str]]) -> bool:
    claim = (step.get("claim") or "").strip()
    entities = _fast_entities([step])
    abstract_lower = (abstract or "").lower()
    if abstract_lower and any(entity.lower() in abstract_lower for entity in entities):
        return True
    if gt_terms:
        for entity in entities:
            if any(_fast_similarity(entity, term) >= 0.75 for term in gt_terms):
                return True
    return bool(claim)


def _fast_factual_precision(
    path: List[Dict[str, Any]],
    abstract: str,
    gt_terms: Optional[List[str]],
    gt_relations: Optional[List[Dict[str, Any]]] = None,
    gt_evidence_paths: Optional[List[Dict[str, Any]]] = None,
) -> float:
    if not path:
        return 0.0
    gt_relations = gt_relations or []
    gt_evidence_paths = gt_evidence_paths or []

    def _fast_step_supported_by_gt_relation(step: Dict[str, Any]) -> bool:
        gen_h = (step.get("head") or "").strip().lower()
        gen_t = (step.get("tail") or "").strip().lower()
        if not gen_h or not gen_t:
            return False
        for rel in gt_relations:
            rel_h = (rel.get("head") or "").strip().lower()
            rel_t = (rel.get("tail") or "").strip().lower()
            if not rel_h or not rel_t:
                continue
            direct = (_fast_similarity(gen_h, rel_h) + _fast_similarity(gen_t, rel_t)) / 2
            reverse = (_fast_similarity(gen_h, rel_t) + _fast_similarity(gen_t, rel_h)) / 2
            if max(direct, reverse) >= 0.75:
                return True
        return False

    def _fast_gt_evidence_supported(step: Dict[str, Any]) -> Optional[float]:
        entities = _fast_entities([step])
        if not entities:
            return 1.0
        evidence_texts: List[str] = []
        for ref_path in gt_evidence_paths:
            if not isinstance(ref_path, dict):
                continue
            matched = False
            for ref_step in ref_path.get("path", []) or []:
                if not isinstance(ref_step, dict):
                    continue
                ref_entities = [str(ref_step.get("head") or "").strip(), str(ref_step.get("tail") or "").strip()]
                if any(any(_fast_similarity(entity, ref_ent) >= 0.75 for ref_ent in ref_entities if ref_ent) for entity in entities):
                    matched = True
                    evidence = (ref_step.get("evidence") or ref_step.get("claim") or "").strip()
                    if evidence:
                        evidence_texts.append(evidence)
            if matched:
                context = (ref_path.get("context") or "").strip()
                if context:
                    evidence_texts.append(context)
        if not evidence_texts:
            return None
        lowered = [text.lower() for text in evidence_texts if text]
        return 1.0 if any(any(entity.lower() in text for entity in entities) for text in lowered) else 0.0

    step_scores: List[float] = []
    for step in path:
        claim = (step.get("claim") or "").strip()
        if not claim:
            step_scores.append(1.0)
            continue
        source_score = 1.0 if _fast_claim_supported(step, abstract, gt_terms) else 0.0
        evidence_score = _fast_gt_evidence_supported(step)
        relation_score = 1.0 if (
            _fast_step_supported_by_gt_relation(step)
            or any(
                gt_terms and any(_fast_similarity(entity, term) >= 0.75 for term in gt_terms)
                for entity in _fast_entities([step])
            )
        ) else (0.0 if (gt_relations or gt_terms) else None)
        channel_values = [(0.5, source_score), (0.3, evidence_score), (0.2, relation_score)]
        available = [(w, v) for w, v in channel_values if v is not None]
        if not available:
            step_scores.append(0.0)
            continue
        total_weight = sum(w for w, _ in available)
        step_scores.append(sum(w * float(v) for w, v in available) / total_weight)
    return round(sum(step_scores) / len(path), 4)


def _fast_hallucination_rate(
    path: List[Dict[str, Any]],
    abstract: str,
    gt_terms: Optional[List[str]],
) -> float:
    entities = _fast_entities(path)
    if not entities:
        return 0.0
    abstract_lower = (abstract or "").lower()
    ungrounded = 0
    for entity in entities:
        entity_lower = entity.lower()
        in_abstract = bool(abstract_lower and entity_lower in abstract_lower)
        in_gt = bool(gt_terms and any(_fast_similarity(entity, term) >= 0.75 for term in gt_terms))
        if not in_abstract and not in_gt:
            ungrounded += 1
    return round(ungrounded / len(entities), 4)


def _fast_concept_coverage(path: List[Dict[str, Any]], gt_terms: Optional[List[str]]) -> Dict[str, float]:
    entities = _fast_entities(path)
    terms = [term for term in (gt_terms or []) if term]
    if not entities or not terms:
        return {"concept_recall": 0.0, "concept_precision": 0.0, "concept_f1": 0.0}

    entity_hits = sum(1 for entity in entities if any(_fast_similarity(entity, term) >= 0.75 for term in terms))
    term_hits = sum(1 for term in terms if any(_fast_similarity(entity, term) >= 0.75 for entity in entities))
    precision = entity_hits / len(entities)
    recall = term_hits / len(terms)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "concept_recall": round(recall, 4),
        "concept_precision": round(precision, 4),
        "concept_f1": round(f1, 4),
    }


def _fast_path_text(path: List[Dict[str, Any]]) -> str:
    return " -> ".join(
        f"{step.get('head', '')} {step.get('relation', step.get('relation_type', ''))} {step.get('tail', '')}"
        for step in path
    )


def _fast_path_alignment(path: List[Dict[str, Any]], gt_paths: Optional[List[Dict[str, Any]]]) -> Dict[str, float]:
    if not path or not gt_paths:
        return {"best_alignment": 0.0, "mean_alignment": 0.0}
    gen_text = _fast_path_text(path)
    sims: List[float] = []
    for gt in gt_paths:
        steps = gt.get("path", gt) if isinstance(gt, dict) else gt
        gt_text = _fast_path_text(steps) if isinstance(steps, list) else str(steps)
        sims.append(_fast_similarity(gen_text, gt_text))
    return {
        "best_alignment": round(max(sims), 4) if sims else 0.0,
        "mean_alignment": round(float(np.mean(sims)), 4) if sims else 0.0,
    }


def _fast_chain_coherence(path: List[Dict[str, Any]]) -> float:
    if not path:
        return 0.0
    if len(path) == 1:
        return 1.0
    sims = []
    for prev, cur in zip(path, path[1:]):
        sims.append(_fast_similarity(str(prev.get("tail", "")), str(cur.get("head", ""))))
    return round(float(np.mean(sims)), 4) if sims else 1.0


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
    abstract: str = "",
    use_kg_background: bool = True,
    fast_mode: bool = False,
    x5_only: bool = False,
    include_legacy_llm_judge: bool = True,
    _item_id: str = "",
    _path_idx: int = 0,
) -> Dict[str, float]:
    """Evaluate a single hypothesis path with graph + LLM + GT-aware metrics."""

    tag = f"ID {_item_id} {level}[{_path_idx}]" if _item_id else f"{level}[{_path_idx}]"

    # ── Log inputs ─────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info("[Eval] %s 开始评估", tag)
    logger.info("[Eval] %s 生成路径: %s", tag, _fmt_path_short(path)[:200])
    logger.info("[Eval] %s 参考路径数: %d (GT: %d, web: %d)",
                tag, len(gt_paths),
                sum(1 for g in gt_paths if g.get("source") != "web_search"),
                sum(1 for g in gt_paths if g.get("source") == "web_search"))
    logger.info("[Eval] %s query='%s'  discipline='%s'  abstract_len=%d",
                tag, query[:60], discipline, len(abstract))
    if fast_mode:
        logger.info("[Eval] %s fast_mode=ON: skipping NLI/SBERT-heavy objective metrics", tag)
    if x5_only:
        logger.info("[Eval] %s x5_only=ON: skipping non-X+5 metrics", tag)
    if gt_terms:
        logger.info("[Eval] %s gt_terms(%d): %s", tag, len(gt_terms), ", ".join(gt_terms[:8]))

    scores: Dict[str, float] = {}

    # ── Graph metrics (objective) ──────────────────────────────────────
    logger.info("[Eval] %s ── 计算客观图指标 ──", tag)

    # Legacy consistency (backward compat)
    # Enhanced consistency (P/R/F1)
    enhanced = GraphMetricEvaluator.calculate_enhanced_consistency(path, gt_paths)
    scores["consistency_recall"] = enhanced["consistency_recall"]
    scores["consistency_f1"] = enhanced["consistency_f1"]
    if not x5_only:
        scores["consistency"] = GraphMetricEvaluator.calculate_path_consistency(path, gt_paths)
        scores["consistency_precision"] = enhanced["consistency_precision"]
    logger.info("[Eval] %s consistency_f1=%.4f (P=%.4f R=%.4f) — 生成路径与参考路径的实体/关系重叠度",
                tag, scores["consistency_f1"], enhanced["consistency_precision"], scores["consistency_recall"])

    # Bridging — legacy + embedding-based
    if not x5_only:
        scores["bridging"] = GraphMetricEvaluator.calculate_bridging_score(path)
    if fast_mode:
        scores["embedding_bridging"] = scores["bridging"] if not x5_only else GraphMetricEvaluator.calculate_bridging_score(path)
    else:
        scores["embedding_bridging"] = GraphMetricEvaluator.calculate_embedding_bridging(path)
    logger.info("[Eval] %s embedding_bridging=%.4f — 路径中相邻步骤的语义跨越程度",
                tag, scores["embedding_bridging"])

    # Chain coherence
    scores["chain_coherence"] = _fast_chain_coherence(path) if fast_mode else GraphMetricEvaluator.calculate_chain_coherence(path)
    logger.info("[Eval] %s chain_coherence=%.4f — 相邻步骤间的语义连贯性",
                tag, scores["chain_coherence"])

    # Information-theoretic novelty
    kg_ctx = _runtime_kg_context(kg, gt_paths, use_kg_background=use_kg_background)
    if kg_ctx is not None:
        scores["info_novelty"] = GraphMetricEvaluator.calculate_info_novelty(
            path, kg_ctx["all_triples"], kg_ctx["total_triples"]
        )
        scores["atypical_combination"] = atypical_combination_index(
            path, kg_ctx["cooccurrence"], kg_ctx["cooc_mu"], kg_ctx["cooc_sigma"]
        )
        scores["rao_stirling"] = rao_stirling_diversity(
            path, kg_ctx["node_disciplines"], kg_ctx["disc_paths"], kg_ctx["max_depth"]
        )
        scores["disciplinary_leap_index"] = disciplinary_leap_index(
            path, kg_ctx["node_disciplines"], kg_ctx["disc_paths"], kg_ctx["max_depth"]
        )
        if not x5_only:
            scores["discipline_balance"] = discipline_balance(
                path, kg_ctx["node_disciplines"]
            )
        logger.info("[Eval] %s rao_stirling=%.4f — Rao-Stirling 学科多样性指数",
                    tag, scores["rao_stirling"])
        logger.info("[Eval] %s atypical_combination=%.4f — 非典型概念组合度 (z-score)",
                    tag, scores["atypical_combination"])
        logger.info("[Eval] %s disciplinary_leap_index=%.4f — 最大学科跨越距离",
                    tag, scores["disciplinary_leap_index"])
        if not x5_only:
            logger.info("[Eval] %s discipline_balance=%.4f — 学科分布均衡度 (1-Gini)",
                        tag, scores["discipline_balance"])
        logger.info("[Eval] %s info_novelty=%.4f — 信息论新颖度 (surprisal)",
                    tag, scores["info_novelty"])
    else:
        scores["info_novelty"] = 0.0
        scores["atypical_combination"] = 0.0
        scores["rao_stirling"] = 0.0
        scores["disciplinary_leap_index"] = 0.0
        if not x5_only:
            scores["discipline_balance"] = 0.0
        logger.info("[Eval] %s KG 不可用，跳过 KG 相关指标", tag)

    # ── New objective metrics (no KG dependency) ──────────────────────
    logger.info("[Eval] %s ── 计算比较型指标 (vs GT) ──", tag)

    scores["remote_association_index"] = scores["embedding_bridging"] if fast_mode else remote_association_index(path)
    logger.info("[Eval] %s remote_association_index=%.4f — 路径步骤间平均语义距离",
                tag, scores["remote_association_index"])

    scores["causal_direction_accuracy"] = causal_direction_accuracy(path, gt_paths)
    logger.info("[Eval] %s causal_direction_accuracy=%.4f — 因果方向与参考路径的吻合度",
                tag, scores["causal_direction_accuracy"])

    scores["novelty_convention_balance"] = novelty_convention_balance(path, gt_paths)
    logger.info("[Eval] %s novelty_convention_balance=%.4f — 新颖性与传统性的平衡度",
                tag, scores["novelty_convention_balance"])

    # Factual Precision (NLI-based, needs abstract)
    if fast_mode:
        scores["factual_precision"] = _fast_factual_precision(
            path,
            abstract,
            gt_terms,
            gt_relations=gt_relations,
            gt_evidence_paths=gt_evidence_paths,
        )
        logger.info("[Eval] %s factual_precision=%.4f — fast multi-source proxy (source abstract + GT evidence + GT support)", tag, scores["factual_precision"])
    else:
        scores["factual_precision"] = factual_precision(
            path,
            abstract=abstract,
            gt_terms=gt_terms or [],
            gt_relations=gt_relations or [],
            gt_evidence_paths=gt_evidence_paths or [],
        )
        logger.info("[Eval] %s factual_precision=%.4f — multi-source NLI (source abstract + GT evidence + GT support)",
                    tag, scores["factual_precision"])

    # Hallucination Rate (needs gt_terms + abstract)
    if fast_mode:
        scores["hallucination_rate"] = _fast_hallucination_rate(path, abstract, gt_terms)
    elif gt_terms or abstract:
        scores["hallucination_rate"] = hallucination_rate(
            path, gt_terms or [], abstract
        )
    else:
        scores["hallucination_rate"] = 0.0
    logger.info("[Eval] %s hallucination_rate=%.4f — 路径中未被参考支持的实体比例",
                tag, scores["hallucination_rate"])

    # ── Evidence-grounded GT metrics (v3) ──────────────────────────────
    logger.info("[Eval] %s ── 计算 GT 证据指标 ──", tag)

    if gt_terms:
        cc = _fast_concept_coverage(path, gt_terms) if fast_mode else concept_coverage(path, gt_terms)
        scores["concept_f1"] = cc["concept_f1"]
        if not x5_only:
            scores["concept_recall"] = cc["concept_recall"]
            scores["concept_precision"] = cc["concept_precision"]
        logger.info("[Eval] %s concept_f1=%.4f (P=%.4f R=%.4f) — 概念覆盖度",
                    tag, scores["concept_f1"], cc["concept_precision"], cc["concept_recall"])
    else:
        scores["concept_f1"] = 0.0
        if not x5_only:
            scores["concept_recall"] = 0.0
            scores["concept_precision"] = 0.0
        logger.info("[Eval] %s concept_f1=N/A (无 gt_terms)", tag)

    if gt_relations:
        rp = relation_precision(path, gt_relations)
        scores["relation_precision"] = rp["relation_precision"]
        scores["evidence_coverage"] = rp["evidence_coverage"]
        if not x5_only:
            scores["relation_type_accuracy"] = rp["relation_type_accuracy"]
        logger.info("[Eval] %s evidence_coverage=%.4f — GT 证据路径覆盖度",
                    tag, scores["evidence_coverage"])
    else:
        scores["relation_precision"] = 0.0
        scores["evidence_coverage"] = 0.0
        if not x5_only:
            scores["relation_type_accuracy"] = 0.0

    if gt_evidence_paths:
        pa = _fast_path_alignment(path, gt_evidence_paths) if fast_mode else path_semantic_alignment(path, gt_evidence_paths)
        scores["path_alignment_best"] = pa["best_alignment"]
        if not x5_only:
            scores["path_alignment_mean"] = pa["mean_alignment"]
        logger.info("[Eval] %s path_alignment_best=%.4f — 与最相似 GT 路径的语义对齐度",
                    tag, scores["path_alignment_best"])
    else:
        scores["path_alignment_best"] = 0.0
        if not x5_only:
            scores["path_alignment_mean"] = 0.0

    # ── LLM evaluation (subjective) ───────────────────────────────────
    logger.info("[Eval] %s ── LLM 主观评估 ──", tag)

    path_str = format_path_for_prompt(path)
    gt_str = format_gt_set(gt_paths) if gt_paths else "无参考证据"

    if include_legacy_llm_judge:
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

        logger.info("[Eval] %s LLM prompt 长度: %d 字符 (含 %d 条参考路径)",
                    tag, len(sys_prompt), len(gt_paths))

        messages = [{"role": "user", "content": sys_prompt}]
        try:
            resp = chat_completion_with_retry(messages, temperature=0.0)
            llm_scores = parse_llm_score(resp)
            if "feasibility" in llm_scores:
                llm_scores["legacy_feasibility"] = llm_scores["feasibility"]
            logger.info("[Eval] %s LLM 原始响应: %s", tag, resp[:300])
            logger.info("[Eval] %s LLM 评分: innovation=%.2f feasibility=%.2f scientificity=%.2f",
                        tag, llm_scores.get("innovation", 0), llm_scores.get("feasibility", 0),
                        llm_scores.get("scientificity", 0))
        except Exception as e:
            logger.error("[Eval] %s LLM 评估请求失败: %s", tag, e)
            llm_scores = {
                "innovation": 0.0,
                "feasibility": 0.0,
                "legacy_feasibility": 0.0,
                "scientificity": 0.0,
            }

        scores.update(llm_scores)
    else:
        logger.info("[Eval] %s 跳过 legacy LLM judge（innovation/scientificity）", tag)

    # ── Feasibility (LLM, dedicated rubric) ────────────────────────────
    try:
        feasibility_prompt = PROMPT_FEASIBILITY.format(
            hypothesis_path=path_str,
            reference_evidence=gt_str,
        )
        feasibility_msgs = [{"role": "user", "content": feasibility_prompt}]
        feasibility_resp = chat_completion_with_retry(feasibility_msgs, temperature=0.0)
        feasibility_scores = parse_llm_score(
            feasibility_resp,
            fields=[
                "data_feasibility",
                "method_feasibility",
                "resource_feasibility",
                "validation_readiness",
            ],
        )
        scores["feasibility_data"] = feasibility_scores.get("data_feasibility", 0.0)
        scores["feasibility_method"] = feasibility_scores.get("method_feasibility", 0.0)
        scores["feasibility_resource"] = feasibility_scores.get("resource_feasibility", 0.0)
        scores["feasibility_validation"] = feasibility_scores.get("validation_readiness", 0.0)
        scores["feasibility"] = float(np.mean(list(feasibility_scores.values())))
        logger.info(
            "[Eval] %s LLM 现实可行性: feasibility=%.4f (data=%.2f method=%.2f resource=%.2f validation=%.2f)",
            tag,
            scores["feasibility"],
            scores["feasibility_data"],
            scores["feasibility_method"],
            scores["feasibility_resource"],
            scores["feasibility_validation"],
        )
    except Exception as e:
        logger.warning("[Eval] %s Feasibility 评估失败: %s", tag, e)
        scores["feasibility_data"] = 0.0
        scores["feasibility_method"] = 0.0
        scores["feasibility_resource"] = 0.0
        scores["feasibility_validation"] = 0.0
        scores["feasibility"] = 0.0

    # ── Testability (LLM) ─────────────────────────────────────────────

    try:
        test_prompt = PROMPT_TESTABILITY.format(
            hypothesis_path=path_str,
            reference_evidence=gt_str,
        )
        test_msgs = [{"role": "user", "content": test_prompt}]
        test_resp = chat_completion_with_retry(test_msgs, temperature=0.0)
        test_scores = parse_llm_score(
            test_resp,
            fields=["specificity", "measurability", "falsifiability", "resource_feasibility"],
        )
        scores["testability"] = float(np.mean(list(test_scores.values())))
        logger.info("[Eval] %s LLM 可验证性: testability=%.4f (specificity=%.2f measurability=%.2f "
                    "falsifiability=%.2f resource_feasibility=%.2f)",
                    tag, scores["testability"],
                    test_scores.get("specificity", 0), test_scores.get("measurability", 0),
                    test_scores.get("falsifiability", 0), test_scores.get("resource_feasibility", 0))
    except Exception as e:
        logger.warning("[Eval] %s Testability 评估失败: %s", tag, e)
        scores["testability"] = 0.0

    # ── Summary ────────────────────────────────────────────────────────
    logger.info("[Eval] %s ── 评分汇总 ──", tag)
    for k in sorted(scores.keys()):
        logger.info("[Eval] %s   %-30s = %.4f", tag, k, scores[k])
    logger.info("─" * 60)

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
    parser.add_argument("--use-benchmark-gt", dest="use_benchmark_gt", action="store_true", default=True,
                        help="评估时使用 Benchmark GT 参考证据和 KG 背景统计 (默认开启)")
    parser.add_argument("--no-benchmark-gt", dest="use_benchmark_gt", action="store_false",
                        help="评估时不使用 Benchmark GT 参考证据和 KG 背景统计；可与 --web-search 独立组合")
    parser.add_argument("--web-search", action="store_true", help="启用 Web Search 增强参考证据")
    parser.add_argument("--no-web-search", dest="web_search", action="store_false",
                        help="禁用 Web Search 参考证据 (默认)")
    parser.add_argument("--web-search-limit", type=int, default=10, help="搜索相似论文数量")
    parser.add_argument("--web-cache-dir", default=None, help="Web Search 缓存目录")
    parser.add_argument("--web-provider", choices=["openalex", "semantic_scholar", "auto"], default="openalex",
                        help="Web Search provider (默认 openalex)")
    parser.add_argument(
        "--reference-source",
        choices=["evidence", "legacy_llm"],
        default="evidence",
        help="Benchmark reference source. Default: evidence ground_truth['paths']; legacy_llm is ablation-only.",
    )
    parser.add_argument(
        "--allow-legacy-llm-gt",
        action="store_true",
        help="Explicitly allow legacy LLM-generated paths as reference/prediction source for ablation only.",
    )
    parser.add_argument(
        "--prediction-source",
        choices=["model_outputs", "legacy_llm", "ground_truth_legacy"],
        default="model_outputs",
        help="Where to read paths from benchmark-format prediction items. Parsed extraction files are unchanged.",
    )
    args = parser.parse_args()

    if args.reference_source == "legacy_llm" and not args.allow_legacy_llm_gt:
        raise SystemExit("--reference-source legacy_llm is ablation-only; pass --allow-legacy-llm-gt")
    if args.prediction_source in {"legacy_llm", "ground_truth_legacy"} and not args.allow_legacy_llm_gt:
        raise SystemExit(f"--prediction-source {args.prediction_source} requires --allow-legacy-llm-gt")

    # 1. 构建全局知识图谱
    kg = GlobalKG(
        args.benchmark,
        taxonomy_path=args.taxonomy,
        reference_source=args.reference_source,
        allow_legacy_llm_gt=args.allow_legacy_llm_gt,
    )

    # 2. 加载预测结果
    with open(args.predictions, encoding="utf-8") as f:
        predictions = json.load(f)

    if args.max_items:
        predictions = predictions[: args.max_items]

    results = []
    eval_trace: List[Dict[str, Any]] = []  # full trace for JSON output

    # 3. 逐条评估
    for item_idx, item in enumerate(tqdm(predictions, desc="Evaluating")):
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
            abstract = item.get("abstract", "")
        else:
            item_id = item.get("id", "unknown")
            input_info = item.get("input", {})
            title = input_info.get("title", "")
            primary_disc = input_info.get("primary_discipline", "unknown")
            pred_paths_dict = _prediction_paths_from_item(
                item,
                prediction_source=args.prediction_source,
                allow_legacy_llm_gt=args.allow_legacy_llm_gt,
            )
            l1_query_from_data = ""
            l2_queries_from_data = []
            l3_queries_from_data = []
            abstract = input_info.get("abstract", "")

        # ── Per-item header ──────────────────────────────────────────
        logger.info("=" * 70)
        logger.info("[Item %d/%d] ID=%s", item_idx + 1, len(predictions), item_id)
        logger.info("[Item] title    = '%s'", title[:100])
        logger.info("[Item] discipline= '%s'", primary_disc)
        logger.info("[Item] abstract  = '%s'", (abstract or "")[:150])
        logger.info("[Item] 生成假设路径数: L1=%d  L2=%d  L3=%d",
                    len(pred_paths_dict.get("L1", [])),
                    len(pred_paths_dict.get("L2", [])),
                    len(pred_paths_dict.get("L3", [])))

        # Per-item trace record
        item_trace: Dict[str, Any] = {
            "item_idx": item_idx,
            "item_id": item_id,
            "title": title,
            "discipline": primary_disc,
            "abstract_len": len(abstract or ""),
            "reference_source": args.reference_source,
            "prediction_source": "parsed" if "parsed" in item else args.prediction_source,
            "uses_llm_generated_gt": bool(args.reference_source == "legacy_llm"),
            "pred_path_counts": {
                "L1": len(pred_paths_dict.get("L1", [])),
                "L2": len(pred_paths_dict.get("L2", [])),
                "L3": len(pred_paths_dict.get("L3", [])),
            },
        }

        l1_query = l1_query_from_data or f"关于 {primary_disc} 的 {title} 的跨学科研究假设"
        logger.info("[Item] 检索 query = '%s'", l1_query[:80])

        gt_set: List[Dict[str, Any]] = []
        if args.use_benchmark_gt:
            gt_set = kg.retrieve_relevant_paths(primary_disc, l1_query, k=3)
            logger.info("[Item] Benchmark GT 开启: KG 检索到 %d 条 GT 参考路径", len(gt_set))
            if not gt_set:
                logger.warning("ID %s: 未找到任何 Benchmark GT 参考路径 (学科: %s)", item_id, primary_disc)
        else:
            logger.info("[Item] Benchmark GT 已关闭: 不使用 KG 检索参考路径 / GT evidence")

        # ── Web Search reference paths ────────────────────────────────
        web_ref_paths: List[Dict[str, Any]] = []
        if args.web_search:
            logger.info("ID %s: [WebSearch-Integration] Web Search 开启", item_id)
            try:
                from crossdisc_extractor.benchmark.web_search import search_and_extract_reference_paths
                web_cache = args.web_cache_dir or os.path.join(
                    os.path.dirname(args.output), "web_search_cache"
                )
                web_ref_paths = search_and_extract_reference_paths(
                    title=title,
                    abstract=abstract,
                    limit=args.web_search_limit,
                    cache_dir=web_cache,
                    provider=args.web_provider,
                )
                logger.info("ID %s: [WebSearch-Integration] 提取到 %d 条 web search 参考路径",
                            item_id, len(web_ref_paths))
                for wi, wp in enumerate(web_ref_paths):
                    wp_steps = wp.get("path", []) if isinstance(wp, dict) else []
                    preview = " -> ".join(
                        f"{s.get('head', '?')}-->{s.get('tail', '?')}" for s in wp_steps
                    )
                    logger.info("ID %s: [WebSearch-Integration]   WEB[%d] [%s] from='%s' | %s",
                                item_id, wi, wp.get("level", "?"), wp.get("source_paper", "?")[:40], preview[:100])
            except Exception as e:
                logger.warning("ID %s: [WebSearch-Integration] web search 失败 (non-fatal): %s", item_id, e)
        else:
            logger.info("[Item] Web Search 已关闭: 不使用 web 参考证据")

        gt_data = item.get("ground_truth", {})
        reference_evidence = build_reference_evidence(
            gt_data=gt_data,
            benchmark_gt_paths=gt_set,
            web_ref_paths=web_ref_paths,
            use_benchmark_gt=args.use_benchmark_gt,
            use_web_search=args.web_search,
        )
        reference_paths = reference_evidence["reference_paths"]
        gt_terms_list = reference_evidence["gt_terms"]
        gt_relations_list = reference_evidence["gt_relations"]
        gt_evidence_paths = reference_evidence["gt_evidence_paths"]
        logger.info(
            "ID %s: [Reference-Evidence] sources=%s",
            item_id,
            reference_evidence["source_counts"],
        )
        logger.info(
            "ID %s: [Reference-Evidence] reference_source=%s uses_llm_generated_gt=%s",
            item_id,
            args.reference_source,
            args.reference_source == "legacy_llm",
        )

        item_scores: Dict[str, list] = defaultdict(list)
        item_trace["evaluations"] = []

        # --- L1 ---
        l1_paths = normalize_paths_structure(pred_paths_dict.get("L1", []))
        logger.info("[Item] ── L1 评估: %d 条生成路径 ──", len(l1_paths))
        for pi, path in enumerate(l1_paths):
            s = evaluate_single_path(
                path, reference_paths, l1_query, primary_disc, "L1", kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
                abstract=abstract,
                use_kg_background=args.use_benchmark_gt,
                _item_id=item_id, _path_idx=pi,
            )
            for k, v in s.items():
                item_scores[f"L1_{k}"].append(v)
            item_trace["evaluations"].append({"level": "L1", "path_idx": pi, "path": _fmt_path_short(path)[:200], "scores": {k: round(v, 4) for k, v in s.items()}})

        # --- L2 ---
        l2_paths = normalize_paths_structure(pred_paths_dict.get("L2", []))
        logger.info("[Item] ── L2 评估: %d 条生成路径 ──", len(l2_paths))
        for i, path in enumerate(l2_paths):
            gen_query = l2_queries_from_data[i] if i < len(l2_queries_from_data) else l1_query
            s = evaluate_single_path(
                path, reference_paths, l1_query, primary_disc, "L2", gen_query=gen_query, kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
                abstract=abstract,
                use_kg_background=args.use_benchmark_gt,
                _item_id=item_id, _path_idx=i,
            )
            for k, v in s.items():
                item_scores[f"L2_{k}"].append(v)
            item_trace["evaluations"].append({"level": "L2", "path_idx": i, "path": _fmt_path_short(path)[:200], "scores": {k: round(v, 4) for k, v in s.items()}})

        # --- L3 ---
        l3_paths = normalize_paths_structure(pred_paths_dict.get("L3", []))
        logger.info("[Item] ── L3 评估: %d 条生成路径 ──", len(l3_paths))
        for i, path in enumerate(l3_paths):
            gen_query = l3_queries_from_data[i] if i < len(l3_queries_from_data) else l1_query
            s = evaluate_single_path(
                path, reference_paths, l1_query, primary_disc, "L3", gen_query=gen_query, kg=kg,
                gt_terms=gt_terms_list,
                gt_relations=gt_relations_list,
                gt_evidence_paths=gt_evidence_paths,
                abstract=abstract,
                use_kg_background=args.use_benchmark_gt,
                _item_id=item_id, _path_idx=i,
            )
            for k, v in s.items():
                item_scores[f"L3_{k}"].append(v)
            item_trace["evaluations"].append({"level": "L3", "path_idx": i, "path": _fmt_path_short(path)[:200], "scores": {k: round(v, 4) for k, v in s.items()}})

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
        try:
            from crossdisc_extractor.benchmark.x5_metrics import (
                compute_x5_breakdown,
                compute_x5_scores,
            )

            x5_scores = {
                level: compute_x5_scores(avg_scores, level=level)
                for level in ("L1", "L2", "L3")
            }
            x5_breakdown = {
                level: compute_x5_breakdown(avg_scores, level=level)
                for level in ("L1", "L2", "L3")
            }
        except Exception as exc:
            logger.warning("ID %s: X+5 聚合失败 (non-fatal): %s", item_id, exc)
            x5_scores = {}
            x5_breakdown = {}
        results.append({
            "id": item_id,
            "scores": avg_scores,
            "x5_scores": x5_scores,
            "x5_breakdown": x5_breakdown,
        })

        # ── Per-item summary log ─────────────────────────────────────
        logger.info("[Item] ── ID %s 评估完成，各级别平均分 ──", item_id)
        # Group by L1/L2/L3 and show key metrics
        for lvl in ["L1", "L2", "L3"]:
            key_metrics = ["consistency_f1", "innovation", "testability", "rao_stirling",
                           "factual_precision", "hallucination_rate", "chain_coherence"]
            parts = []
            for m in key_metrics:
                k = f"{lvl}_{m}"
                if k in avg_scores:
                    parts.append(f"{m}={avg_scores[k]:.3f}")
            if parts:
                logger.info("[Item]   %s: %s", lvl, "  ".join(parts))
        logger.info("=" * 70)

        # Save trace for this item
        item_trace["avg_scores"] = {k: round(v, 4) for k, v in avg_scores.items()}
        item_trace["x5_scores"] = x5_scores
        item_trace["x5_breakdown"] = x5_breakdown
        item_trace["reference_sources"] = reference_evidence["source_counts"]
        item_trace["gt_paths_count"] = reference_evidence["source_counts"]["benchmark_gt_paths"]
        item_trace["web_paths_count"] = reference_evidence["source_counts"]["web_ref_paths"]
        item_trace["combined_gt_count"] = reference_evidence["source_counts"]["reference_paths"]
        eval_trace.append(item_trace)

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

    # Save full evaluation trace
    trace_path = args.output.replace(".json", "_trace.json")
    try:
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(eval_trace, f, ensure_ascii=False, indent=2)
        print(f"Evaluation trace saved to {trace_path}")
    except Exception as e:
        logger.warning("Trace 保存失败: %s", e)


if __name__ == "__main__":
    main()

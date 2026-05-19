"""
crossdisc_extractor/benchmark/metrics.py

New evaluation metrics for cross-disciplinary hypothesis assessment.

Implements:
- Rao-Stirling Diversity Index (Stirling 2007)
- Information-Theoretic Novelty (surprisal-based)
- Reasoning Chain Coherence (per-hop semantic coherence)
- Structural Diversity (Torrance-inspired divergent thinking metrics)
- Hierarchical Depth Progression (L1→L2→L3 quality)
- Atypical Combination Index (Uzzi et al. 2013)
- KG Topology Metrics (graph theory indicators)
"""

from __future__ import annotations

import os
# 必须在 import huggingface_hub / sentence_transformers / transformers 之前设置，
# 否则库在 import 时缓存了联网状态，后续 local_files_only 无法阻止所有网络请求
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import gc
import json
import logging
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger("eval_metrics")

_SBERT_TEXT_CACHE: Dict[str, np.ndarray] = {}
_NLI_LABEL_CACHE: Dict[Tuple[str, str], str] = {}
_EMBEDDING_BRIDGING_CACHE: Dict[Tuple[str, str], float] = {}
_CONCEPT_COVERAGE_CACHE: Dict[Tuple[Tuple[str, ...], Tuple[str, ...], float], Dict[str, float]] = {}
_PATH_ALIGNMENT_CACHE: Dict[Tuple[str, Tuple[str, ...]], Dict[str, float]] = {}
_REMOTE_ASSOCIATION_CACHE: Dict[Tuple[Tuple[str, str], ...], float] = {}
_HALLUCINATION_RATE_CACHE: Dict[Tuple[Tuple[str, ...], Tuple[str, ...], str, float], float] = {}
_FACTUAL_PRECISION_CACHE: Dict[Tuple[Any, ...], float] = {}
_CHAIN_COHERENCE_CACHE: Dict[Tuple[Tuple[str, str, str, str], ...], Dict[str, Any]] = {}

try:
    import torch as _TORCH
except ImportError:  # pragma: no cover
    _TORCH = None


def _torch_cuda_available() -> bool:
    return bool(_TORCH is not None and _TORCH.cuda.is_available())


def _clear_torch_cuda_cache() -> None:
    if _TORCH is not None and _TORCH.cuda.is_available():
        try:
            _TORCH.cuda.empty_cache()
        except Exception:
            pass
    gc.collect()


def _resolve_sbert_device() -> str:
    raw = (os.getenv("CROSSDISC_SBERT_DEVICE") or "").strip().lower()
    if raw in {"", "cpu", "-1", "none", "off", "no-gpu", "nogpu"}:
        return "cpu"
    if raw == "auto":
        return "cuda" if _torch_cuda_available() else "cpu"
    return raw


def _candidate_sbert_devices(preferred: str) -> List[str]:
    if preferred == "cpu":
        return ["cpu"]
    if preferred.startswith("cuda"):
        return [preferred, "cpu"]
    return [preferred, "cpu"]

# ---------------------------------------------------------------------------
# Optional: sentence-transformers (graceful degradation)
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer

    _SBERT_MODEL: Optional[SentenceTransformer] = None
    _SBERT_DEVICE: Optional[str] = None

    def _get_sbert():
        global _SBERT_MODEL, _SBERT_DEVICE
        if _SBERT_MODEL is None:
            preferred_device = _resolve_sbert_device()
            last_error: Optional[Exception] = None
            for device in _candidate_sbert_devices(preferred_device):
                try:
                    _SBERT_MODEL = SentenceTransformer(
                        "paraphrase-multilingual-MiniLM-L12-v2",
                        local_files_only=True,
                        device=device,
                    )
                    _SBERT_DEVICE = device
                    if device == "cpu" and preferred_device != "cpu":
                        logger.warning(
                            "SBERT switched to CPU mode (preferred=%s).",
                            preferred_device,
                        )
                    break
                except Exception as exc:  # pragma: no cover - runtime hardware dependent
                    last_error = exc
                    _SBERT_MODEL = None
                    lower = str(exc).lower()
                    is_cuda_issue = "out of memory" in lower or "cuda" in lower
                    if device != "cpu" and is_cuda_issue:
                        logger.warning(
                            "SBERT init on %s failed (%s); retrying on CPU.",
                            device,
                            exc,
                        )
                        _clear_torch_cuda_cache()
                        continue
                    if device == "cpu":
                        logger.warning("SBERT CPU init failed: %s", exc)
                        return None
                    raise
            if _SBERT_MODEL is None and last_error is not None:
                logger.warning("SBERT unavailable, fallback to string similarity: %s", last_error)
        return _SBERT_MODEL

    _HAS_SBERT = True
except ImportError:
    _HAS_SBERT = False

    def _get_sbert():  # type: ignore[misc]
        return None

# ---------------------------------------------------------------------------
# Optional: NLI model for factual precision (graceful degradation)
# ---------------------------------------------------------------------------
try:
    from transformers import pipeline as _hf_pipeline

    _NLI_MODEL = None

    def _get_nli():
        global _NLI_MODEL
        if _NLI_MODEL is None:
            _NLI_MODEL = _hf_pipeline(
                "text-classification",
                model="microsoft/deberta-xlarge-mnli",
                device=-1,
            )
        return _NLI_MODEL

    _HAS_NLI = True
except ImportError:
    _HAS_NLI = False

    def _get_nli():  # type: ignore[misc]
        return None


def _cosine_sim_vectors(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _cache_text(text: str) -> str:
    return (text or "").strip()


def _cache_text_lower(text: str) -> str:
    return _cache_text(text).lower()


def _path_signature(path_steps: List[Dict[str, Any]]) -> Tuple[Tuple[str, str, str, str], ...]:
    return tuple(
        (
            _cache_text_lower(step.get("head", "")),
            _cache_text_lower(step.get("relation") or step.get("relation_type") or ""),
            _cache_text_lower(step.get("tail", "")),
            _cache_text_lower(step.get("claim", "")),
        )
        for step in path_steps
    )


def _relation_signature(gt_relations: List[Dict[str, Any]]) -> Tuple[Tuple[str, str, str, str], ...]:
    items = []
    for rel in gt_relations:
        items.append(
            (
                _cache_text_lower(rel.get("head", "")),
                _cache_text_lower(rel.get("tail", "")),
                _cache_text_lower(rel.get("relation_type", "")),
                _cache_text(rel.get("evidence_sentence", "")),
            )
        )
    return tuple(items)


def _path_to_text(path_steps: List[Dict[str, Any]]) -> str:
    parts = []
    for step in path_steps:
        head = step.get("head", "")
        rel = step.get("relation", step.get("relation_type", ""))
        tail = step.get("tail", "")
        parts.append(f"{head} [{rel}] {tail}")
    return " -> ".join(parts)


def _encode_texts_cached(texts: List[str]) -> Optional[List[np.ndarray]]:
    sbert = _get_sbert()
    if sbert is None:
        return None

    keys = [_cache_text(text) for text in texts]
    missing = [key for key in keys if key not in _SBERT_TEXT_CACHE]
    if missing:
        embeddings = sbert.encode(missing)
        for key, emb in zip(missing, embeddings):
            _SBERT_TEXT_CACHE[key] = np.asarray(emb)

    return [_SBERT_TEXT_CACHE[key] for key in keys]


def _cached_nli_label(premise: str, hypothesis: str) -> Optional[str]:
    premise_text = _cache_text(premise)
    hypothesis_text = _cache_text(hypothesis)
    if not premise_text or not hypothesis_text:
        return None

    cache_key = (premise_text, hypothesis_text)
    if cache_key in _NLI_LABEL_CACHE:
        return _NLI_LABEL_CACHE[cache_key]

    nli = _get_nli()
    if nli is None:
        return None

    result = nli(f"{premise_text}</s></s>{hypothesis_text}", truncation=True)
    label = result[0]["label"].upper() if result else "NEUTRAL"
    _NLI_LABEL_CACHE[cache_key] = label
    return label


# ===========================================================================
#  1. Rao-Stirling Diversity Index
# ===========================================================================

def _load_taxonomy(taxonomy_path: str) -> Dict[str, Any]:
    with open(taxonomy_path, encoding="utf-8") as f:
        return json.load(f)


def _build_discipline_paths(
    tree: Dict[str, Any], prefix: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """
    Build a mapping: leaf/node name → path from root.
    E.g. {"线性代数": ["数学", "代数学", "线性代数"], ...}
    """
    if prefix is None:
        prefix = []
    result: Dict[str, List[str]] = {}
    for key, value in tree.items():
        current_path = prefix + [key]
        result[key] = current_path
        if isinstance(value, dict) and value:
            result.update(_build_discipline_paths(value, current_path))
    return result


def taxonomy_distance(
    disc_i: str,
    disc_j: str,
    disc_paths: Dict[str, List[str]],
    max_depth: int,
) -> float:
    """
    Normalized tree distance between two disciplines via their
    Lowest Common Ancestor (LCA) in the taxonomy.

    Returns a value in [0, 1].  1 = maximally distant.
    """
    if disc_i == disc_j:
        return 0.0
    path_i = disc_paths.get(disc_i)
    path_j = disc_paths.get(disc_j)
    if path_i is None or path_j is None:
        return 1.0  # unknown discipline → max distance

    # Find LCA depth (length of common prefix)
    lca_depth = 0
    for a, b in zip(path_i, path_j):
        if a == b:
            lca_depth += 1
        else:
            break

    total_dist = (len(path_i) - lca_depth) + (len(path_j) - lca_depth)
    return min(total_dist / (2 * max(max_depth, 1)), 1.0)


def rao_stirling_diversity(
    path_steps: List[Dict[str, Any]],
    node_disciplines: Dict[str, str],
    disc_paths: Dict[str, List[str]],
    max_depth: int,
) -> float:
    """
    Rao-Stirling diversity index Δ = Σ_{i≠j} d_ij · p_i · p_j

    Captures variety, balance, and disparity of disciplines in a
    hypothesis path.

    Reference: Stirling (2007), J. Royal Society Interface.
    """
    # Collect disciplines of entities in the path
    entities = []
    for step in path_steps:
        for field in ("head", "tail"):
            ent = (step.get(field) or "").strip()
            if ent:
                entities.append(ent)

    disc_counts: Counter = Counter()
    for ent in entities:
        disc = node_disciplines.get(ent) or node_disciplines.get(ent.lower(), "unknown")
        if disc not in ("unknown", "hypothesis_inferred", "struct_relation_inferred"):
            disc_counts[disc] += 1

    total = sum(disc_counts.values())
    if total <= 1 or len(disc_counts) <= 1:
        return 0.0

    delta = 0.0
    discs = list(disc_counts.keys())
    for i in range(len(discs)):
        for j in range(i + 1, len(discs)):
            p_i = disc_counts[discs[i]] / total
            p_j = disc_counts[discs[j]] / total
            d_ij = taxonomy_distance(discs[i], discs[j], disc_paths, max_depth)
            delta += d_ij * p_i * p_j
    return delta * 2  # symmetry


# ===========================================================================
#  2. Information-Theoretic Novelty (surprisal)
# ===========================================================================

def information_theoretic_novelty(
    gen_path: List[Dict[str, Any]],
    all_kg_triples: Counter,
    total_triples: int,
) -> Dict[str, float]:
    """
    Novelty(path) = mean( -log2 P(triple_i | KG) )

    Uses Laplace-smoothed empirical distribution of triples in the
    global knowledge graph.
    """
    if not gen_path or total_triples == 0:
        return {"mean_surprisal": 0.0, "normalized_novelty": 0.0}

    vocab_size = len(all_kg_triples) + 1  # +1 for unseen

    step_surprisals: List[float] = []
    for step in gen_path:
        h = (step.get("head") or "").strip().lower()
        r = (step.get("relation") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()

        count = all_kg_triples.get((h, r, t), 0)
        p = (count + 1) / (total_triples + vocab_size)
        step_surprisals.append(-math.log2(p))

    max_surprisal = -math.log2(1 / (total_triples + vocab_size))

    return {
        "mean_surprisal": float(np.mean(step_surprisals)),
        "max_surprisal": float(np.max(step_surprisals)),
        "normalized_novelty": float(np.mean(step_surprisals) / max_surprisal) if max_surprisal > 0 else 0.0,
    }


# ===========================================================================
#  3. Reasoning Chain Coherence
# ===========================================================================

def _difflib_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def reasoning_chain_coherence(path_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Per-hop coherence of a reasoning chain.

    With sentence-transformers: uses embedding cosine similarity.
    Without: falls back to SequenceMatcher ratio.
    """
    if len(path_steps) <= 1:
        return {"overall_coherence": 1.0, "per_hop": [], "weakest_hop_score": 1.0}

    cache_key = tuple(
        (
            _cache_text(step.get("claim", "")),
            _cache_text(path_steps[i + 1].get("claim", "")) if i + 1 < len(path_steps) else "",
            _cache_text(step.get("tail", "")),
            _cache_text(path_steps[i + 1].get("head", "")) if i + 1 < len(path_steps) else "",
        )
        for i, step in enumerate(path_steps[:-1])
    )
    if cache_key in _CHAIN_COHERENCE_CACHE:
        cached = _CHAIN_COHERENCE_CACHE[cache_key]
        return {
            "overall_coherence": cached["overall_coherence"],
            "per_hop": [dict(hop) for hop in cached["per_hop"]],
            "weakest_hop_score": cached["weakest_hop_score"],
        }

    sbert = _get_sbert()

    hop_scores: List[Dict[str, Any]] = []
    for i in range(len(path_steps) - 1):
        curr_claim = (path_steps[i].get("claim") or "")
        next_claim = (path_steps[i + 1].get("claim") or "")
        curr_tail = (path_steps[i].get("tail") or "")
        next_head = (path_steps[i + 1].get("head") or "")

        if sbert is not None:
            embs = _encode_texts_cached([curr_claim, next_claim, curr_tail, next_head]) or []
            claim_coh = _cosine_sim_vectors(embs[0], embs[1])
            bridge_nat = _cosine_sim_vectors(embs[2], embs[3])
        else:
            claim_coh = _difflib_similarity(curr_claim, next_claim)
            bridge_nat = _difflib_similarity(curr_tail, next_head)

        combined = 0.6 * max(claim_coh, 0) + 0.4 * max(bridge_nat, 0)
        hop_scores.append({
            "hop": f"step{i + 1}→step{i + 2}",
            "claim_coherence": round(claim_coh, 4),
            "bridge_naturalness": round(bridge_nat, 4),
            "combined": round(combined, 4),
        })

    overall = float(np.mean([h["combined"] for h in hop_scores])) if hop_scores else 1.0
    weakest = min((h["combined"] for h in hop_scores), default=1.0)

    result = {
        "overall_coherence": round(overall, 4),
        "per_hop": hop_scores,
        "weakest_hop_score": round(weakest, 4),
    }
    _CHAIN_COHERENCE_CACHE[cache_key] = {
        "overall_coherence": result["overall_coherence"],
        "per_hop": [dict(hop) for hop in hop_scores],
        "weakest_hop_score": result["weakest_hop_score"],
    }
    return result


# ===========================================================================
#  4. Structural Diversity (Torrance-inspired)
# ===========================================================================

def structural_diversity(paths: List[List[Dict[str, Any]]]) -> Dict[str, float]:
    """
    Measures diversity across multiple hypothesis paths generated for the
    same paper at the same level.

    Inspired by Torrance Tests of Creative Thinking:
    - Fluency:   number of paths
    - Flexibility: diversity of relation types used
    - Pairwise Diversity: average semantic distance between paths
    - Entity Coverage: proportion of unique entities
    """
    if not paths:
        return {"fluency": 0, "flexibility": 0.0, "pairwise_diversity": 0.0, "entity_coverage": 0.0}

    fluency = len(paths)

    # Flexibility: diversity of relation types
    all_relation_types: Set[str] = set()
    all_entities: Set[str] = set()
    for path in paths:
        for step in path:
            rt = (step.get("relation_type") or step.get("relation") or "").strip().lower()
            if rt:
                all_relation_types.add(rt)
            for field in ("head", "tail"):
                ent = (step.get(field) or "").strip().lower()
                if ent:
                    all_entities.add(ent)

    flexibility = len(all_relation_types) / max(fluency, 1)

    # Pairwise diversity
    sbert = _get_sbert()
    if sbert is not None and fluency >= 2:
        path_texts = [
            " → ".join(
                f"{s.get('head', '')} [{s.get('relation', '')}] {s.get('tail', '')}"
                for s in path
            )
            for path in paths
        ]
        embeddings = sbert.encode(path_texts)
        dists = []
        for i, j in combinations(range(len(embeddings)), 2):
            sim = _cosine_sim_vectors(embeddings[i], embeddings[j])
            dists.append(1.0 - sim)
        pairwise_diversity = float(np.mean(dists)) if dists else 0.0
    else:
        # Fallback: Jaccard distance on entity sets
        if fluency >= 2:
            path_entity_sets = []
            for path in paths:
                ents = set()
                for step in path:
                    ents.add((step.get("head") or "").lower())
                    ents.add((step.get("tail") or "").lower())
                ents.discard("")
                path_entity_sets.append(ents)

            dists = []
            for i, j in combinations(range(len(path_entity_sets)), 2):
                union = path_entity_sets[i] | path_entity_sets[j]
                inter = path_entity_sets[i] & path_entity_sets[j]
                jd = 1.0 - (len(inter) / len(union)) if union else 0.0
                dists.append(jd)
            pairwise_diversity = float(np.mean(dists)) if dists else 0.0
        else:
            pairwise_diversity = 0.0

    # Entity coverage: unique entities / max possible entities
    max_entities = fluency * 4  # each 3-step path has at most 4 unique entities
    entity_coverage = len(all_entities) / max(max_entities, 1)

    return {
        "fluency": fluency,
        "flexibility": round(flexibility, 4),
        "pairwise_diversity": round(pairwise_diversity, 4),
        "entity_coverage": round(min(entity_coverage, 1.0), 4),
    }


# ===========================================================================
#  5. Hierarchical Depth Progression
# ===========================================================================

def _extract_entities_from_paths(paths: List[List[Dict[str, Any]]]) -> Set[str]:
    entities: Set[str] = set()
    for path in paths:
        for step in path:
            for field in ("head", "tail"):
                ent = (step.get(field) or "").strip().lower()
                if ent:
                    entities.add(ent)
    return entities


def _avg_semantic_span(paths: List[List[Dict[str, Any]]]) -> float:
    """Average semantic distance from path start to path end."""
    if not paths:
        return 0.0

    sbert = _get_sbert()
    spans: List[float] = []

    for path in paths:
        if len(path) < 2:
            continue
        start = (path[0].get("head") or "").strip()
        end = (path[-1].get("tail") or "").strip()
        if not start or not end:
            continue

        if sbert is not None:
            embs = sbert.encode([start, end])
            dist = 1.0 - _cosine_sim_vectors(embs[0], embs[1])
        else:
            dist = 1.0 - _difflib_similarity(start, end)
        spans.append(max(dist, 0.0))

    return float(np.mean(spans)) if spans else 0.0


def hierarchical_depth_progression(
    l1_paths: List[List[Dict[str, Any]]],
    l2_paths: List[List[Dict[str, Any]]],
    l3_paths: List[List[Dict[str, Any]]],
) -> Dict[str, float]:
    """
    Evaluate the quality of L1→L2→L3 deepening:
    - Concept Expansion: does each deeper level introduce new concepts?
    - Span Progression: does semantic span increase with depth?
    - Anchoring: do deeper levels still share core concepts with upper levels?
    """
    l1_ents = _extract_entities_from_paths(l1_paths)
    l2_ents = _extract_entities_from_paths(l2_paths)
    l3_ents = _extract_entities_from_paths(l3_paths)

    l1_span = _avg_semantic_span(l1_paths)
    l2_span = _avg_semantic_span(l2_paths)
    l3_span = _avg_semantic_span(l3_paths)

    # Concept Expansion
    l2_new = len(l2_ents - l1_ents) / max(len(l2_ents), 1) if l2_ents else 0.0
    l3_new = len(l3_ents - l2_ents) / max(len(l3_ents), 1) if l3_ents else 0.0

    # Span Progression (positive = good, deeper levels have wider span)
    span_prog_12 = max(l2_span - l1_span, 0.0)
    span_prog_23 = max(l3_span - l2_span, 0.0)

    # Anchoring (share core concepts with upper level)
    l2_anchor = len(l2_ents & l1_ents) / max(len(l1_ents), 1) if l1_ents else 0.0
    l3_anchor = len(l3_ents & l2_ents) / max(len(l2_ents), 1) if l2_ents else 0.0

    depth_quality = (l2_new + l3_new + span_prog_12 + span_prog_23) / 4

    return {
        "l2_concept_expansion": round(l2_new, 4),
        "l3_concept_expansion": round(l3_new, 4),
        "span_progression_l1_l2": round(span_prog_12, 4),
        "span_progression_l2_l3": round(span_prog_23, 4),
        "l2_anchoring": round(l2_anchor, 4),
        "l3_anchoring": round(l3_anchor, 4),
        "depth_quality": round(depth_quality, 4),
    }


# ===========================================================================
#  6. Atypical Combination Index (Uzzi et al. 2013)
# ===========================================================================

def build_cooccurrence_from_kg(
    all_kg_paths: List[List[Dict[str, Any]]],
) -> Tuple[Counter, float, float]:
    """
    Build a concept-pair co-occurrence matrix from KG paths.
    Returns (cooccurrence_counter, mean_freq, std_freq).
    """
    pair_counter: Counter = Counter()
    for path in all_kg_paths:
        for step in path:
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            if h and t:
                pair = tuple(sorted([h, t]))
                pair_counter[pair] += 1

    freqs = list(pair_counter.values()) if pair_counter else [0]
    return pair_counter, float(np.mean(freqs)), float(np.std(freqs))


def atypical_combination_index(
    path_steps: List[Dict[str, Any]],
    cooccurrence: Counter,
    mu: float,
    sigma: float,
) -> float:
    """
    Based on Uzzi et al. (2013, Science): high-impact work combines
    conventional pairings with a few atypical ones.

    Returns a score in [0, 1].  Higher = more atypical combinations.
    """
    pairs: List[float] = []
    for step in path_steps:
        h = (step.get("head") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()
        if h and t:
            pair = tuple(sorted([h, t]))
            freq = cooccurrence.get(pair, 0)
            pairs.append(freq)

    if not pairs:
        return 0.0

    median_freq = float(np.median(pairs))
    z_score = (median_freq - mu) / sigma if sigma > 0 else 0.0

    # sigmoid: lower freq (more negative z) → higher score
    return float(1.0 / (1.0 + math.exp(z_score)))


# ===========================================================================
#  7. KG Topology Metrics
# ===========================================================================

def kg_topology_metrics(nodes: List[Any], edges: List[Any]) -> Dict[str, float]:
    """
    Compute graph-theoretic topology metrics from a ConceptGraph.

    Metrics:
    - density, avg_betweenness, inverse_modularity,
      largest_cc_ratio, avg_path_length, clustering_coefficient
    """
    import networkx as nx

    G = nx.DiGraph()
    for node in nodes:
        nid = node.id if hasattr(node, "id") else node.get("id", "")
        disc = node.discipline if hasattr(node, "discipline") else node.get("discipline", "unknown")
        G.add_node(nid, discipline=disc)

    for edge in edges:
        src = edge.source if hasattr(edge, "source") else edge.get("source", "")
        tgt = edge.target if hasattr(edge, "target") else edge.get("target", "")
        G.add_edge(src, tgt)

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    if n_nodes == 0:
        return {
            "n_nodes": 0, "n_edges": 0, "density": 0.0,
            "avg_betweenness": 0.0, "inverse_modularity": 0.0,
            "largest_cc_ratio": 0.0, "avg_path_length": 0.0,
            "clustering_coefficient": 0.0,
        }

    G_und = G.to_undirected()

    # Density
    density = nx.density(G)

    # Betweenness centrality
    betweenness = nx.betweenness_centrality(G_und)
    avg_betweenness = float(np.mean(list(betweenness.values()))) if betweenness else 0.0

    # Modularity based on discipline partition
    disc_partition: Dict[str, set] = defaultdict(set)
    for nid, data in G.nodes(data=True):
        disc = data.get("discipline", "unknown")
        if disc not in ("unknown", "hypothesis_inferred", "struct_relation_inferred"):
            disc_partition[disc].add(nid)
        else:
            disc_partition["_other"].add(nid)

    partition_list = [frozenset(s) for s in disc_partition.values() if s]
    try:
        if len(partition_list) >= 2:
            modularity = nx.community.modularity(G_und, partition_list)
        else:
            modularity = 0.0
    except Exception:
        modularity = 0.0
    inverse_modularity = max(1.0 - modularity, 0.0)

    # Connected components
    components = list(nx.weakly_connected_components(G))
    largest_cc_size = max(len(c) for c in components) if components else 0
    largest_cc_ratio = largest_cc_size / n_nodes

    # Average shortest path (largest CC only)
    if largest_cc_size >= 2:
        largest_cc = max(components, key=len)
        sub = G_und.subgraph(largest_cc)
        try:
            avg_path_length = nx.average_shortest_path_length(sub)
        except nx.NetworkXError:
            avg_path_length = 0.0
    else:
        avg_path_length = 0.0

    # Clustering coefficient
    clustering = nx.average_clustering(G_und)

    return {
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "density": round(density, 4),
        "avg_betweenness": round(avg_betweenness, 4),
        "inverse_modularity": round(inverse_modularity, 4),
        "largest_cc_ratio": round(largest_cc_ratio, 4),
        "avg_path_length": round(avg_path_length, 4),
        "clustering_coefficient": round(clustering, 4),
    }


# ===========================================================================
#  8. Enhanced Path Consistency with Relation-Aware F1
# ===========================================================================

# Symmetric relation types (direction doesn't matter)
_SYMMETRIC_RELATIONS = {
    "corresponds_to", "maps_to", "correlates_with", "related_to",
    "co_occurs_with", "similar_to",
}

# Relation type semantic clusters
_RELATION_CLUSTERS = {
    "causal_positive": {"improves_metric", "driven_by", "extends", "generalizes"},
    "causal_negative": {"constrains", "inhibits", "limits"},
    "mapping": {"maps_to", "corresponds_to", "aligned_with"},
    "dependency": {"depends_on", "assumes", "requires"},
    "derivation": {"inferred_from", "derived_from", "based_on"},
    "application": {"method_applied_to", "used_for"},
}

_REL_TO_CLUSTER: Dict[str, str] = {}
for cluster_name, members in _RELATION_CLUSTERS.items():
    for m in members:
        _REL_TO_CLUSTER[m] = cluster_name


def _same_relation_cluster(r1: Optional[str], r2: Optional[str]) -> bool:
    c1 = _REL_TO_CLUSTER.get(r1 or "", "")
    c2 = _REL_TO_CLUSTER.get(r2 or "", "")
    return bool(c1 and c1 == c2)


def _normalize_rel(raw: str) -> str:
    """Lightweight relation normalization for matching."""
    s = (raw or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def enhanced_path_consistency(
    gen_path: List[Dict[str, Any]],
    gt_paths: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Relation-aware path consistency with Precision / Recall / F1.

    Scoring tiers:
      1.0  — (h, r, t) exact match
      0.8  — (h, t) match, relation in same semantic cluster
      0.5  — (h, t) match, different relation
      0.3  — (t, h) reverse match, symmetric relation
      0.1  — (t, h) reverse match, non-symmetric relation
      0.0  — no match
    """
    if not gen_path:
        return {"consistency_precision": 0.0, "consistency_recall": 0.0, "consistency_f1": 0.0}

    # Build GT triple index: (h, t) → normalized_relation
    gt_index: Dict[Tuple[str, str], str] = {}
    for gt_item in gt_paths:
        for step in gt_item.get("path", []):
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            r = _normalize_rel(step.get("relation_type") or step.get("relation") or "")
            if h and t:
                gt_index[(h, t)] = r

    if not gt_index:
        return {"consistency_precision": 0.0, "consistency_recall": 0.0, "consistency_f1": 0.0}

    # Precision: how well gen matches GT
    precision_score = 0.0
    for step in gen_path:
        h = (step.get("head") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()
        r_gen = _normalize_rel(step.get("relation_type") or step.get("relation") or "")

        if (h, t) in gt_index:
            r_gt = gt_index[(h, t)]
            if r_gen and r_gt and r_gen == r_gt:
                precision_score += 1.0
            elif _same_relation_cluster(r_gen, r_gt):
                precision_score += 0.8
            else:
                precision_score += 0.5
        elif (t, h) in gt_index:
            r_gt = gt_index[(t, h)]
            if r_gt in _SYMMETRIC_RELATIONS:
                precision_score += 0.3
            else:
                precision_score += 0.1

    precision = precision_score / len(gen_path)

    # Recall: how much of GT is covered
    gen_pairs = set()
    for step in gen_path:
        h = (step.get("head") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()
        gen_pairs.add((h, t))
        gen_pairs.add((t, h))  # allow reverse match for recall

    recall_matched = sum(1 for (h, t) in gt_index if (h, t) in gen_pairs)
    recall = recall_matched / len(gt_index)

    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "consistency_precision": round(precision, 4),
        "consistency_recall": round(recall, 4),
        "consistency_f1": round(f1, 4),
    }


# ===========================================================================
#  9. Embedding Bridging Score (replaces Jaccard-based Bridging)
# ===========================================================================

def embedding_bridging_score(gen_path: List[Dict[str, Any]]) -> float:
    """
    Semantic distance between first head and last tail using
    sentence embeddings.  Falls back to difflib if SBERT unavailable.
    """
    if not gen_path:
        return 0.0

    start = (gen_path[0].get("head") or "").strip()
    end = (gen_path[-1].get("tail") or "").strip()
    if not start or not end:
        return 0.0

    cache_key = (_cache_text(start), _cache_text(end))
    if cache_key in _EMBEDDING_BRIDGING_CACHE:
        return _EMBEDDING_BRIDGING_CACHE[cache_key]

    sbert = _get_sbert()
    if sbert is not None:
        embs = _encode_texts_cached([start, end]) or []
        sim = _cosine_sim_vectors(embs[0], embs[1])
        score = round(max(1.0 - sim, 0.0), 4)
    else:
        sim = _difflib_similarity(start, end)
        score = round(max(1.0 - sim, 0.0), 4)
    _EMBEDDING_BRIDGING_CACHE[cache_key] = score
    return score


# ===========================================================================
#  10. Concept Coverage (GT-aware)
# ===========================================================================

def concept_coverage(
    gen_path: List[Dict[str, Any]],
    gt_terms: List[str],
    threshold: float = 0.75,
) -> Dict[str, float]:
    """
    Measure how many GT terms are covered by a generated path.

    Uses soft matching: a GT term is "covered" if any entity in the
    generated path matches it with similarity >= threshold.

    Returns:
        {
            "concept_recall": float,    # GT terms covered / total GT terms
            "concept_precision": float, # gen entities matching GT / total gen entities
            "concept_f1": float,
        }
    """
    if not gen_path or not gt_terms:
        return {"concept_recall": 0.0, "concept_precision": 0.0, "concept_f1": 0.0}

    # Extract all entities from generated path
    gen_entities: List[str] = []
    for step in gen_path:
        for field in ("head", "tail"):
            ent = (step.get(field) or "").strip()
            if ent:
                gen_entities.append(ent)
    gen_entities = list(set(gen_entities))

    if not gen_entities:
        return {"concept_recall": 0.0, "concept_precision": 0.0, "concept_f1": 0.0}

    cache_key = (
        tuple(sorted(_cache_text(entity) for entity in gen_entities)),
        tuple(sorted(_cache_text(term) for term in gt_terms if term)),
        round(float(threshold), 4),
    )
    if cache_key in _CONCEPT_COVERAGE_CACHE:
        return dict(_CONCEPT_COVERAGE_CACHE[cache_key])

    # Use SBERT if available for matching, otherwise difflib
    sbert = _get_sbert()
    gen_entities = list(cache_key[0])
    gt_terms = list(cache_key[1])

    # Recall: how many GT terms are covered
    gt_covered = 0
    if sbert is not None:
        gt_embs = _encode_texts_cached(gt_terms) or []
        gen_embs = _encode_texts_cached(gen_entities) or []
    else:
        gt_embs = []
        gen_embs = []
    for gt_term in gt_terms:
        best_sim = 0.0
        if sbert is not None:
            gt_emb = gt_embs[gt_terms.index(gt_term)]
            for ge in gen_embs:
                sim = _cosine_sim_vectors(gt_emb, ge)
                best_sim = max(best_sim, sim)
        else:
            for ge in gen_entities:
                sim = _difflib_similarity(gt_term, ge)
                best_sim = max(best_sim, sim)

        if best_sim >= threshold:
            gt_covered += 1

    # Precision: how many gen entities match some GT term
    gen_matched = 0
    for ge in gen_entities:
        best_sim = 0.0
        if sbert is not None:
            ge_emb = gen_embs[gen_entities.index(ge)]
            for gte in gt_embs:
                sim = _cosine_sim_vectors(ge_emb, gte)
                best_sim = max(best_sim, sim)
        else:
            for gt_term in gt_terms:
                sim = _difflib_similarity(ge, gt_term)
                best_sim = max(best_sim, sim)

        if best_sim >= threshold:
            gen_matched += 1

    recall = gt_covered / len(gt_terms)
    precision = gen_matched / len(gen_entities)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    result = {
        "concept_recall": round(recall, 4),
        "concept_precision": round(precision, 4),
        "concept_f1": round(f1, 4),
    }
    _CONCEPT_COVERAGE_CACHE[cache_key] = result
    return dict(result)


# ===========================================================================
#  11. Relation Precision (GT-aware, evidence-backed)
# ===========================================================================

def relation_precision(
    gen_path: List[Dict[str, Any]],
    gt_relations: List[Dict[str, Any]],
    entity_threshold: float = 0.75,
) -> Dict[str, float]:
    """
    Measure how many generated relations are supported by GT evidence.

    A generated relation (head, tail) is "supported" if GT contains a
    relation with matching head+tail (soft match). Relation type matching
    is scored as a bonus.

    Args:
        gen_path: Generated path steps
        gt_relations: GT relations with evidence, each having
            {head, tail, relation_type, evidence_sentence}
        entity_threshold: Similarity threshold for entity matching

    Returns:
        {
            "relation_precision": float,  # supported gen relations / total gen
            "relation_type_accuracy": float,  # type matches / supported
            "evidence_coverage": float,  # GT relations covered / total GT
        }
    """
    if not gen_path:
        return {
            "relation_precision": 0.0,
            "relation_type_accuracy": 0.0,
            "evidence_coverage": 0.0,
        }
    if not gt_relations:
        return {
            "relation_precision": 0.0,
            "relation_type_accuracy": 0.0,
            "evidence_coverage": 0.0,
        }

    # Build GT relation index
    gt_pairs: List[Tuple[str, str, str]] = []
    for r in gt_relations:
        h = (r.get("head") or "").strip().lower()
        t = (r.get("tail") or "").strip().lower()
        rt = (r.get("relation_type") or "").strip().lower()
        if h and t:
            gt_pairs.append((h, t, rt))

    if not gt_pairs:
        return {
            "relation_precision": 0.0,
            "relation_type_accuracy": 0.0,
            "evidence_coverage": 0.0,
        }

    supported = 0
    type_matches = 0
    gt_covered: Set[int] = set()

    for step in gen_path:
        gen_h = (step.get("head") or "").strip().lower()
        gen_t = (step.get("tail") or "").strip().lower()
        gen_rt = (step.get("relation_type") or step.get("relation") or "").strip().lower()

        best_gt_idx = -1
        best_sim = 0.0

        for idx, (gt_h, gt_t, gt_rt) in enumerate(gt_pairs):
            # Soft match on head+tail
            h_sim = _difflib_similarity(gen_h, gt_h)
            t_sim = _difflib_similarity(gen_t, gt_t)
            avg_sim = (h_sim + t_sim) / 2

            # Also check reverse direction
            h_sim_rev = _difflib_similarity(gen_h, gt_t)
            t_sim_rev = _difflib_similarity(gen_t, gt_h)
            avg_sim_rev = (h_sim_rev + t_sim_rev) / 2

            pair_sim = max(avg_sim, avg_sim_rev)

            if pair_sim > best_sim:
                best_sim = pair_sim
                best_gt_idx = idx

        if best_sim >= entity_threshold and best_gt_idx >= 0:
            supported += 1
            gt_covered.add(best_gt_idx)
            # Check relation type match
            _, _, gt_rt = gt_pairs[best_gt_idx]
            if gen_rt and gt_rt and (
                gen_rt == gt_rt or _same_relation_cluster_str(gen_rt, gt_rt)
            ):
                type_matches += 1

    precision = supported / len(gen_path) if gen_path else 0.0
    type_acc = type_matches / max(supported, 1) if supported > 0 else 0.0
    evidence_cov = len(gt_covered) / len(gt_pairs) if gt_pairs else 0.0

    return {
        "relation_precision": round(precision, 4),
        "relation_type_accuracy": round(type_acc, 4),
        "evidence_coverage": round(evidence_cov, 4),
    }


def _same_relation_cluster_str(r1: str, r2: str) -> bool:
    """Check if two relation type strings belong to the same semantic cluster."""
    c1 = _REL_TO_CLUSTER.get(r1, "")
    c2 = _REL_TO_CLUSTER.get(r2, "")
    return bool(c1 and c1 == c2)


# ===========================================================================
#  12. Path Semantic Alignment (GT-aware, soft matching)
# ===========================================================================

def path_semantic_alignment(
    gen_path: List[Dict[str, Any]],
    gt_paths: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Semantic alignment between a generated path and the best-matching GT path.

    Instead of exact matching, computes embedding-based similarity between
    the full path texts.

    Args:
        gen_path: Generated path steps
        gt_paths: GT paths, each with a "path" key containing steps

    Returns:
        {
            "best_alignment": float,     # similarity to best GT path [0,1]
            "mean_alignment": float,     # mean similarity to all GT paths
            "best_gt_index": int,        # index of best-matching GT path
        }
    """
    if not gen_path or not gt_paths:
        return {"best_alignment": 0.0, "mean_alignment": 0.0, "best_gt_index": -1}

    gen_text = _path_to_text(gen_path)

    gt_texts = []
    for gt in gt_paths:
        steps = gt.get("path", gt) if isinstance(gt, dict) else gt
        if isinstance(steps, list):
            gt_texts.append(_path_to_text(steps))
        else:
            gt_texts.append(str(steps))

    if not gt_texts:
        return {"best_alignment": 0.0, "mean_alignment": 0.0, "best_gt_index": -1}

    cache_key = (_cache_text(gen_text), tuple(_cache_text(text) for text in gt_texts))
    if cache_key in _PATH_ALIGNMENT_CACHE:
        return dict(_PATH_ALIGNMENT_CACHE[cache_key])

    sbert = _get_sbert()
    if sbert is not None:
        all_texts = [gen_text] + gt_texts
        embs = _encode_texts_cached(all_texts) or []
        gen_emb = embs[0]
        gt_embs = embs[1:]

        sims = [_cosine_sim_vectors(gen_emb, ge) for ge in gt_embs]
    else:
        sims = [_difflib_similarity(gen_text, gt_text) for gt_text in gt_texts]

    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    mean_sim = float(np.mean(sims))

    result = {
        "best_alignment": round(max(best_sim, 0.0), 4),
        "mean_alignment": round(max(mean_sim, 0.0), 4),
        "best_gt_index": best_idx,
    }
    _PATH_ALIGNMENT_CACHE[cache_key] = result
    return dict(result)


# ===========================================================================
#  15. Causal Direction Accuracy  (D3 — 推理链结构)
# ===========================================================================

def causal_direction_accuracy(
    gen_path: List[Dict[str, Any]],
    gt_paths: List[Dict[str, Any]],
) -> float:
    """
    Proportion of GT-matched steps whose (head→tail) direction is correct.

    CDA = forward_match / any_match

    Reference: Simon (1983); Pearl (2009) — causal asymmetry.
    """
    if not gen_path:
        return 0.0

    gt_pairs: Set[Tuple[str, str]] = set()
    for gt_item in gt_paths:
        for step in gt_item.get("path", []):
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            if h and t:
                gt_pairs.add((h, t))

    if not gt_pairs:
        return 0.0

    forward_match = 0
    any_match = 0
    for step in gen_path:
        h = (step.get("head") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()
        fwd = (h, t) in gt_pairs
        rev = (t, h) in gt_pairs
        if fwd or rev:
            any_match += 1
            if fwd:
                forward_match += 1

    if any_match == 0:
        return 0.0
    return round(forward_match / any_match, 4)


# ===========================================================================
#  16. Disciplinary Leap Index  (D4 — 跨学科性)
# ===========================================================================

def disciplinary_leap_index(
    path_steps: List[Dict[str, Any]],
    node_disciplines: Dict[str, str],
    disc_paths: Dict[str, List[str]],
    max_depth: int,
) -> float:
    """
    Maximum single-step taxonomy distance in the path.

    DLI = max_s  d_tax(disc(head_s), disc(tail_s))

    Captures the boldest cross-disciplinary leap.
    Reference: Fortunato et al. (2018); Coccia (2022).
    """
    if not path_steps:
        return 0.0

    _SKIP = {"unknown", "hypothesis_inferred", "struct_relation_inferred"}
    max_dist = 0.0
    for step in path_steps:
        h = (step.get("head") or "").strip()
        t = (step.get("tail") or "").strip()
        disc_h = node_disciplines.get(h) or node_disciplines.get(h.lower(), "unknown")
        disc_t = node_disciplines.get(t) or node_disciplines.get(t.lower(), "unknown")
        if disc_h in _SKIP or disc_t in _SKIP:
            continue
        d = taxonomy_distance(disc_h, disc_t, disc_paths, max_depth)
        max_dist = max(max_dist, d)

    return round(max_dist, 4)


# ===========================================================================
#  17. Discipline Balance  (D4 — 跨学科性)
# ===========================================================================

def discipline_balance(
    path_steps: List[Dict[str, Any]],
    node_disciplines: Dict[str, str],
) -> float:
    """
    1 - Gini coefficient of discipline frequency distribution.

    Balance = 1 - Gini({p_1, ..., p_k})

    1.0 = perfectly balanced across disciplines, 0.0 = single discipline.
    Reference: Stirling (2007) balance dimension; Gini (1912).
    """
    if not path_steps:
        return 0.0

    _SKIP = {"unknown", "hypothesis_inferred", "struct_relation_inferred"}
    disc_counts: Counter = Counter()
    for step in path_steps:
        for field in ("head", "tail"):
            ent = (step.get(field) or "").strip()
            disc = node_disciplines.get(ent) or node_disciplines.get(ent.lower(), "unknown")
            if disc not in _SKIP:
                disc_counts[disc] += 1

    if len(disc_counts) <= 1:
        return 0.0

    values = sorted(disc_counts.values())
    n = len(values)
    total = sum(values)
    cumsum = sum((i + 1) * v for i, v in enumerate(values))
    gini = (2 * cumsum) / (n * total) - (n + 1) / n

    return round(max(1.0 - gini, 0.0), 4)


# ===========================================================================
#  18. Remote Association Index  (D5 — 新颖性与创造力)
# ===========================================================================

def remote_association_index(
    path_steps: List[Dict[str, Any]],
) -> float:
    """
    Mean per-step semantic distance between head and tail.

    RAI = mean_s (1 - cos(emb(head_s), emb(tail_s)))

    Reference: Mednick (1962) Remote Associations Test.
    """
    if not path_steps:
        return 0.0

    cache_key = tuple(
        (_cache_text(step.get("head", "")), _cache_text(step.get("tail", "")))
        for step in path_steps
        if _cache_text(step.get("head", "")) and _cache_text(step.get("tail", ""))
    )
    if cache_key in _REMOTE_ASSOCIATION_CACHE:
        return _REMOTE_ASSOCIATION_CACHE[cache_key]

    sbert = _get_sbert()
    distances: List[float] = []

    for step in path_steps:
        h = (step.get("head") or "").strip()
        t = (step.get("tail") or "").strip()
        if not h or not t:
            continue

        if sbert is not None:
            embs = _encode_texts_cached([h, t]) or []
            sim = _cosine_sim_vectors(embs[0], embs[1])
        else:
            sim = _difflib_similarity(h, t)

        distances.append(max(1.0 - sim, 0.0))

    if not distances:
        return 0.0
    score = round(float(np.mean(distances)), 4)
    _REMOTE_ASSOCIATION_CACHE[cache_key] = score
    return score


# ===========================================================================
#  19. Novelty-Convention Balance  (D5 — 新颖性与创造力)
# ===========================================================================

def novelty_convention_balance(
    gen_path: List[Dict[str, Any]],
    gt_paths: List[Dict[str, Any]],
) -> float:
    """
    Balance between novel and conventional steps.

    NCB = min(r_novel, r_conv) / max(r_novel, r_conv)

    A step is 'conventional' if (h,t) or (t,h) appears in GT.
    1.0 = perfect balance, 0.0 = all novel or all conventional.
    Reference: Uzzi et al. (2013) Science.
    """
    if not gen_path:
        return 0.0

    gt_pairs: Set[Tuple[str, str]] = set()
    for gt_item in gt_paths:
        for step in gt_item.get("path", []):
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            if h and t:
                gt_pairs.add((h, t))
                gt_pairs.add((t, h))

    n_conv = 0
    n_novel = 0
    for step in gen_path:
        h = (step.get("head") or "").strip().lower()
        t = (step.get("tail") or "").strip().lower()
        if (h, t) in gt_pairs:
            n_conv += 1
        else:
            n_novel += 1

    total = len(gen_path)
    if total == 0:
        return 0.0

    r_conv = n_conv / total
    r_novel = n_novel / total
    denom = max(r_novel, r_conv)
    if denom == 0:
        return 0.0
    return round(min(r_novel, r_conv) / denom, 4)


# ===========================================================================
#  20. Hallucination Rate  (D8 — 可靠性)
# ===========================================================================

def hallucination_rate(
    path_steps: List[Dict[str, Any]],
    gt_terms: List[str],
    abstract: str,
    entity_threshold: float = 0.75,
) -> float:
    """
    Proportion of path entities not grounded in GT terms or abstract.

    HR = ungrounded / total_entities

    Two-tier check: (1) substring in abstract, (2) SBERT soft-match to GT.
    Lower is better (0 = no hallucinations).
    Reference: Min et al. (2023) FActScore; Li et al. (2023) HaluEval.
    """
    if not path_steps:
        return 0.0

    entities: Set[str] = set()
    for step in path_steps:
        for field in ("head", "tail"):
            ent = (step.get(field) or "").strip()
            if ent:
                entities.add(ent)

    if not entities:
        return 0.0

    abstract_lower = (abstract or "").lower()
    gt_terms_lower = [(t or "").strip().lower() for t in (gt_terms or []) if t]
    cache_key = (
        tuple(sorted(_cache_text(entity) for entity in entities)),
        tuple(sorted(_cache_text(term) for term in gt_terms if term)),
        abstract_lower,
        round(float(entity_threshold), 4),
    )
    if cache_key in _HALLUCINATION_RATE_CACHE:
        return _HALLUCINATION_RATE_CACHE[cache_key]

    sbert = _get_sbert()
    gt_embs = None
    if sbert is not None and gt_terms:
        gt_embs = _encode_texts_cached(gt_terms) or []

    ungrounded = 0
    for ent in entities:
        ent_lower = ent.lower()

        # Check 1: substring in abstract
        if abstract_lower and ent_lower in abstract_lower:
            continue

        # Check 2: soft match against GT terms
        grounded = False
        if gt_embs is not None:
            ent_emb = (_encode_texts_cached([ent]) or [None])[0]
            for ge in gt_embs:
                if _cosine_sim_vectors(ent_emb, ge) >= entity_threshold:
                    grounded = True
                    break
        elif gt_terms_lower:
            for gt in gt_terms_lower:
                if _difflib_similarity(ent_lower, gt) >= entity_threshold:
                    grounded = True
                    break

        if not grounded:
            ungrounded += 1

    score = round(ungrounded / len(entities), 4)
    _HALLUCINATION_RATE_CACHE[cache_key] = score
    return score


# ===========================================================================
#  21. Factual Precision  (D8 — 可靠性)
# ===========================================================================

def factual_precision(
    path_steps: List[Dict[str, Any]],
    abstract: str = "",
    gt_terms: Optional[List[str]] = None,
    gt_relations: Optional[List[Dict[str, Any]]] = None,
    gt_evidence_paths: Optional[List[Dict[str, Any]]] = None,
    entity_threshold: float = 0.75,
) -> float:
    """
    Factual precision with multi-source support:
    1. Source abstract non-contradiction (weight 0.5)
    2. GT evidence/path text non-contradiction (weight 0.3)
    3. GT relation support / grounding fallback (weight 0.2)

    Missing channels are skipped and the remaining weights are renormalized.

    This makes the metric usable for query-only / held-out evaluation settings
    where the original abstract may be absent.
    """
    if not path_steps:
        return 0.0

    gt_terms = gt_terms or []
    gt_relations = gt_relations or []
    gt_evidence_paths = gt_evidence_paths or []
    cache_key = (
        _path_signature(path_steps),
        _cache_text(abstract),
        tuple(sorted(_cache_text(term) for term in gt_terms if term)),
        _relation_signature(gt_relations),
        tuple(
            sorted(
                (
                    _cache_text(path.get("context", "")),
                    tuple(
                        sorted(
                            _cache_text(
                                step.get("evidence")
                                or step.get("claim")
                                or step.get("relation")
                                or ""
                            )
                            for step in (path.get("path", []) or [])
                            if isinstance(step, dict)
                        )
                    ),
                )
                for path in gt_evidence_paths
                if isinstance(path, dict)
            )
        ),
        round(float(entity_threshold), 4),
    )
    if cache_key in _FACTUAL_PRECISION_CACHE:
        return _FACTUAL_PRECISION_CACHE[cache_key]

    gt_terms_key = cache_key[2]
    gt_term_list = list(gt_terms_key)
    gt_term_embs = _encode_texts_cached(gt_term_list) if gt_term_list else None

    def _entity_grounded(entity: str) -> bool:
        ent = (entity or "").strip()
        if not ent or not gt_term_list:
            return False
        ent_lower = ent.lower()
        sbert = _get_sbert()
        if sbert is not None and gt_term_embs is not None:
            ent_emb = (_encode_texts_cached([ent]) or [None])[0]
            return any(
                _cosine_sim_vectors(ent_emb, gt_emb) >= entity_threshold
                for gt_emb in gt_term_embs
            )
        return any(
            _difflib_similarity(ent_lower, (gt or "").strip().lower()) >= entity_threshold
            for gt in gt_term_list
        )

    def _step_supported_by_gt_relation(step: Dict[str, Any]) -> bool:
        gen_h = (step.get("head") or "").strip().lower()
        gen_t = (step.get("tail") or "").strip().lower()
        gen_rt = _normalize_rel(step.get("relation_type") or step.get("relation") or "")
        claim = (step.get("claim") or "").strip()

        if not gen_h or not gen_t or not gt_relations:
            return False

        best_relation: Optional[Dict[str, Any]] = None
        best_sim = 0.0
        best_reverse = False

        for rel in gt_relations:
            gt_h = (rel.get("head") or "").strip().lower()
            gt_t = (rel.get("tail") or "").strip().lower()
            if not gt_h or not gt_t:
                continue

            direct_sim = (_difflib_similarity(gen_h, gt_h) + _difflib_similarity(gen_t, gt_t)) / 2
            reverse_sim = (_difflib_similarity(gen_h, gt_t) + _difflib_similarity(gen_t, gt_h)) / 2

            if direct_sim >= reverse_sim:
                pair_sim = direct_sim
                reverse = False
            else:
                pair_sim = reverse_sim
                reverse = True

            if pair_sim > best_sim:
                best_sim = pair_sim
                best_relation = rel
                best_reverse = reverse

        if best_relation is None or best_sim < entity_threshold:
            return False

        gt_rt = _normalize_rel(best_relation.get("relation_type") or "")
        relation_supported = False
        if not gen_rt or not gt_rt:
            relation_supported = True
        elif gen_rt == gt_rt or _same_relation_cluster_str(gen_rt, gt_rt):
            relation_supported = True
        elif best_reverse and gt_rt in _SYMMETRIC_RELATIONS:
            relation_supported = True

        if not relation_supported:
            return False

        evidence_sentence = (best_relation.get("evidence_sentence") or "").strip()
        if claim and evidence_sentence:
            try:
                label = _cached_nli_label(evidence_sentence, claim)
                if label is None:
                    return True
                return label != "CONTRADICTION"
            except Exception as e:
                logger.warning("NLI inference failed for GT evidence factual check: %s", e)

        return True

    def _matched_gt_evidence_texts(step: Dict[str, Any]) -> List[str]:
        gen_h = (step.get("head") or "").strip().lower()
        gen_t = (step.get("tail") or "").strip().lower()
        if not gen_h or not gen_t:
            return []

        texts: List[str] = []
        for ref_path in gt_evidence_paths:
            if not isinstance(ref_path, dict):
                continue
            path_steps_ref = ref_path.get("path", []) or []
            best_sim = 0.0
            best_text = ""
            for ref_step in path_steps_ref:
                if not isinstance(ref_step, dict):
                    continue
                ref_h = (ref_step.get("head") or "").strip().lower()
                ref_t = (ref_step.get("tail") or "").strip().lower()
                if not ref_h or not ref_t:
                    continue
                direct_sim = (_difflib_similarity(gen_h, ref_h) + _difflib_similarity(gen_t, ref_t)) / 2
                reverse_sim = (_difflib_similarity(gen_h, ref_t) + _difflib_similarity(gen_t, ref_h)) / 2
                pair_sim = max(direct_sim, reverse_sim)
                if pair_sim > best_sim:
                    best_sim = pair_sim
                    best_text = (
                        (ref_step.get("evidence") or "").strip()
                        or (ref_step.get("claim") or "").strip()
                        or (ref_step.get("relation") or "").strip()
                    )
            if best_sim >= entity_threshold:
                if best_text:
                    texts.append(best_text)
                context = (ref_path.get("context") or "").strip()
                if context:
                    texts.append(context)
        return texts

    def _non_contradicted(text: str, claim: str) -> bool:
        if not text or not claim:
            return True
        try:
            label = _cached_nli_label(text, claim) or "NEUTRAL"
            return label != "CONTRADICTION"
        except Exception as e:
            logger.warning("NLI inference failed for claim: %s", e)
            return True  # fail-open

    def _source_abstract_score(step: Dict[str, Any]) -> Optional[float]:
        claim = (step.get("claim") or "").strip()
        if not claim:
            return 1.0
        if not abstract:
            return None
        if _get_nli() is None:
            logger.warning("NLI model unavailable; factual_precision source-abstract channel skipped")
            return None
        return 1.0 if _non_contradicted(abstract, claim) else 0.0

    def _gt_evidence_score(step: Dict[str, Any]) -> Optional[float]:
        claim = (step.get("claim") or "").strip()
        if not claim:
            return 1.0
        evidence_texts = _matched_gt_evidence_texts(step)
        if not evidence_texts:
            return None
        if _get_nli() is None:
            logger.warning("NLI model unavailable; factual_precision GT-evidence channel skipped")
            return None
        return 1.0 if any(_non_contradicted(text, claim) for text in evidence_texts) else 0.0

    def _gt_support_score(step: Dict[str, Any]) -> Optional[float]:
        claim = (step.get("claim") or "").strip()
        if not claim:
            return 1.0
        if _step_supported_by_gt_relation(step):
            return 1.0
        if _entity_grounded(step.get("head") or "") and _entity_grounded(step.get("tail") or ""):
            return 1.0
        if gt_relations or gt_terms:
            return 0.0
        return None

    step_scores: List[float] = []
    for step in path_steps:
        channel_values = [
            (0.5, _source_abstract_score(step)),
            (0.3, _gt_evidence_score(step)),
            (0.2, _gt_support_score(step)),
        ]
        available = [(w, v) for w, v in channel_values if v is not None]
        if not available:
            step_scores.append(0.0)
            continue
        total_weight = sum(w for w, _ in available)
        weighted = sum(w * float(v) for w, v in available) / total_weight
        step_scores.append(weighted)

    score = round(sum(step_scores) / len(path_steps), 4)
    _FACTUAL_PRECISION_CACHE[cache_key] = score
    return score

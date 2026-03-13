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

import json
import logging
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger("eval_metrics")

# ---------------------------------------------------------------------------
# Optional: sentence-transformers (graceful degradation)
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer

    _SBERT_MODEL: Optional[SentenceTransformer] = None

    def _get_sbert():
        global _SBERT_MODEL
        if _SBERT_MODEL is None:
            _SBERT_MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        return _SBERT_MODEL

    _HAS_SBERT = True
except ImportError:
    _HAS_SBERT = False

    def _get_sbert():  # type: ignore[misc]
        return None


def _cosine_sim_vectors(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


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

    sbert = _get_sbert()

    hop_scores: List[Dict[str, Any]] = []
    for i in range(len(path_steps) - 1):
        curr_claim = (path_steps[i].get("claim") or "")
        next_claim = (path_steps[i + 1].get("claim") or "")
        curr_tail = (path_steps[i].get("tail") or "")
        next_head = (path_steps[i + 1].get("head") or "")

        if sbert is not None:
            embs = sbert.encode([curr_claim, next_claim, curr_tail, next_head])
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

    return {
        "overall_coherence": round(overall, 4),
        "per_hop": hop_scores,
        "weakest_hop_score": round(weakest, 4),
    }


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

    sbert = _get_sbert()
    if sbert is not None:
        embs = sbert.encode([start, end])
        sim = _cosine_sim_vectors(embs[0], embs[1])
        return round(max(1.0 - sim, 0.0), 4)
    else:
        sim = _difflib_similarity(start, end)
        return round(max(1.0 - sim, 0.0), 4)


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

    # Use SBERT if available for matching, otherwise difflib
    sbert = _get_sbert()

    # Recall: how many GT terms are covered
    gt_covered = 0
    for gt_term in gt_terms:
        best_sim = 0.0
        if sbert is not None:
            gt_emb = sbert.encode([gt_term])
            gen_embs = sbert.encode(gen_entities)
            for ge in gen_embs:
                sim = _cosine_sim_vectors(gt_emb[0], ge)
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
            ge_emb = sbert.encode([ge])
            gt_embs = sbert.encode(gt_terms)
            for gte in gt_embs:
                sim = _cosine_sim_vectors(ge_emb[0], gte)
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

    return {
        "concept_recall": round(recall, 4),
        "concept_precision": round(precision, 4),
        "concept_f1": round(f1, 4),
    }


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

    def _path_to_text(path_steps: List[Dict[str, Any]]) -> str:
        parts = []
        for s in path_steps:
            h = s.get("head", "")
            r = s.get("relation", s.get("relation_type", ""))
            t = s.get("tail", "")
            parts.append(f"{h} [{r}] {t}")
        return " → ".join(parts)

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

    sbert = _get_sbert()
    if sbert is not None:
        all_texts = [gen_text] + gt_texts
        embs = sbert.encode(all_texts)
        gen_emb = embs[0]
        gt_embs = embs[1:]

        sims = [_cosine_sim_vectors(gen_emb, ge) for ge in gt_embs]
    else:
        sims = [_difflib_similarity(gen_text, gt_text) for gt_text in gt_texts]

    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    mean_sim = float(np.mean(sims))

    return {
        "best_alignment": round(max(best_sim, 0.0), 4),
        "mean_alignment": round(max(mean_sim, 0.0), 4),
        "best_gt_index": best_idx,
    }

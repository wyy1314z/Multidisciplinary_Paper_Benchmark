from __future__ import annotations

import json
import logging
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Set

from crossdisc_extractor.schemas import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    Extraction,
    GraphMetrics,
    HypothesisStep,
)

logger = logging.getLogger("crossdisc.graph_builder")

# Default taxonomy path (resolved relative to project root)
_DEFAULT_TAXONOMY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "msc_converted.json",
)


def build_graph_and_metrics(
    extraction: Extraction,
    taxonomy_path: Optional[str] = None,
) -> Extraction:
    """
    构建图谱并计算指标，更新 extraction 对象。

    Changes in v2:
    - Fixed bridging_score denominator (only counts edges with valid disciplines)
    - Added Rao-Stirling diversity, embedding bridging, KG topology, etc.
    """
    from crossdisc_extractor.benchmark.metrics import (
        _build_discipline_paths,
        _load_taxonomy,
        atypical_combination_index,
        build_cooccurrence_from_kg,
        embedding_bridging_score,
        kg_topology_metrics,
        rao_stirling_diversity,
        reasoning_chain_coherence,
    )

    struct = extraction
    hyp = extraction.假设
    meta = extraction.meta

    nodes_map: Dict[str, ConceptNode] = {}
    edges: List[ConceptEdge] = []

    # -------------------------------------------------------
    # 1. Add nodes from Struct Concepts
    # -------------------------------------------------------
    primary_disc = meta.primary or "Primary"
    if struct.概念 and struct.概念.主学科:
        for c in struct.概念.主学科:
            nid = (c.normalized or c.term).strip()
            if not nid:
                continue
            if nid not in nodes_map:
                nodes_map[nid] = ConceptNode(
                    id=nid,
                    term=c.term,
                    normalized=nid,
                    discipline=primary_disc,
                    evidence=c.evidence,
                    source=c.source,
                    confidence=c.confidence,
                )

    if struct.概念 and struct.概念.辅学科:
        for disc, concepts in struct.概念.辅学科.items():
            for c in concepts:
                nid = (c.normalized or c.term).strip()
                if not nid:
                    continue
                if nid not in nodes_map:
                    nodes_map[nid] = ConceptNode(
                        id=nid,
                        term=c.term,
                        normalized=nid,
                        discipline=disc,
                        evidence=c.evidence,
                        source=c.source,
                        confidence=c.confidence,
                    )

    # -- helpers ------------------------------------------------
    def find_node_id(text: str) -> Optional[str]:
        if not text:
            return None
        text = text.strip()
        if text in nodes_map:
            return text
        text_lower = text.lower()
        for nid, node in nodes_map.items():
            if nid.lower() == text_lower:
                return nid
            if node.term.lower() == text_lower:
                return nid
            if node.normalized and node.normalized.lower() == text_lower:
                return nid
        return None

    def get_or_create_node(text: str, discipline_hint: str = "hypothesis_inferred") -> str:
        text = text.strip()
        # Skip degenerate node ids (empty, lone punctuation, etc.)
        if not text or len(text) <= 1 and not ('\u4e00' <= text <= '\u9fff'):
            return ""
        found = find_node_id(text)
        if found:
            return found
        # If the node doesn't exist in concept list, only create it for
        # struct_relation sources (which are grounded in the paper text).
        # For hypothesis-inferred nodes, skip creation to prevent ghost nodes.
        if discipline_hint == "hypothesis_inferred":
            logger.debug("Skipping hypothesis-inferred ghost node: %s", text)
            return ""
        nid = text
        nodes_map[nid] = ConceptNode(
            id=nid,
            term=text,
            normalized=text,
            discipline=discipline_hint,
            evidence="",
            source="struct_relation_inferred",
            confidence=0.8,
        )
        return nid

    # -------------------------------------------------------
    # 2. Add edges from Struct Relations
    # -------------------------------------------------------
    struct_edges_set: Set[tuple] = set()

    if struct.跨学科关系:
        for r in struct.跨学科关系:
            src_id = get_or_create_node(r.head, discipline_hint="struct_relation_inferred")
            tgt_id = get_or_create_node(r.tail, discipline_hint="struct_relation_inferred")
            if not src_id or not tgt_id:
                continue
            edge = ConceptEdge(
                source=src_id,
                target=tgt_id,
                relation=r.relation,
                relation_type=r.relation_type,
                metadata={"evidence": r.evidence, "source": "struct", "direction": r.direction},
            )
            edges.append(edge)
            struct_edges_set.add((src_id, tgt_id))

    # -------------------------------------------------------
    # 3. Add edges from Hypothesis (H1/H2/H3)
    # -------------------------------------------------------
    hyp_edges_count = 0
    consistent_edges_count = 0
    hyp_covered_nodes: Set[str] = set()

    def process_hyp_level(paths: List[List[HypothesisStep]], level_label: str):
        nonlocal hyp_edges_count, consistent_edges_count
        if not paths:
            return
        for i, path in enumerate(paths):
            for step in path:
                src_id = get_or_create_node(step.head)
                tgt_id = get_or_create_node(step.tail)
                if not src_id or not tgt_id:
                    continue
                hyp_covered_nodes.add(src_id)
                hyp_covered_nodes.add(tgt_id)
                edge = ConceptEdge(
                    source=src_id,
                    target=tgt_id,
                    relation=step.relation,
                    relation_type=level_label,
                    metadata={"claim": step.claim, "step": step.step, "source": "hypothesis", "path_index": i},
                )
                edges.append(edge)
                hyp_edges_count += 1
                if (src_id, tgt_id) in struct_edges_set:
                    consistent_edges_count += 1

    process_hyp_level(hyp.一级, "H1")
    process_hyp_level(hyp.二级, "H2")
    process_hyp_level(hyp.三级, "H3")

    # -------------------------------------------------------
    # 4. Build Graph Object
    # -------------------------------------------------------
    graph = ConceptGraph(nodes=list(nodes_map.values()), edges=edges)
    extraction.graph = graph

    # -------------------------------------------------------
    # 5. Calculate Legacy Metrics
    # -------------------------------------------------------
    path_consistency = (consistent_edges_count / hyp_edges_count) if hyp_edges_count > 0 else 0.0

    base_struct_nodes = [n.id for n in nodes_map.values() if n.source not in ("hypothesis_inferred",)]
    covered_struct_nodes = [nid for nid in hyp_covered_nodes if nid in base_struct_nodes]
    coverage = (len(covered_struct_nodes) / len(base_struct_nodes)) if base_struct_nodes else 0.0

    # FIX: Bridging score — only count edges where *both* endpoints have valid disciplines
    def _is_valid_disc(d: str) -> bool:
        return d not in ("unknown", "hypothesis_inferred", "struct_relation_inferred")

    cross_disc_edges = 0
    valid_edges_for_bridging = 0
    for e in edges:
        s_node = nodes_map.get(e.source)
        t_node = nodes_map.get(e.target)
        if s_node and t_node:
            s_disc = s_node.discipline
            t_disc = t_node.discipline
            if _is_valid_disc(s_disc) and _is_valid_disc(t_disc):
                valid_edges_for_bridging += 1  # FIX: only count valid-disc edges
                if s_disc != t_disc:
                    cross_disc_edges += 1

    bridging_score = (cross_disc_edges / valid_edges_for_bridging) if valid_edges_for_bridging > 0 else 0.0

    # -------------------------------------------------------
    # 6. New Metrics (v2)
    # -------------------------------------------------------
    # Build node→discipline mapping for Rao-Stirling
    node_disciplines: Dict[str, str] = {}
    for nid, node in nodes_map.items():
        node_disciplines[nid] = node.discipline
        node_disciplines[nid.lower()] = node.discipline

    # Rao-Stirling diversity
    rs_diversity = 0.0
    tax_path = taxonomy_path or _DEFAULT_TAXONOMY
    try:
        taxonomy = _load_taxonomy(tax_path)
        disc_paths = _build_discipline_paths(taxonomy)
        max_depth = max((len(p) for p in disc_paths.values()), default=1)

        # Compute across all hypothesis paths
        all_hyp_steps: List[Dict[str, Any]] = []
        for level_paths in [hyp.一级, hyp.二级, hyp.三级]:
            for path in level_paths:
                for step in path:
                    all_hyp_steps.append({"head": step.head, "tail": step.tail})
        if all_hyp_steps:
            rs_diversity = rao_stirling_diversity(all_hyp_steps, node_disciplines, disc_paths, max_depth)
    except Exception as exc:
        logger.warning("Failed to compute Rao-Stirling diversity: %s", exc)

    # Embedding bridging (across all L3 paths — deepest level)
    emb_bridging = 0.0
    try:
        l3_step_dicts = [
            [{"head": s.head, "tail": s.tail, "relation": s.relation} for s in path]
            for path in hyp.三级
        ]
        if l3_step_dicts:
            emb_scores = [embedding_bridging_score(p) for p in l3_step_dicts]
            emb_bridging = float(sum(emb_scores) / len(emb_scores))
        elif hyp.一级:
            l1_step_dicts = [
                [{"head": s.head, "tail": s.tail, "relation": s.relation} for s in path]
                for path in hyp.一级
            ]
            emb_scores = [embedding_bridging_score(p) for p in l1_step_dicts]
            emb_bridging = float(sum(emb_scores) / len(emb_scores))
    except Exception as exc:
        logger.warning("Failed to compute embedding bridging: %s", exc)

    # Chain coherence (average across all levels)
    chain_coh = 0.0
    try:
        coh_scores: list = []
        for level_paths in [hyp.一级, hyp.二级, hyp.三级]:
            for path in level_paths:
                step_dicts = [{"head": s.head, "tail": s.tail, "claim": s.claim, "relation": s.relation} for s in path]
                result = reasoning_chain_coherence(step_dicts)
                coh_scores.append(result["overall_coherence"])
        chain_coh = float(sum(coh_scores) / len(coh_scores)) if coh_scores else 0.0
    except Exception as exc:
        logger.warning("Failed to compute chain coherence: %s", exc)

    # KG topology
    kg_density = 0.0
    kg_inv_mod = 0.0
    kg_lcc = 0.0
    kg_betw = 0.0
    kg_clust = 0.0
    try:
        topo = kg_topology_metrics(graph.nodes, graph.edges)
        kg_density = topo.get("density", 0.0)
        kg_inv_mod = topo.get("inverse_modularity", 0.0)
        kg_lcc = topo.get("largest_cc_ratio", 0.0)
        kg_betw = topo.get("avg_betweenness", 0.0)
        kg_clust = topo.get("clustering_coefficient", 0.0)
    except Exception as exc:
        logger.warning("Failed to compute KG topology metrics: %s", exc)

    # Atypical combination (using self-contained co-occurrence)
    atypical_comb = 0.0
    try:
        all_step_dicts_for_cooc = []
        for level_paths in [hyp.一级, hyp.二级, hyp.三级]:
            for path in level_paths:
                for step in path:
                    all_step_dicts_for_cooc.append([{"head": step.head, "tail": step.tail}])
        if all_step_dicts_for_cooc:
            flat_paths = [sd for p in all_step_dicts_for_cooc for sd in p]
            cooc, mu, sigma = build_cooccurrence_from_kg([flat_paths])
            # Use all hypothesis steps as the "corpus" for now
            all_flat = [{"head": s.head, "tail": s.tail} for lp in [hyp.一级, hyp.二级, hyp.三级] for p in lp for s in p]
            if all_flat and sigma > 0:
                atypical_comb = atypical_combination_index(all_flat, cooc, mu, sigma)
    except Exception as exc:
        logger.warning("Failed to compute atypical combination: %s", exc)

    # -------------------------------------------------------
    # 7. Assemble GraphMetrics
    # -------------------------------------------------------
    extraction.metrics = GraphMetrics(
        path_consistency=path_consistency,
        coverage=coverage,
        bridging_score=bridging_score,
        # v2 metrics
        rao_stirling_diversity=round(rs_diversity, 4),
        embedding_bridging=round(emb_bridging, 4),
        chain_coherence=round(chain_coh, 4),
        atypical_combination=round(atypical_comb, 4),
        kg_density=round(kg_density, 4),
        kg_inverse_modularity=round(kg_inv_mod, 4),
        kg_largest_cc_ratio=round(kg_lcc, 4),
        kg_avg_betweenness=round(kg_betw, 4),
        kg_clustering_coefficient=round(kg_clust, 4),
    )

    return extraction

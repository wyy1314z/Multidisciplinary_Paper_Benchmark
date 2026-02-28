from typing import List, Dict, Any, Set, Optional
from collections import defaultdict

from crossdisc_extractor.schemas import (
    Extraction, 
    ConceptGraph, ConceptNode, ConceptEdge, GraphMetrics,
    HypothesisStep
)

def build_graph_and_metrics(extraction: Extraction) -> Extraction:
    """
    构建图谱并计算指标，更新 extraction 对象。
    """
    struct = extraction
    hyp = extraction.假设
    meta = extraction.meta

    nodes_map: Dict[str, ConceptNode] = {}
    edges: List[ConceptEdge] = []

    # -------------------------------------------------------
    # 1. Add nodes from Struct Concepts
    # -------------------------------------------------------
    
    # Primary
    primary_disc = meta.primary or "Primary"
    if struct.概念 and struct.概念.主学科:
        for c in struct.概念.主学科:
            # 优先使用 normalized，其次 term
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
                    confidence=c.confidence
                )
    
    # Secondary
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
                        discipline=disc, # 使用分组名作为学科
                        evidence=c.evidence,
                        source=c.source,
                        confidence=c.confidence
                    )

    # Helper: Find existing node id by flexible matching
    def find_node_id(text: str) -> Optional[str]:
        if not text:
            return None
        text = text.strip()
        # 1. Exact match on ID
        if text in nodes_map:
            return text
        # 2. Match on term (case insensitive)
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
        found = find_node_id(text)
        if found:
            return found
        
        # Create new
        nid = text
        nodes_map[nid] = ConceptNode(
            id=nid,
            term=text,
            normalized=text,
            discipline=discipline_hint,
            evidence="",
            source="hypothesis_inferred",
            confidence=0.8 # Default lower confidence for inferred
        )
        return nid

    # -------------------------------------------------------
    # 2. Add edges from Struct Relations
    # -------------------------------------------------------
    struct_edges_set = set() # For consistency check: (src_id, tgt_id)
    
    if struct.跨学科关系:
        for r in struct.跨学科关系:
            src_id = get_or_create_node(r.head, discipline_hint="struct_relation_inferred")
            tgt_id = get_or_create_node(r.tail, discipline_hint="struct_relation_inferred")
            
            edge = ConceptEdge(
                source=src_id,
                target=tgt_id,
                relation=r.relation,
                relation_type=r.relation_type,
                metadata={
                    "evidence": r.evidence, 
                    "source": "struct",
                    "direction": r.direction
                }
            )
            edges.append(edge)
            struct_edges_set.add((src_id, tgt_id))

    # -------------------------------------------------------
    # 3. Add edges from Hypothesis (H1/H2/H3)
    # -------------------------------------------------------
    hyp_edges_count = 0
    consistent_edges_count = 0
    hyp_covered_nodes = set()

    def process_hyp_level(paths: List[List[HypothesisStep]], level_label: str):
        nonlocal hyp_edges_count, consistent_edges_count
        
        if not paths:
            return

        for i, path in enumerate(paths):
            for step in path:
                src_id = get_or_create_node(step.head)
                tgt_id = get_or_create_node(step.tail)
                
                hyp_covered_nodes.add(src_id)
                hyp_covered_nodes.add(tgt_id)

                edge = ConceptEdge(
                    source=src_id,
                    target=tgt_id,
                    relation=step.relation,
                    relation_type=level_label, # H1 / H2 / H3
                    metadata={
                        "claim": step.claim, 
                        "step": step.step, 
                        "source": "hypothesis",
                        "path_index": i
                    }
                )
                edges.append(edge)
                hyp_edges_count += 1
                
                # Check consistency (undirected check or directed?)
                # Struct relations are directed. Assuming hypothesis steps are also directed A->B.
                if (src_id, tgt_id) in struct_edges_set:
                    consistent_edges_count += 1

    process_hyp_level(hyp.一级, "H1")
    process_hyp_level(hyp.二级, "H2")
    process_hyp_level(hyp.三级, "H3")

    # -------------------------------------------------------
    # 4. Build Graph Object
    # -------------------------------------------------------
    graph = ConceptGraph(
        nodes=list(nodes_map.values()),
        edges=edges
    )
    extraction.graph = graph

    # -------------------------------------------------------
    # 5. Calculate Metrics
    # -------------------------------------------------------
    
    # Path Consistency: % of hypothesis edges that align with struct edges
    # (Existing struct edges that confirm hypothesis steps)
    path_consistency = (consistent_edges_count / hyp_edges_count) if hyp_edges_count > 0 else 0.0

    # Coverage: % of Struct Nodes (excluding purely inferred ones) covered by Hypothesis
    # "Struct Nodes" = nodes that came from Struct Concepts or Struct Relations
    base_struct_nodes = [
        n.id for n in nodes_map.values() 
        if n.source not in ("hypothesis_inferred",)
    ]
    covered_struct_nodes = [nid for nid in hyp_covered_nodes if nid in base_struct_nodes]
    
    coverage = (len(covered_struct_nodes) / len(base_struct_nodes)) if base_struct_nodes else 0.0

    # Bridging Score: Ratio of edges connecting different disciplines (only counting Struct Edges for now? 
    # Or all edges? Usually bridging refers to the extracted knowledge quality.)
    # Let's calculate it based on the Struct Relations to measure the "Cross-disciplinarity" of the extraction.
    # Or maybe the Hypothesis bridging? 
    # "跨学科桥接度" likely refers to how well the graph connects different disciplines.
    
    cross_disc_edges = 0
    valid_edges_for_bridging = 0
    
    for e in edges:
        # Only consider edges that are not purely hypothesis steps (or include them?)
        # Let's include all edges to see the full picture.
        s_node = nodes_map.get(e.source)
        t_node = nodes_map.get(e.target)
        
        if s_node and t_node:
            valid_edges_for_bridging += 1
            s_disc = s_node.discipline
            t_disc = t_node.discipline
            
            # Filter out "unknown" or "inferred" if we want strict discipline bridging
            # But "hypothesis_inferred" nodes don't have discipline info. 
            # So maybe only count edges where both nodes have known disciplines.
            
            is_valid_disc = lambda d: d not in ("unknown", "hypothesis_inferred", "struct_relation_inferred")
            
            if is_valid_disc(s_disc) and is_valid_disc(t_disc):
                if s_disc != t_disc:
                    cross_disc_edges += 1
            
    bridging_score = (cross_disc_edges / valid_edges_for_bridging) if valid_edges_for_bridging > 0 else 0.0

    extraction.metrics = GraphMetrics(
        path_consistency=path_consistency,
        coverage=coverage,
        bridging_score=bridging_score
    )

    return extraction

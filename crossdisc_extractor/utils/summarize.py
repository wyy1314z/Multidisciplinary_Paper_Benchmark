# # crossdisc_extractor/utils/summarize.py
# from __future__ import annotations

# import json
# from typing import Dict, Any, List

# from schemas import StructExtraction, ConceptEntry, RelationEntry


# def _concept_to_dict(c: ConceptEntry) -> Dict[str, Any]:
#     return {
#         "term": c.term,
#         "normalized": c.normalized,
#         "std_label": c.std_label,
#         "evidence": c.evidence,
#         "source": c.source,
#         "confidence": c.confidence,
#     }


# def _relation_to_dict(r: RelationEntry) -> Dict[str, Any]:
#     return {
#         "head": r.head,
#         "tail": r.tail,
#         "relation": r.relation,
#         "relation_type": r.relation_type,
#         "relation_type_norm": getattr(r, "relation_type_norm", None),
#         "relation_type_raw": getattr(r, "relation_type_raw", None),
#         "direction": r.direction,
#         "quant": r.quant.model_dump() if r.quant else None,
#         "assumptions": r.assumptions,
#         "evidence": r.evidence,
#         "source": r.source,
#         "confidence": r.confidence,
#     }


# def build_struct_summary_json(struct: StructExtraction) -> str:
#     """
#     为阶段 3（假设生成）构建一个“结构化摘要”JSON 字符串，
#     包括 meta / 主学科概念 / 每个辅学科的概念 / 关系。
#     """
#     meta = struct.meta
#     concepts = struct.概念
#     rels = struct.跨学科关系 or []

#     primary_concepts = [_concept_to_dict(c) for c in concepts.主学科]

#     secondary_concepts: Dict[str, List[Dict[str, Any]]] = {}
#     for sec, lst in (concepts.辅学科 or {}).items():
#         secondary_concepts[sec] = [_concept_to_dict(c) for c in lst]

#     rel_dicts = [_relation_to_dict(r) for r in rels]

#     summary = {
#         "meta": {
#             "title": meta.title,
#             "primary": meta.primary,
#             "secondary_list": meta.secondary_list,
#         },
#         "primary_concepts": primary_concepts,
#         "secondary_concepts": secondary_concepts,
#         "relations": rel_dicts,
#     }
#     return json.dumps(summary, ensure_ascii=False, indent=2)


# crossdisc_extractor/utils/summarize.py
from __future__ import annotations

import json
from typing import Dict, Any, List

from crossdisc_extractor.schemas import StructExtraction, ConceptEntry, RelationEntry


def _concept_to_dict(c: ConceptEntry) -> Dict[str, Any]:
    return {
        "term": c.term,
        "normalized": c.normalized,
        "std_label": c.std_label,
        "evidence": c.evidence,
        "source": c.source,
        "confidence": c.confidence,
    }


def _relation_to_dict(r: RelationEntry) -> Dict[str, Any]:
    return {
        "head": r.head,
        "tail": r.tail,
        "relation": r.relation,
        "relation_type": r.relation_type,
        "direction": r.direction,
        "quant": r.quant.model_dump() if r.quant else None,
        "assumptions": r.assumptions,
        "evidence": r.evidence,
        "source": r.source,
        "confidence": r.confidence,
    }


def build_struct_summary_json(struct: StructExtraction) -> str:
    """
    为阶段 3（假设生成）构建一个“结构化摘要”JSON 字符串，
    包括 meta / 主学科概念 / 每个辅学科的概念 / 关系。
    """
    meta = struct.meta
    concepts = struct.概念
    rels = struct.跨学科关系 or []

    primary_concepts = [_concept_to_dict(c) for c in concepts.主学科]

    secondary_concepts: Dict[str, List[Dict[str, Any]]] = {}
    for sec, lst in (concepts.辅学科 or {}).items():
        secondary_concepts[sec] = [_concept_to_dict(c) for c in lst]

    rel_dicts = [_relation_to_dict(r) for r in rels]

    summary = {
        "meta": {
            "title": meta.title,
            "primary": meta.primary,
            "secondary_list": meta.secondary_list,
        },
        "primary_concepts": primary_concepts,
        "secondary_concepts": secondary_concepts,
        "relations": rel_dicts,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)

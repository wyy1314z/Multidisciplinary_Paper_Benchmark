# crossdisc_extractor/__init__.py
"""
Cross-disciplinary benchmark extractor (multi-stage LLM pipeline).

Stages:
1) struct: meta + 概念 + 跨学科关系
2) query: 按辅助学科分类 + 查询(三级)
3) hypothesis: 假设(三级知识路径 + 总结)
"""

__version__ = "0.1.0"

from crossdisc_extractor.config import LanguageMode, PipelineConfig
from crossdisc_extractor.schemas import (
    ConceptEdge,
    ConceptEntry,
    ConceptGraph,
    ConceptNode,
    Concepts,
    Extraction,
    GraphMetrics,
    Hypothesis3Levels,
    HypothesisStep,
    MetaInfo,
    Query3Levels,
    QueryAndBuckets,
    RelationEntry,
    StructExtraction,
)

__all__ = [
    "__version__",
    "LanguageMode",
    "PipelineConfig",
    "ConceptEdge",
    "ConceptEntry",
    "ConceptGraph",
    "ConceptNode",
    "Concepts",
    "Extraction",
    "GraphMetrics",
    "Hypothesis3Levels",
    "HypothesisStep",
    "MetaInfo",
    "Query3Levels",
    "QueryAndBuckets",
    "RelationEntry",
    "StructExtraction",
]

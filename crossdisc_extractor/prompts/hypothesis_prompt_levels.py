# crossdisc_extractor/prompts/hypothesis_prompt_levels.py
"""
P1–P5 五级 prompt 策略：逐步增加引导信息量的假设生成 prompt。

用于消融实验，评估不同引导程度对跨学科假设生成质量的影响。

| 级别 | Query       | 论文信息              | 结构化知识          | 格式约束              |
|------|-------------|----------------------|--------------------|-----------------------|
| P1   | L1 only     | 无                   | 无                 | 自由文本              |
| P2   | L1 + L2     | abstract + 学科角色   | 无                 | 自由文本              |
| P3   | L1+L2+L3    | abstract + 学科角色   | 概念列表            | 半结构化              |
| P4   | L1+L2+L3    | abstract + 学科角色   | 概念 + 关系         | 半结构化（含推理链）   |
| P5   | L1+L2+L3    | 完整结构化摘要        | 概念+关系+路径约束   | 严格 3-step 路径      |
"""
from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from crossdisc_extractor.schemas import (
    ConceptEntry,
    Query3Levels,
    RelationEntry,
    StructExtraction,
)

logger = logging.getLogger("crossdisc.prompt_levels")


# ---------------------------------------------------------------------------
#  Enum
# ---------------------------------------------------------------------------

class PromptLevel(str, Enum):
    P1 = "P1"  # L1 query only
    P2 = "P2"  # + L2 queries, abstract, discipline role
    P3 = "P3"  # + L3 queries, concepts
    P4 = "P4"  # + relations
    P5 = "P5"  # full structured pipeline (current system)


# ---------------------------------------------------------------------------
#  P1 — Minimal: L1 query only, no paper context
# ---------------------------------------------------------------------------

SYSTEM_P1 = (
    "You are a researcher. Given a research question, propose a novel, "
    "specific, and testable hypothesis based on your own knowledge."
)

USER_P1 = """Research Question:
{l1_query}

Please propose a novel hypothesis that addresses this question.
Your hypothesis should be specific, testable, and go beyond common knowledge.
Output your hypothesis as a concise paragraph."""


# ---------------------------------------------------------------------------
#  P2 — Discipline-Guided: + L2 queries, abstract, discipline role
# ---------------------------------------------------------------------------

SYSTEM_P2 = (
    "You are a {primary} researcher with expertise in cross-disciplinary "
    "research involving {secondary_list}. You are tasked with generating "
    "novel hypotheses that bridge insights across these disciplines."
)

USER_P2 = """Paper Abstract:
{abstract}

This paper spans multiple disciplines:
- Primary: {primary}
- Secondary: {secondary_list}

Macro-level Research Question:
{l1_query}

Sub-questions (discipline-specific):
{l2_block}

Based on the abstract and the research questions above, generate novel
hypotheses that address both the macro question and the sub-questions.
For each question, provide a concise hypothesis paragraph.

Output format:
L1 Hypothesis: <paragraph>
L2 Hypotheses:
- Q1: <paragraph>
- Q2: <paragraph>
..."""


# ---------------------------------------------------------------------------
#  P3 — Concept-Enriched: + L3 queries, extracted concepts
# ---------------------------------------------------------------------------

SYSTEM_P3 = (
    "You are a {primary} researcher with expertise in cross-disciplinary "
    "research. You are given structured domain concepts extracted from a "
    "paper and tasked with generating hypotheses that connect concepts "
    "across disciplines."
)

USER_P3 = """Paper Abstract:
{abstract}

Disciplines:
- Primary: {primary}
- Secondary: {secondary_list}

Extracted Domain Concepts:
{concepts_block}

Research Questions:
[Macro-level] {l1_query}

[Discipline-specific]
{l2_block}

[Operational-level]
{l3_block}

Using the extracted concepts as building blocks, generate novel hypotheses
for each level of research question. Each hypothesis should:
1. Reference specific concepts from at least two disciplines
2. Propose a concrete mechanism or relationship
3. Be testable and falsifiable

Output format:
L1 Hypothesis: <paragraph referencing key concepts>
L2 Hypotheses:
- Q1: <paragraph>
- Q2: <paragraph>
...
L3 Hypotheses:
- Q1: <paragraph>
- Q2: <paragraph>
..."""


# ---------------------------------------------------------------------------
#  P4 — Relation-Augmented: + cross-disciplinary relations
# ---------------------------------------------------------------------------

SYSTEM_P4 = (
    "You are a cross-disciplinary research hypothesis generator. You are "
    "given structured knowledge extracted from a paper, including domain "
    "concepts and their cross-disciplinary relationships. Use these as a "
    "foundation to generate novel hypotheses that extend beyond the known "
    "relationships."
)

USER_P4 = """Paper Abstract:
{abstract}

Disciplines:
- Primary: {primary}
- Secondary: {secondary_list}

Extracted Concepts:
{concepts_block}

Known Cross-Disciplinary Relationships:
{relations_block}

Research Questions:
[Macro-level] {l1_query}

[Discipline-specific]
{l2_block}

[Operational-level]
{l3_block}

Based on the known concepts and relationships, generate novel hypotheses
for each level of research question. Each hypothesis should:
1. Build upon (but go beyond) the known relationships
2. Propose new connections or mechanisms not explicitly stated
3. Involve concepts from at least two disciplines
4. Include a reasoning chain: premise → mechanism → testable prediction

Output format:
L1 Hypothesis:
  hypothesis: <paragraph>
  reasoning: <step-by-step chain>
  key_concepts: <list>
  disciplines_bridged: <list>

L2 Hypotheses:
- Q1:
    hypothesis: <paragraph>
    reasoning: <chain>
    key_concepts: <list>
    disciplines_bridged: <list>
- Q2: ...

L3 Hypotheses:
- Q1:
    hypothesis: <paragraph>
    reasoning: <chain>
    key_concepts: <list>
    disciplines_bridged: <list>
- Q2: ..."""


# ---------------------------------------------------------------------------
#  P5 — Full Structured Pipeline (delegates to existing prompts)
# ---------------------------------------------------------------------------
# P5 直接复用 hypothesis_prompt_split.py 中的 SYSTEM_PROMPT_HYP_L1/L2/L3，
# 不在此处重复定义。


# ===========================================================================
#  Helper: 格式化辅助函数
# ===========================================================================

def _format_concepts_block(
    primary: str,
    concepts: Optional[Dict[str, Any]],
) -> str:
    """将概念字典格式化为可读文本块。"""
    if not concepts:
        return "(no concepts available)"

    lines: List[str] = []

    # 主学科概念
    primary_concepts = concepts.get("主学科", [])
    terms = []
    for c in primary_concepts:
        if isinstance(c, dict):
            t = c.get("normalized") or c.get("term", "")
        elif isinstance(c, ConceptEntry):
            t = c.normalized or c.term
        else:
            t = str(c)
        if t:
            terms.append(t)
    lines.append(f"- {primary} (primary): {', '.join(terms)}")

    # 辅学科概念
    secondary_concepts = concepts.get("辅学科", {})
    for disc, entries in secondary_concepts.items():
        terms = []
        for c in entries:
            if isinstance(c, dict):
                t = c.get("normalized") or c.get("term", "")
            elif isinstance(c, ConceptEntry):
                t = c.normalized or c.term
            else:
                t = str(c)
            if t:
                terms.append(t)
        lines.append(f"- {disc}: {', '.join(terms)}")

    return "\n".join(lines)


def _format_relations_block(
    relations: Optional[List[Any]],
) -> str:
    """将关系列表格式化为可读文本块。"""
    if not relations:
        return "(no relations available)"

    lines: List[str] = []
    for i, r in enumerate(relations):
        if isinstance(r, dict):
            head = r.get("head", "?")
            tail = r.get("tail", "?")
            rel = r.get("relation", "?")
            rtype = r.get("relation_type", "")
        elif isinstance(r, RelationEntry):
            head = r.head
            tail = r.tail
            rel = r.relation
            rtype = r.relation_type
        else:
            lines.append(f"  {i+1}. {r}")
            continue
        type_tag = f" ({rtype})" if rtype else ""
        lines.append(f"  {i+1}. [{head}] --({rel}{type_tag})--> [{tail}]")
    return "\n".join(lines)


def _format_query_list(queries: List[str], prefix: str = "Q") -> str:
    """格式化查询列表。"""
    if not queries:
        return "(none)"
    return "\n".join(f"  {prefix}{i+1}: {q}" for i, q in enumerate(queries))


# ===========================================================================
#  统一入口: build_messages
# ===========================================================================

def build_messages(
    level: PromptLevel,
    *,
    l1_query: str,
    l2_queries: Optional[List[str]] = None,
    l3_queries: Optional[List[str]] = None,
    abstract: str = "",
    primary: str = "",
    secondary_list: Optional[List[str]] = None,
    concepts: Optional[Dict[str, Any]] = None,
    relations: Optional[List[Any]] = None,
    # P5 专用
    struct: Optional[StructExtraction] = None,
    query_3levels: Optional[Query3Levels] = None,
) -> List[Dict[str, str]]:
    """
    根据 prompt 级别构建 messages 列表。

    Parameters
    ----------
    level : PromptLevel
        P1–P5 中的一个。
    l1_query : str
        一级查询（所有级别都需要）。
    l2_queries : list[str], optional
        二级查询列表（P2+ 需要）。
    l3_queries : list[str], optional
        三级查询列表（P3+ 需要）。
    abstract : str
        论文摘要（P2+ 需要）。
    primary : str
        主学科名称（P2+ 需要）。
    secondary_list : list[str], optional
        辅学科名称列表（P2+ 需要）。
    concepts : dict, optional
        概念字典，格式 {"主学科": [...], "辅学科": {...}}（P3+ 需要）。
    relations : list, optional
        关系列表（P4+ 需要）。
    struct : StructExtraction, optional
        完整结构化抽取结果（仅 P5）。
    query_3levels : Query3Levels, optional
        完整三级查询对象（仅 P5）。

    Returns
    -------
    list[dict]
        [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
    """
    sec_list = secondary_list or []
    sec_str = ", ".join(sec_list) if sec_list else "N/A"
    l2 = l2_queries or []
    l3 = l3_queries or []

    if level == PromptLevel.P1:
        return _build_p1(l1_query)
    elif level == PromptLevel.P2:
        return _build_p2(l1_query, l2, abstract, primary, sec_str)
    elif level == PromptLevel.P3:
        return _build_p3(l1_query, l2, l3, abstract, primary, sec_str, concepts)
    elif level == PromptLevel.P4:
        return _build_p4(l1_query, l2, l3, abstract, primary, sec_str,
                         concepts, relations)
    elif level == PromptLevel.P5:
        return _build_p5(struct, query_3levels)
    else:
        raise ValueError(f"Unknown prompt level: {level}")


# ---------------------------------------------------------------------------
#  Level-specific builders
# ---------------------------------------------------------------------------

def _build_p1(l1_query: str) -> List[Dict[str, str]]:
    user = USER_P1.format(l1_query=l1_query)
    return [
        {"role": "system", "content": SYSTEM_P1},
        {"role": "user", "content": user},
    ]


def _build_p2(
    l1_query: str,
    l2_queries: List[str],
    abstract: str,
    primary: str,
    sec_str: str,
) -> List[Dict[str, str]]:
    system = SYSTEM_P2.format(primary=primary, secondary_list=sec_str)
    l2_block = _format_query_list(l2_queries)
    user = USER_P2.format(
        abstract=abstract,
        primary=primary,
        secondary_list=sec_str,
        l1_query=l1_query,
        l2_block=l2_block,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _build_p3(
    l1_query: str,
    l2_queries: List[str],
    l3_queries: List[str],
    abstract: str,
    primary: str,
    sec_str: str,
    concepts: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    system = SYSTEM_P3.format(primary=primary, secondary_list=sec_str)
    concepts_block = _format_concepts_block(primary, concepts)
    l2_block = _format_query_list(l2_queries)
    l3_block = _format_query_list(l3_queries)
    user = USER_P3.format(
        abstract=abstract,
        primary=primary,
        secondary_list=sec_str,
        concepts_block=concepts_block,
        l1_query=l1_query,
        l2_block=l2_block,
        l3_block=l3_block,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _build_p4(
    l1_query: str,
    l2_queries: List[str],
    l3_queries: List[str],
    abstract: str,
    primary: str,
    sec_str: str,
    concepts: Optional[Dict[str, Any]],
    relations: Optional[List[Any]],
) -> List[Dict[str, str]]:
    concepts_block = _format_concepts_block(primary, concepts)
    relations_block = _format_relations_block(relations)
    l2_block = _format_query_list(l2_queries)
    l3_block = _format_query_list(l3_queries)
    user = USER_P4.format(
        abstract=abstract,
        primary=primary,
        secondary_list=sec_str,
        concepts_block=concepts_block,
        relations_block=relations_block,
        l1_query=l1_query,
        l2_block=l2_block,
        l3_block=l3_block,
    )
    return [
        {"role": "system", "content": SYSTEM_P4},
        {"role": "user", "content": user},
    ]


def _build_p5(
    struct: Optional[StructExtraction],
    query_3levels: Optional[Query3Levels],
) -> List[Dict[str, str]]:
    """P5 直接复用现有的完整结构化 prompt（返回 L1 messages）。"""
    if struct is None or query_3levels is None:
        raise ValueError(
            "P5 requires both `struct` (StructExtraction) and "
            "`query_3levels` (Query3Levels)."
        )
    from crossdisc_extractor.prompts.hypothesis_prompt_split import (
        build_hypothesis_messages_l1,
    )
    return build_hypothesis_messages_l1(struct, query_3levels)


def build_p5_all_levels(
    struct: StructExtraction,
    query_3levels: Query3Levels,
) -> Dict[str, List[Dict[str, str]]]:
    """
    P5 专用：返回三个级别各自的 messages。

    Returns
    -------
    dict
        {"L1": messages, "L2": messages, "L3": messages}
    """
    from crossdisc_extractor.prompts.hypothesis_prompt_split import (
        build_hypothesis_messages_l1,
        build_hypothesis_messages_l2,
        build_hypothesis_messages_l3,
    )
    return {
        "L1": build_hypothesis_messages_l1(struct, query_3levels),
        "L2": build_hypothesis_messages_l2(struct, query_3levels),
        "L3": build_hypothesis_messages_l3(struct, query_3levels),
    }


# ===========================================================================
#  便捷函数：从 StructExtraction 对象中自动提取参数
# ===========================================================================

def build_messages_from_extraction(
    level: PromptLevel,
    *,
    struct: StructExtraction,
    query_3levels: Query3Levels,
    abstract: str = "",
) -> List[Dict[str, str]]:
    """
    从已有的 StructExtraction + Query3Levels 中自动提取所有参数，
    按指定级别构建 messages。简化调用方代码。
    """
    meta = struct.meta
    concepts_dict = struct.概念.model_dump() if struct.概念 else {}
    relations_list = [r.model_dump() for r in (struct.跨学科关系 or [])]

    return build_messages(
        level,
        l1_query=query_3levels.一级,
        l2_queries=query_3levels.二级,
        l3_queries=query_3levels.三级,
        abstract=abstract,
        primary=meta.primary,
        secondary_list=meta.secondary_list,
        concepts=concepts_dict,
        relations=relations_list,
        struct=struct,
        query_3levels=query_3levels,
    )

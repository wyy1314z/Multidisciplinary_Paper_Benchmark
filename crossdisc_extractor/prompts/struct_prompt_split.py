# crossdisc_extractor/prompts/struct_prompt_split.py
from __future__ import annotations

import json
from typing import Dict, List, Any

from crossdisc_extractor.schemas import StructExtraction, MetaInfo, Concepts, RelationEntry
from crossdisc_extractor.utils.parsing import coerce_json_object

# ----------------------------------------------------------------------
# Step 1: Concepts Extraction (Meta + Concepts)
# ----------------------------------------------------------------------

SYSTEM_PROMPT_CONCEPTS = """你是一名跨学科信息抽取与本体对齐专家。
任务：从题目/摘要/（可选）引文片段中，按“主学科/辅助学科”抽取领域概念。

本阶段只需要输出：
- meta: {title, primary, secondary_list}
- 概念: { 主学科: ConceptEntry[], 辅学科: { 学科名: ConceptEntry[] } }

字段定义：

1) meta：
   - title: 论文标题（原文）
   - primary: 主学科
   - secondary_list: 辅学科列表（字符串数组）

2) 概念：
   - 主学科: ConceptEntry[]
   - 辅学科: { 学科名: ConceptEntry[] }
   - ConceptEntry = {
       term: string,
       normalized: string|null,
       std_label: string|null,
       evidence: string (≤40汉字/≤30英文词),
       source: "abstract" | "introduction",
       confidence: number ∈ [0,1]
     }

约束：
- 对 meta.secondary_list 中列出的每个辅学科，都要提供 3–8 个 ConceptEntry，严禁为空。
- 所有概念必须有 evidence 和 source 作为支撑，不得凭空臆测。
- 不需要抽取“跨学科关系”。

输出要求：
- 严格输出一个 JSON 对象，只包含字段：meta、概念。
- 禁止输出任何说明文字或 Markdown 代码块。
"""

USER_TEMPLATE_CONCEPTS = """输入元信息：
- title: {title}
- abstract: {abstract}
- introduction: {introduction}
- primary: {primary}
- secondary_list: [{secondary_list}]

请严格按照要求，只输出一个 JSON 对象：
{{ "meta": {{...}}, "概念": {{...}} }}。"""


def build_concepts_messages(
    title: str,
    abstract: str,
    introduction: str,
    primary: str,
    secondary_list: List[str],
) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_CONCEPTS
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("任务：从题目/摘要/（可选）引文片段中，按“主学科/辅助学科”抽取领域概念。", 
                              "任务：从题目/摘要/（可选）引文片段中，按“主学科/辅助学科”抽取领域概念。请保留原文语言，不要强制翻译。")

    user_content = USER_TEMPLATE_CONCEPTS.format(
        title=title.strip(),
        abstract=abstract.strip(),
        introduction=(introduction or "").strip(),
        primary=primary.strip() or "（未提供）",
        secondary_list=", ".join(secondary_list) if secondary_list else "（未提供）",
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def parse_concepts_output(text: str) -> Dict[str, Any]:
    obj = coerce_json_object(text)
    if not isinstance(obj, dict):
        raise ValueError("概念抽取输出不是 JSON 对象")
    # check keys
    if "meta" not in obj or "概念" not in obj:
        # 宽容模式：如果缺了 meta，可能是只输出了概念？
        # 但我们要求必须有 meta 以确认题目等信息
        # 暂时严格一点
        raise ValueError("概念抽取输出缺少必要字段 meta / 概念")
    return obj


# ----------------------------------------------------------------------
# Step 2: Relations Extraction
# ----------------------------------------------------------------------

SYSTEM_PROMPT_RELATIONS = """你是一名跨学科信息抽取与本体对齐专家。
任务：基于给定的“概念”列表和原始文本，抽取“跨学科关系”（Concept-Relation-Concept 三元组）。

输入：
1. 原始文本（Title/Abstract/Introduction）
2. 已抽取的概念列表（JSON）

本阶段只需要输出：
- 跨学科关系: RelationEntry[]

字段定义：
- RelationEntry = {
    head: string,
    tail: string,
    relation: string,        # 自然语言关系短语（用于描述 head 与 tail 的语义）
    relation_type: string,   # 枚举: ['method_applied_to','maps_to','constrains','improves_metric','corresponds_to','inferred_from','assumes','extends','generalizes','driven_by','depends_on']
    direction: "->",
    quant?: {metric, value},
    assumptions: string[],
    evidence: string,
    source: "abstract" | "introduction",
    confidence: number ∈ [0,1]
  }

约束：
- 关系的两端（head/tail）必须尽量使用“已抽取概念”中的 term 或 normalized 形式。
- 必须有 evidence 和 source 作为支撑。
- 只输出“跨学科关系”字段。

输出要求：
- 严格输出一个 JSON 对象，只包含字段：跨学科关系。
- 格式：{ "跨学科关系": [ ... ] }
- 禁止输出任何说明文字或 Markdown 代码块。
"""

USER_TEMPLATE_RELATIONS = """输入元信息：
- title: {title}
- abstract: {abstract}
- introduction: {introduction}
- primary: {primary}
- secondary_list: [{secondary_list}]

已抽取概念结构：
{concepts_json}

请基于上述信息，只输出一个 JSON 对象，包含“跨学科关系”列表：
{{ "跨学科关系": [...] }}。"""


def build_relations_messages(
    title: str,
    abstract: str,
    introduction: str,
    primary: str,
    secondary_list: List[str],
    concepts_obj: Dict[str, Any],
) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_RELATIONS
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("任务：基于给定的“概念”列表和原始文本，抽取“跨学科关系”（Concept-Relation-Concept 三元组）。", 
                              "任务：基于给定的“概念”列表和原始文本，抽取“跨学科关系”（Concept-Relation-Concept 三元组）。请保留原文语言，不要强制翻译。")

    concepts_json = json.dumps(concepts_obj, ensure_ascii=False, indent=2)
    user_content = USER_TEMPLATE_RELATIONS.format(
        title=title.strip(),
        abstract=abstract.strip(),
        introduction=(introduction or "").strip(),
        primary=primary.strip() or "（未提供）",
        secondary_list=", ".join(secondary_list) if secondary_list else "（未提供）",
        concepts_json=concepts_json,
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def parse_relations_output(text: str) -> List[Dict[str, Any]]:
    obj = coerce_json_object(text)
    if not isinstance(obj, dict):
        raise ValueError("关系抽取输出不是 JSON 对象")
    
    # 兼容：有时模型可能直接返回 list？
    # 但 prompt 要求 { "跨学科关系": [...] }
    
    if "跨学科关系" in obj:
        val = obj["跨学科关系"]
        if isinstance(val, list):
            return val
        return []
    
    # fallback
    return []

# crossdisc_extractor/prompts/struct_prompt.py
from __future__ import annotations

import json
from typing import Dict, List

from ..schemas import StructExtraction
from ..utils.parsing import coerce_json_object

SYSTEM_PROMPT_STRUCT = """你是一名跨学科信息抽取与本体对齐专家。
任务：从题目/摘要/（可选）引文片段中，按“主学科/辅助学科”抽取领域概念与跨学科三元组。

本阶段只需要输出：
- meta: {title, primary, secondary_list}
- 概念: { 主学科: ConceptEntry[], 辅学科: { 学科名: ConceptEntry[] } }
- 跨学科关系: RelationEntry[]

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
       source: "abstract" | "refs[i]",
       confidence: number ∈ [0,1]
     }

3) 跨学科关系：
   - RelationEntry = {
       head: string,
       tail: string,
       relation: string,        # 自然语言关系短语（用于描述 head 与 tail 的语义）
       relation_type: string,   # 从给定枚举中选一项：['method_applied_to','maps_to','constrains','improves_metric','corresponds_to','inferred_from','assumes','extends','generalizes','driven_by','depends_on']
       direction: "->",
       quant?: {metric, value},
       assumptions: string[],
       evidence: string,
       source: "abstract" | "refs[i]",
       confidence: number ∈ [0,1]
     }

约束：
- 对 meta.secondary_list 中列出的每个辅学科，都要提供 3–8 个 ConceptEntry，严禁为空。
- 所有概念和关系必须有 evidence 和 source 作为支撑，不得凭空臆测。
- 本阶段不需要生成“按辅助学科分类”“查询”“假设”。

输出要求：
- 严格输出一个 JSON 对象，只包含字段：meta、概念、跨学科关系。
- 禁止输出任何说明文字或 Markdown 代码块。
"""

USER_TEMPLATE_STRUCT = """输入元信息：
- title: {title}
- abstract: {abstract}
- introduction: {introduction}
- primary: {primary}
- secondary_list: [{secondary_list}]

请严格按照要求，只输出一个 JSON 对象：
{{ "meta": {{...}}, "概念": {{...}}, "跨学科关系": [...] }}。"""


def build_struct_messages(
    title: str,
    abstract: str,
    introduction: str,
    primary: str,
    secondary_list: List[str],
) -> List[Dict[str, str]]:
    user_content = USER_TEMPLATE_STRUCT.format(
        title=title.strip(),
        abstract=abstract.strip(),
        introduction=(introduction or "").strip(),
        primary=primary.strip() or "（未提供）",
        secondary_list=", ".join(secondary_list) if secondary_list else "（未提供）",
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT_STRUCT},
        {"role": "user", "content": user_content},
    ]


def parse_struct_output(text: str) -> StructExtraction:
    obj = coerce_json_object(text)
    if not isinstance(obj, dict):
        raise ValueError("结构抽取输出不是 JSON 对象")
    if not {"meta", "概念", "跨学科关系"}.issubset(obj.keys()):
        raise ValueError("结构抽取输出缺少必要字段 meta / 概念 / 跨学科关系")
    return StructExtraction.model_validate(obj)

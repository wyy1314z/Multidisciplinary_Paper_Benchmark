"""
crossdisc_extractor/benchmark/gt_prompts.py

Prompts for evidence-grounded GT construction.

Stage 1: Constrained terminology extraction (with evidence sentences)
Stage 2: Relation classification (given two terms + evidence sentence)
"""

from __future__ import annotations

# ===========================================================================
#  Stage 1: Constrained Terminology Extraction
# ===========================================================================

PROMPT_TERM_EXTRACTION = """你是一位跨学科文献分析专家。请从以下论文的摘要和引言中提取所有专业术语或专有名词。

【约束条件】
1. 只提取在特定学科中有明确定义的专业术语（如"脑深部刺激""beta振荡""有限元分析"），不提取通用学术词汇（如"方法""结论""假设""研究""分析"）
2. 每个术语标注其所属学科领域
3. 对于每个术语，给出论文原文中包含该术语的一句话作为 evidence（必须是原文中的句子）
4. 提取的术语应覆盖论文涉及的所有学科领域
5. 每个学科至少提取 2 个术语，每个学科最多 8 个术语

【论文标题】
{title}

【摘要】
{abstract}

【引言】
{introduction}

【输出格式】
请输出一个 JSON 对象，包含以下字段：
{{
    "terms": [
        {{
            "term": "<专业术语原文>",
            "normalized": "<术语的标准化名称（去除修饰词，保留核心概念）>",
            "discipline": "<所属学科领域>",
            "evidence": "<包含该术语的原文句子>",
            "source": "<来源：abstract 或 introduction>",
            "confidence": <0.0-1.0 的置信度>
        }}
    ]
}}
只输出 JSON，不要输出其他内容。
"""


# ===========================================================================
#  Stage 2: Evidence-Based Relation Classification
# ===========================================================================

PROMPT_RELATION_CLASSIFICATION = """你是一位学术关系抽取专家。请根据以下论文原文句子，判断两个术语之间是否存在直接关系。

【论文原文句子】
"{evidence_sentence}"

【术语1】{term_a}（学科：{disc_a}）
【术语2】{term_b}（学科：{disc_b}）

【任务】
1. 判断上述句子是否直接表达了这两个术语之间的关系
2. 如果存在关系，从以下预定义关系类型中选择最匹配的一个：
   - method_applied_to: A被应用于B / A是B的方法
   - maps_to: A映射到B / A对应B
   - constrains: A约束/限制B
   - improves_metric: A提升/改善B
   - corresponds_to: A与B相关联/对应
   - inferred_from: A由B推断/导出
   - assumes: A以B为前提
   - extends: A扩展/延伸B
   - generalizes: A泛化/推广B
   - driven_by: A由B驱动/引起
   - depends_on: A依赖于B
   - other: 其他关系（请在 relation_detail 中说明）
   - none: 该句子不支持这两个术语之间存在直接关系

3. 指明关系方向：term_a → term_b 还是 term_b → term_a

【输出格式】
{{
    "has_relation": <true/false>,
    "relation_type": "<关系类型>",
    "relation_detail": "<用自然语言描述具体关系>",
    "direction": "<term_a_to_term_b 或 term_b_to_term_a>",
    "confidence": <0.0-1.0>
}}
只输出 JSON，不要输出其他内容。
"""


# ===========================================================================
#  Stage 2b: Batch Relation Extraction from Sentence
# ===========================================================================

PROMPT_RELATION_BATCH = """你是一位学术关系抽取专家。请从以下论文原文句子中，识别句中出现的专业术语之间的关系。

【论文原文句子】
"{sentence}"

【已知术语列表】
{term_list}

【任务】
1. 识别句子中出现了哪些术语（允许部分匹配和同义词）
2. 对于句中共现的每一对术语，判断它们之间是否存在直接关系
3. 关系类型限定为：method_applied_to, maps_to, constrains, improves_metric, corresponds_to, inferred_from, assumes, extends, generalizes, driven_by, depends_on, other

【输出格式】
{{
    "found_terms": ["<在句中出现的术语>"],
    "relations": [
        {{
            "head": "<起始术语>",
            "tail": "<目标术语>",
            "relation_type": "<关系类型>",
            "relation_detail": "<关系的自然语言描述>",
            "confidence": <0.0-1.0>
        }}
    ]
}}
如果句中没有两个以上术语共现，或者没有明确关系，则 relations 为空列表。
只输出 JSON，不要输出其他内容。
"""

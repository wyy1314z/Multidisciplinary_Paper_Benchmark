# crossdisc_extractor/prompts/struct_prompt_split.py
from __future__ import annotations

import json
from typing import Dict, List, Any

from crossdisc_extractor.schemas import StructExtraction, MetaInfo, Concepts, RelationEntry
from crossdisc_extractor.utils.parsing import coerce_json_object

# ----------------------------------------------------------------------
# Step 1: Concepts Extraction (Meta + Concepts)
# ----------------------------------------------------------------------

SYSTEM_PROMPT_CONCEPTS = """\
你是一名跨学科信息抽取与本体对齐专家。
任务：从题目/摘要/（可选）引言中，按"主学科/辅助学科"**尽可能广泛、全面**地抽取专业术语和专有名词。
本阶段抽取的概念将直接作为后续"假设生成"和"知识图谱构建"的节点词表——
如果某个术语在本阶段未被抽取，后续环节将无法使用它。因此，宁可多抽不可漏抽。

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

【概念定义——什么是合格的概念（必须满足）】
概念必须是论文原文中实际出现的具体专业术语或专有名词，包括但不限于：
✓ 具体方法/技术：如 "deep brain stimulation", "CRISPR-Cas9"
✓ 具体物质/结构/器官：如 "centromedian nucleus", "ionic liquid"
✓ 具体现象/指标/度量：如 "cortical delta power", "phase transition"
✓ 具体模型/算法/框架：如 "Jensen-Shannon distance", "random forest"
✓ 专有缩写及其全称：如 "EEG (electroencephalogram)", "FGFR"
✓ 具体疾病/症状：如 "drug-resistant epilepsy", "pediatric glioma"
✓ 具体实验操作：如 "intraoperative recording"
✓ 研究对象/样本：如 "wastewater", "recalcitrant pollutants"
✓ 性能/属性/效果词：如 "catalytic selectivity", "thermal stability", "contaminant degradation"
✓ 具体产物/中间体：如 "sulfate radicals", "reactive oxygen species"
✓ 装置/器件/系统：如 "anion exchange membrane", "gas diffusion layer"
✓ 关键过程/机制：如 "electron transfer", "charge separation"

以下不是概念，严禁抽取：
✗ 学科名称：如 "Neurology", "Electronic engineering", "Biology"
✗ 纯通用动词/描述词：如 "analysis", "method", "approach"（但"impedance analysis"是合格的）
✗ 机构名/人名/地名/期刊名
✗ 论文结构性用语：如 "our study", "these findings"
✗ 评价性/修饰性用语：如 "significant", "novel", "important"

【原文忠实性（必须满足）】
- term 字段必须是论文原文中实际出现的词语或短语，直接从原文复制，不得改写或概括
- normalized 字段可以是标准化/翻译形式，但必须与 term 语义一致
- 如果原文是英文，term 应保留英文原文；normalized 提供中文翻译或标准化形式

【覆盖率要求（必须满足——这是最关键的要求）】
- 主学科：**至少 10-25 个** ConceptEntry，覆盖论文中出现的所有专业术语
- 每个辅学科：**至少 5-12 个** ConceptEntry，严禁为空
- 抽取策略：
  1. 逐句扫描 abstract，提取每个句子中的所有专业术语
  2. 逐句扫描 introduction（如果提供），提取每个句子中的所有专业术语
  3. 特别关注 introduction 中背景综述部分提到的已有方法、材料、现象
  4. 回顾检查：扫描完成后，重新审视是否有遗漏的关键术语
- 特别注意容易遗漏但极有价值的术语：
  * 化学物质/材料名（如 ionic liquid, ZnO nanoparticles）
  * 性能指标/评估标准（如 Faradaic efficiency, overpotential）
  * 实验条件/环境（如 acidic conditions, complex water matrices）
  * 应用场景/目标（如 contaminant degradation, energy conversion）
- 如果一个专业术语在论文中出现 2 次以上，必须被抽取
- 宁多勿少：如果不确定某个术语是否属于某个学科，倾向于抽取它

约束：
- 所有概念必须有 evidence 和 source 作为支撑，不得凭空臆测。
- evidence 必须是原文中包含该术语的原句或原句片段，不得改写。
- 不需要抽取"跨学科关系"。

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
        prompt = prompt.replace("任务：从题目/摘要/（可选）引言中，按“主学科/辅助学科”**尽可能广泛、全面**地抽取专业术语和专有名词。", 
                              "任务：从题目/摘要/（可选）引言中，按“主学科/辅助学科”**尽可能广泛、全面**地抽取专业术语和专有名词。请保留原文语言，不要强制翻译。")

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
    concepts = obj.get("概念")
    if isinstance(concepts, dict):
        concepts.setdefault("主学科", [])
        concepts.setdefault("辅学科", {})
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


def parse_relations_output(text: str, original_text: str = "") -> List[Dict[str, Any]]:
    obj = coerce_json_object(text)
    if not isinstance(obj, dict):
        raise ValueError("关系抽取输出不是 JSON 对象")
    
    # 兼容：有时模型可能直接返回 list？
    # 但 prompt 要求 { "跨学科关系": [...] }
    
    if "跨学科关系" in obj:
        val = obj["跨学科关系"]
        if isinstance(val, list):
            out = []
            for item in val:
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                item["direction"] = "->"
                if item.get("evidence") is None:
                    item["evidence"] = ""
                if item.get("source") in (None, ""):
                    item["source"] = "abstract"
                if item.get("assumptions") is None:
                    item["assumptions"] = []
                out.append(item)
            return out
        return []
    
    # fallback
    return []

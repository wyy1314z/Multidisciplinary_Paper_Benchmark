# # crossdisc_extractor/prompts/query_prompt.py
# from __future__ import annotations

# import json
# import logging
# import re
# from typing import Dict, List, Optional, Tuple

# from ..schemas import StructExtraction, QueryAndBuckets, Query3Levels
# from ..utils.parsing import coerce_json_object

# logger = logging.getLogger("crossdisc.query_prompt")

# _LATIN_RE = re.compile(r"[A-Za-z]")
# _LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\/\.]*")


# def _has_latin_letters(s: str) -> bool:
#     return bool(_LATIN_RE.search(s or ""))


# def _query_has_latin(q: Query3Levels) -> bool:
#     if _has_latin_letters((q.一级 or "").strip()):
#         return True
#     for s in (q.二级 or []):
#         if _has_latin_letters((s or "").strip()):
#             return True
#     for s in (q.三级 or []):
#         if _has_latin_letters((s or "").strip()):
#             return True
#     return False


# def _build_term_replacements_from_struct(struct: StructExtraction) -> List[Tuple[str, str]]:
#     """
#     从结构化抽取结果中构建“英文术语 -> 中文归一化术语”的替换表（尽力而为）。
#     只用于修复“查询”中夹杂的英文术语。
#     """
#     reps: List[Tuple[str, str]] = []

#     def add_pair(term: str, normalized: str):
#         term = (term or "").strip()
#         normalized = (normalized or "").strip()
#         if not term or not normalized:
#             return
#         # 只收集“term 含英文、normalized 不含英文”的映射，避免把中文改坏
#         if _has_latin_letters(term) and (not _has_latin_letters(normalized)):
#             reps.append((term, normalized))

#     # 概念：主学科 + 辅学科
#     concepts = struct.概念
#     for e in (concepts.主学科 or []):
#         add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")
#     for _, lst in (concepts.辅学科 or {}).items():
#         for e in (lst or []):
#             add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")

#     # 关系：head/tail 有时也包含英文且概念中已有中文归一化（这里做弱补充）
#     for r in (struct.跨学科关系 or []):
#         # 这里没有“对应中文”的字段，只能跳过；避免错误替换
#         _ = r

#     # 去重（保序，且优先长词先替换）
#     seen = set()
#     uniq: List[Tuple[str, str]] = []
#     for a, b in reps:
#         key = (a.lower(), b)
#         if key not in seen:
#             seen.add(key)
#             uniq.append((a, b))

#     # 长的先替换，避免子串先被替换导致失配
#     uniq.sort(key=lambda x: len(x[0]), reverse=True)
#     return uniq


# def _apply_replacements(text: str, reps: List[Tuple[str, str]]) -> str:
#     s = text or ""
#     for src, tgt in reps:
#         # 允许大小写差异匹配
#         s = re.sub(re.escape(src), tgt, s, flags=re.IGNORECASE)
#     return s


# def _strip_remaining_latin_tokens(text: str) -> str:
#     """
#     将剩余的英文 token 去掉，保证最终“查询”不含拉丁字母。
#     注意：这是兜底策略，尽量不触发；触发时会尽可能保留中文语境。
#     """
#     s = text or ""
#     s = _LATIN_TOKEN_RE.sub("", s)
#     # 清理多余空格与标点空洞
#     s = re.sub(r"\s{2,}", " ", s).strip()
#     s = re.sub(r"[（）\(\)]\s*[（）\(\)]", " ", s)  # 连续空括号
#     s = re.sub(r"\s{2,}", " ", s).strip()
#     return s


# def _fallback_fill_query_in_chinese(q: Query3Levels, struct: Optional[StructExtraction]) -> Query3Levels:
#     """
#     若兜底清洗后出现空字符串，使用中文占位问题填充，避免后续流程崩溃。
#     """
#     if struct is None:
#         primary = "主学科"
#         sec_list: List[str] = []
#     else:
#         primary = (struct.meta.primary or "主学科").strip() or "主学科"
#         sec_list = [s.strip() for s in (struct.meta.secondary_list or []) if s.strip()]

#     if not (q.一级 or "").strip():
#         q.一级 = f"如何在{primary}研究中提升关键问题的解决效果？"

#     # 二级：尽量按辅学科数量填充缺口，但不强制改长度（避免改变模型生成结构）
#     for i in range(len(q.二级 or [])):
#         if not (q.二级[i] or "").strip():
#             sec = sec_list[i] if i < len(sec_list) else "相关辅学科"
#             q.二级[i] = f"{sec}如何支持{primary}问题的机制刻画与方法优化？"

#     # 三级：给更工作流化的占位
#     for i in range(len(q.三级 or [])):
#         if not (q.三级[i] or "").strip():
#             q.三级[i] = f"如何整合多学科方法形成可验证的工作流以改进{primary}的核心目标？"

#     return q


# def ensure_query_chinese(
#     q: Query3Levels,
#     struct: Optional[StructExtraction] = None,
# ) -> Query3Levels:
#     """
#     当“查询”中出现英文时：
#     1) 若提供 struct，则优先用“英文术语->中文归一化术语”映射替换；
#     2) 再兜底移除剩余英文 token，保证最终不含拉丁字母；
#     3) 若出现空字符串，再用中文占位问题填充。
#     全过程不抛错，只记录 warning，确保不会因为英文导致整条记录失败。
#     """
#     if not _query_has_latin(q):
#         return q

#     reps: List[Tuple[str, str]] = []
#     if struct is not None:
#         try:
#             reps = _build_term_replacements_from_struct(struct)
#         except Exception as e:
#             logger.warning("构建术语替换表失败，将直接移除英文 token：%s", e)
#             reps = []

#     def fix_one(s: str) -> str:
#         s2 = _apply_replacements(s, reps) if reps else (s or "")
#         if _has_latin_letters(s2):
#             s2 = _strip_remaining_latin_tokens(s2)
#         return s2

#     q.一级 = fix_one(q.一级 or "")
#     q.二级 = [fix_one(x or "") for x in (q.二级 or [])]
#     q.三级 = [fix_one(x or "") for x in (q.三级 or [])]

#     # 若仍含英文（理论上不应发生），再强制剥离一次
#     if _query_has_latin(q):
#         q.一级 = _strip_remaining_latin_tokens(q.一级 or "")
#         q.二级 = [_strip_remaining_latin_tokens(x or "") for x in (q.二级 or [])]
#         q.三级 = [_strip_remaining_latin_tokens(x or "") for x in (q.三级 or [])]

#     q = _fallback_fill_query_in_chinese(q, struct)

#     logger.warning("检测到查询中含英文，已自动清洗为中文（不再报错）。")
#     return q


# SYSTEM_PROMPT_QUERY = """你是一名跨学科知识组织与问题设计专家。
# 任务：在给定的“结构化抽取结果”基础上，完成两件事：

# 【语言要求（必须满足，仅约束“查询”）】
# - 你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。
# - 如果输入中包含英文术语，你必须在“查询”中使用中文翻译表达，不得保留英文原词或缩写。
# -（注意：“按辅助学科分类”的概念术语可保留原始形式，不作中文硬约束。）

# 1) 按辅助学科分类（按辅助学科分类）：
#    - 输出一个字典：{ 学科名: { 概念: [string], 关系: [int], rationale: string } }
#    - 概念: 本学科在本论文中的关键术语（通常来自 ConceptEntry.normalized 或 term）；
#    - 关系: 引用 跨学科关系 数组中的下标（0-based），表示与该学科高度相关的三元组；
#    - rationale: 一句话，说明该学科在论文中的功能分工、贡献或者作用。

# 2) 生成三级查询（Query3Levels）：
#    - 查询 = {
#        "一级": string,
#        "二级": [string],
#        "三级": [string]
#      }

#    学科约束：
#    - 一级：只从主学科视角提出总体问题，不显式点名辅学科；
#    - 二级：在一级基础上引入 1–2 个辅学科或工具，但不强调学科间关系；
#    - 三级：在二级基础上，显式写出多学科如何协同形成工作流或机制验证方案。

# 输出要求：
# - 严格输出一个 JSON 对象，只包含字段：
#   - "按辅助学科分类": { ... }
#   - "查询": { "一级": ..., "二级": [...], "三级": [...] }
# - 禁止输出任何说明文字或 Markdown 代码块。
# """

# USER_TEMPLATE_QUERY = """已抽取的结构化结果如下：
# {struct_json}

# 请基于上述结果：
# 1) 构建“按辅助学科分类”视图；
# 2) 生成三级查询结构 Query3Levels。

# 注意：你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何拉丁字母（A-Z/a-z）。

# 只输出一个 JSON 对象：{{ "按辅助学科分类": {{...}}, "查询": {{...}} }}。"""


# def build_query_messages(struct: StructExtraction) -> List[Dict[str, str]]:
#     struct_json = struct.model_dump(mode="json")
#     struct_text = json.dumps(struct_json, ensure_ascii=False, indent=2)
#     user_content = USER_TEMPLATE_QUERY.format(struct_json=struct_text)
#     return [
#         {"role": "system", "content": SYSTEM_PROMPT_QUERY},
#         {"role": "user", "content": user_content},
#     ]


# def _coerce_obj(text: str):
#     """
#     兼容你本地 parsing.coerce_json_object 是否支持 required_top_keys 参数的两种实现。
#     """
#     try:
#         return coerce_json_object(text, required_top_keys={"按辅助学科分类", "查询"})  # type: ignore[arg-type]
#     except TypeError:
#         return coerce_json_object(text)


# def parse_query_output(text: str, struct: Optional[StructExtraction] = None) -> QueryAndBuckets:
#     """
#     重要变化：
#     - 不再因为“查询中含英文”而抛错导致整条记录失败；
#     - 发现英文时会自动清洗/替换并返回修复后的 QueryAndBuckets。
#     """
#     obj = _coerce_obj(text)
#     if not isinstance(obj, dict):
#         raise ValueError("查询生成输出不是 JSON 对象")
#     if not {"按辅助学科分类", "查询"}.issubset(obj.keys()):
#         raise ValueError("查询生成输出缺少字段 按辅助学科分类 / 查询")

#     parsed = QueryAndBuckets.model_validate(obj)

#     # 自动修复“查询必须中文”：不报错，不失败
#     parsed.查询 = ensure_query_chinese(parsed.查询, struct=struct)

#     return parsed



# crossdisc_extractor/prompts/query_prompt.py
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from crossdisc_extractor.schemas import StructExtraction, QueryAndBuckets, Query3Levels
from crossdisc_extractor.utils.parsing import coerce_json_object

logger = logging.getLogger("crossdisc.query_prompt")

_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\/\.]*")


def _has_latin_letters(s: str) -> bool:
    return bool(_LATIN_RE.search(s or ""))


def _query_has_latin(q: Query3Levels) -> bool:
    if _has_latin_letters((q.一级 or "").strip()):
        return True
    for s in (q.二级 or []):
        if _has_latin_letters((s or "").strip()):
            return True
    for s in (q.三级 or []):
        if _has_latin_letters((s or "").strip()):
            return True
    return False


def _build_term_replacements_from_struct(struct: StructExtraction) -> List[Tuple[str, str]]:
    """
    从结构化抽取结果中构建“英文术语 -> 中文归一化术语”的替换表（尽力而为）。
    只用于修复“查询”中夹杂的英文术语。
    """
    reps: List[Tuple[str, str]] = []

    def add_pair(term: str, normalized: str):
        term = (term or "").strip()
        normalized = (normalized or "").strip()
        if not term or not normalized:
            return
        # 只收集“term 含英文、normalized 不含英文”的映射，避免把中文改坏
        if _has_latin_letters(term) and (not _has_latin_letters(normalized)):
            reps.append((term, normalized))

    # 概念：主学科 + 辅学科
    concepts = struct.概念
    for e in (concepts.主学科 or []):
        add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")
    for _, lst in (concepts.辅学科 or {}).items():
        for e in (lst or []):
            add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")

    # 关系：head/tail 有时也包含英文且概念中已有中文归一化（这里做弱补充）
    for r in (struct.跨学科关系 or []):
        # 这里没有“对应中文”的字段，只能跳过；避免错误替换
        _ = r

    # 去重（保序，且优先长词先替换）
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for a, b in reps:
        key = (a.lower(), b)
        if key not in seen:
            seen.add(key)
            uniq.append((a, b))

    # 长的先替换，避免子串先被替换导致失配
    uniq.sort(key=lambda x: len(x[0]), reverse=True)
    return uniq


def _apply_replacements(text: str, reps: List[Tuple[str, str]]) -> str:
    s = text or ""
    for src, tgt in reps:
        # 允许大小写差异匹配
        s = re.sub(re.escape(src), tgt, s, flags=re.IGNORECASE)
    return s


def _strip_remaining_latin_tokens(text: str) -> str:
    """
    将剩余的英文 token 去掉，保证最终“查询”不含拉丁字母。
    注意：这是兜底策略，尽量不触发；触发时会尽可能保留中文语境。
    """
    s = text or ""
    s = _LATIN_TOKEN_RE.sub("", s)
    # 清理多余空格与标点空洞
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"[（）\(\)]\s*[（）\(\)]", " ", s)  # 连续空括号
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _fallback_fill_query_in_chinese(q: Query3Levels, struct: Optional[StructExtraction]) -> Query3Levels:
    """
    若兜底清洗后出现空字符串，使用中文占位问题填充，避免后续流程崩溃。
    """
    if struct is None:
        primary = "主学科"
        sec_list: List[str] = []
    else:
        primary = (struct.meta.primary or "主学科").strip() or "主学科"
        sec_list = [s.strip() for s in (struct.meta.secondary_list or []) if s.strip()]

    if not (q.一级 or "").strip():
        q.一级 = f"如何在{primary}研究中提升关键问题的解决效果？"

    # 二级：尽量按辅学科数量填充缺口，但不强制改长度（避免改变模型生成结构）
    for i in range(len(q.二级 or [])):
        if not (q.二级[i] or "").strip():
            sec = sec_list[i] if i < len(sec_list) else "相关辅学科"
            q.二级[i] = f"{sec}如何支持{primary}问题的机制刻画与方法优化？"

    # 三级：给更工作流化的占位
    for i in range(len(q.三级 or [])):
        if not (q.三级[i] or "").strip():
            q.三级[i] = f"如何整合多学科方法形成可验证的工作流以改进{primary}的核心目标？"

    return q


def ensure_query_chinese(
    q: Query3Levels,
    struct: Optional[StructExtraction] = None,
) -> Query3Levels:
    """
    当“查询”中出现英文时：
    1) 若提供 struct，则优先用“英文术语->中文归一化术语”映射替换；
    2) 再兜底移除剩余英文 token，保证最终不含拉丁字母；
    3) 若出现空字符串，再用中文占位问题填充。
    全过程不抛错，只记录 warning，确保不会因为英文导致整条记录失败。
    """
    if not _query_has_latin(q):
        return q

    reps: List[Tuple[str, str]] = []
    if struct is not None:
        try:
            reps = _build_term_replacements_from_struct(struct)
        except Exception as e:
            logger.warning("构建术语替换表失败，将直接移除英文 token：%s", e)
            reps = []

    def fix_one(s: str) -> str:
        s2 = _apply_replacements(s, reps) if reps else (s or "")
        if _has_latin_letters(s2):
            s2 = _strip_remaining_latin_tokens(s2)
        return s2

    q.一级 = fix_one(q.一级 or "")
    q.二级 = [fix_one(x or "") for x in (q.二级 or [])]
    q.三级 = [fix_one(x or "") for x in (q.三级 or [])]

    # 若仍含英文（理论上不应发生），再强制剥离一次
    if _query_has_latin(q):
        q.一级 = _strip_remaining_latin_tokens(q.一级 or "")
        q.二级 = [_strip_remaining_latin_tokens(x or "") for x in (q.二级 or [])]
        q.三级 = [_strip_remaining_latin_tokens(x or "") for x in (q.三级 or [])]

    q = _fallback_fill_query_in_chinese(q, struct)

    logger.warning("检测到查询中含英文，已自动清洗为中文（不再报错）。")
    return q


SYSTEM_PROMPT_QUERY = """你是一名跨学科知识组织与问题设计专家。
任务：在给定的“结构化抽取结果”基础上，完成两件事：

【语言要求（必须满足，仅约束“查询”）】
- 你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。
- 如果输入中包含英文术语，你必须在“查询”中使用中文翻译表达，不得保留英文原词或缩写。
-（注意：“按辅助学科分类”的概念术语可保留原始形式，不作中文硬约束。）

1) 按辅助学科分类（按辅助学科分类）：
   - 输出一个字典：{ 学科名: { 概念: [string], 关系: [int], rationale: string } }
   - 概念: 本学科在本论文中的关键术语（通常来自 ConceptEntry.normalized 或 term）；
   - 关系: 引用 跨学科关系 数组中的下标（0-based），表示与该学科高度相关的三元组；
   - rationale: 一句话，说明该学科在论文中的功能分工、贡献或者作用。

2) 生成三级查询（Query3Levels）：
   - 查询 = {
       "一级": string,
       "二级": [string],
       "三级": [string]
     }

   学科约束：
   - 一级：只从主学科视角提出总体问题，不显式点名辅学科；
   - 二级：在一级基础上引入 1–2 个辅学科或工具，但不强调学科间关系；
   - 三级：在二级基础上，显式写出多学科如何协同形成工作流或机制验证方案。

输出要求：
- 严格输出一个 JSON 对象，只包含字段：
  - "按辅助学科分类": { ... }
  - "查询": { "一级": ..., "二级": [...], "三级": [...] }
- 禁止输出任何说明文字或 Markdown 代码块。
"""

USER_TEMPLATE_QUERY = """已抽取的结构化结果如下：
{struct_json}

请基于上述结果：
1) 构建“按辅助学科分类”视图；
2) 生成三级查询结构 Query3Levels。

注意：你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何拉丁字母（A-Z/a-z）。

只输出一个 JSON 对象：{{ "按辅助学科分类": {{...}}, "查询": {{...}} }}。"""


def build_query_messages(struct: StructExtraction) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_QUERY
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("【语言要求（必须满足，仅约束“查询”）】", "【语言要求】")
        prompt = prompt.replace("- 你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。", 
                              "- 请保留原文语言，不要强制翻译。")
        prompt = prompt.replace("- 如果输入中包含英文术语，你必须在“查询”中使用中文翻译表达，不得保留英文原词或缩写。", "")
        prompt = prompt.replace("注意：你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何拉丁字母（A-Z/a-z）。", "")
        
    struct_json = struct.model_dump(mode="json")
    struct_text = json.dumps(struct_json, ensure_ascii=False, indent=2)
    user_content = USER_TEMPLATE_QUERY.format(struct_json=struct_text)
    
    if get_language_mode() == LanguageMode.ORIGINAL:
        user_content = user_content.replace("注意：你输出的“查询”字段中的所有字符串必须为中文，禁止出现任何拉丁字母（A-Z/a-z）。", "")

    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def _coerce_obj(text: str):
    """
    兼容你本地 parsing.coerce_json_object 是否支持 required_top_keys 参数的两种实现。
    """
    try:
        return coerce_json_object(text, required_top_keys={"按辅助学科分类", "查询"})  # type: ignore[arg-type]
    except TypeError:
        return coerce_json_object(text)


def parse_query_output(text: str, struct: Optional[StructExtraction] = None) -> QueryAndBuckets:
    """
    重要变化：
    - 不再因为“查询中含英文”而抛错导致整条记录失败；
    - 发现英文时会自动清洗/替换并返回修复后的 QueryAndBuckets。
    """
    obj = _coerce_obj(text)
    if not isinstance(obj, dict):
        raise ValueError("查询生成输出不是 JSON 对象")
    if not {"按辅助学科分类", "查询"}.issubset(obj.keys()):
        raise ValueError("查询生成输出缺少字段 按辅助学科分类 / 查询")

    parsed = QueryAndBuckets.model_validate(obj)

    # 自动修复“查询必须中文”：不报错，不失败
    parsed.查询 = ensure_query_chinese(parsed.查询, struct=struct)

    return parsed


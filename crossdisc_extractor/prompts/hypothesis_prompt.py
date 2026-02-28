# # crossdisc_extractor/prompts/hypothesis_prompt.py
# from __future__ import annotations

# import json
# import logging
# import re
# from typing import Dict, List, Optional, Tuple

# from ..schemas import StructExtraction, Query3Levels, Hypothesis3Levels, HypothesisStep
# from ..utils.summarize import build_struct_summary_json
# from ..utils.parsing import coerce_json_object, ensure_hypothesis_summaries

# logger = logging.getLogger("crossdisc.hypothesis_prompt")

# _LATIN_RE = re.compile(r"[A-Za-z]")
# _LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\/\.]*")


# def _has_latin_letters(s: str) -> bool:
#     return bool(_LATIN_RE.search(s or ""))


# # ----------------------------
# # 术语替换：尽量把英文术语替换成结构化抽取里已有的中文 normalized
# # ----------------------------
# def _build_term_replacements_from_struct(struct: Optional[StructExtraction]) -> List[Tuple[str, str]]:
#     """
#     构建“英文术语 -> 中文归一化术语”的替换表（尽力而为）。
#     只用于清洗“假设”里的英文残留，避免简单粗暴删除导致语义损失。
#     """
#     if struct is None:
#         return []

#     reps: List[Tuple[str, str]] = []

#     def add_pair(term: str, normalized: str):
#         term = (term or "").strip()
#         normalized = (normalized or "").strip()
#         if not term or not normalized:
#             return
#         # 只收集：term 含英文、normalized 不含英文 的映射
#         if _has_latin_letters(term) and (not _has_latin_letters(normalized)):
#             reps.append((term, normalized))

#     # 概念：主学科 + 辅学科
#     concepts = struct.概念
#     for e in (concepts.主学科 or []):
#         add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")
#     for _, lst in (concepts.辅学科 or {}).items():
#         for e in (lst or []):
#             add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")

#     # 去重（保序）+ 长词优先替换
#     seen = set()
#     uniq: List[Tuple[str, str]] = []
#     for a, b in reps:
#         key = (a.lower(), b)
#         if key not in seen:
#             seen.add(key)
#             uniq.append((a, b))
#     uniq.sort(key=lambda x: len(x[0]), reverse=True)
#     return uniq


# def _apply_replacements(text: str, reps: List[Tuple[str, str]]) -> str:
#     s = text or ""
#     for src, tgt in reps:
#         s = re.sub(re.escape(src), tgt, s, flags=re.IGNORECASE)
#     return s


# def _strip_remaining_latin_tokens(text: str) -> str:
#     """
#     兜底：移除仍残留的英文 token，确保最终“假设”不含拉丁字母。
#     """
#     s = text or ""
#     s = _LATIN_TOKEN_RE.sub("", s)
#     s = re.sub(r"\s{2,}", " ", s).strip()
#     # 清理一些英文 token 删除后留下的空括号/多余符号
#     s = re.sub(r"[（）\(\)]\s*[）\)]", "）", s)
#     s = re.sub(r"[\(（]\s*[\)）]", "", s)
#     s = re.sub(r"\s{2,}", " ", s).strip()
#     return s


# # ----------------------------
# # 查询中文要求：不再报错；若含英文，做轻量清洗后继续
# # ----------------------------
# def _ensure_chinese_query_inplace(query: Query3Levels) -> Query3Levels:
#     """
#     build_hypothesis_messages 阶段的兜底：
#     - 查询理论上已在“查询阶段”被强制清洗为中文；
#     - 若仍含英文，这里不再抛错导致整条记录失败，而是轻量清洗后继续。
#     """
#     def fix_one(s: str) -> str:
#         s = (s or "").strip()
#         if not s:
#             return s
#         if _has_latin_letters(s):
#             s = _strip_remaining_latin_tokens(s)
#         return s

#     query.一级 = fix_one(query.一级 or "")
#     query.二级 = [fix_one(x or "") for x in (query.二级 or [])]
#     query.三级 = [fix_one(x or "") for x in (query.三级 or [])]
#     return query


# # ----------------------------
# # 假设中文清洗：发现英文则修复并返回，不抛错
# # ----------------------------
# def _fix_step_text(
#     s: str,
#     reps: List[Tuple[str, str]],
# ) -> str:
#     s2 = _apply_replacements(s or "", reps) if reps else (s or "")
#     if _has_latin_letters(s2):
#         s2 = _strip_remaining_latin_tokens(s2)
#     return (s2 or "").strip()


# def _fallback_fill_path_3steps(path: List[HypothesisStep]) -> List[HypothesisStep]:
#     """
#     保守兜底（一般不触发）：若清洗导致关键字段为空，填充最小中文占位，尽量保持链式一致性。
#     注意：这里不引入具体论文新事实，只提供结构性占位，避免后续崩溃。
#     """
#     # 期望 path 已经是 3 steps（你的 schema 若已硬约束，这里主要用于“字段为空”的兜底）
#     if not path or len(path) != 3:
#         return path

#     s1, s2, s3 = path[0], path[1], path[2]

#     # step1
#     if not (s1.head or "").strip():
#         s1.head = "关键前提"
#     if not (s1.relation or "").strip():
#         s1.relation = "影响"
#     if not (s1.tail or "").strip():
#         s1.tail = "关键中介"

#     # chain
#     s2.head = (s1.tail or "").strip() or "关键中介"

#     # step2
#     if not (s2.relation or "").strip():
#         s2.relation = "导致"
#     if not (s2.tail or "").strip():
#         s2.tail = "关键结果"

#     # chain
#     s3.head = (s2.tail or "").strip() or "关键结果"

#     # step3
#     if not (s3.relation or "").strip():
#         s3.relation = "促进"
#     if not (s3.tail or "").strip():
#         s3.tail = "疗效改进"

#     # claims：若为空，给最小可读句，不引入论文外新实体
#     if not (s1.claim or "").strip():
#         s1.claim = f"{s1.head}{s1.relation}{s1.tail}，构成该路径的关键前提。"
#     if not (s2.claim or "").strip():
#         s2.claim = f"{s2.head}{s2.relation}{s2.tail}，形成可操作的中介环节。"
#     if not (s3.claim or "").strip():
#         s3.claim = f"如果{s3.head}{s3.relation}{s3.tail}，则该路径的假设得到可检验的支持。"

#     # 强制 step 编号一致（仅防御性）
#     s1.step, s2.step, s3.step = 1, 2, 3
#     return [s1, s2, s3]


# def ensure_hypothesis_chinese(
#     h: Hypothesis3Levels,
#     struct: Optional[StructExtraction] = None,
# ) -> Hypothesis3Levels:
#     """
#     当“假设”中出现英文时：
#     1) 优先用 struct 中的“英文 term -> 中文 normalized”做替换；
#     2) 再兜底删除残留英文 token；
#     3) 若删除后出现空字段，则用最小中文占位补齐，并强制链式一致性；
#     4) 不抛错，确保不会因英文导致整条记录失败。
#     """
#     reps = _build_term_replacements_from_struct(struct)

#     def fix_path(path: List[HypothesisStep]) -> List[HypothesisStep]:
#         if not path:
#             return path
#         # 先逐字段清洗
#         for step in path:
#             step.head = _fix_step_text(getattr(step, "head", ""), reps)
#             step.relation = _fix_step_text(getattr(step, "relation", ""), reps)
#             step.tail = _fix_step_text(getattr(step, "tail", ""), reps)
#             step.claim = _fix_step_text(getattr(step, "claim", ""), reps)

#         # 强制链式一致性（避免“英文替换/剥离”后出现不一致）
#         if len(path) >= 2:
#             path[1].head = (path[0].tail or "").strip()
#         if len(path) >= 3:
#             path[2].head = (path[1].tail or "").strip()

#         # 若你的 schema 已硬约束每条路径必须 3 steps，这里主要做“字段为空”兜底
#         if len(path) == 3:
#             path = _fallback_fill_path_3steps(path)

#         return path

#     # levels
#     h.一级 = [fix_path(p) for p in (h.一级 or [])]
#     h.二级 = [fix_path(p) for p in (h.二级 or [])]
#     h.三级 = [fix_path(p) for p in (h.三级 or [])]

#     # summaries
#     def fix_summaries(lst: List[str]) -> List[str]:
#         out: List[str] = []
#         for s in (lst or []):
#             s2 = _fix_step_text(s or "", reps)
#             out.append(s2)
#         return out

#     h.一级总结 = fix_summaries(h.一级总结 or [])
#     h.二级总结 = fix_summaries(h.二级总结 or [])
#     h.三级总结 = fix_summaries(h.三级总结 or [])

#     # 如果清洗后有空总结，用“对应路径 step3.claim”自动补齐（只补齐，不覆盖）
#     h = ensure_hypothesis_summaries(h)

#     return h


# def _collect_latin_positions(h: Hypothesis3Levels) -> List[str]:
#     """
#     仅用于日志：定位哪些字段还残留英文（理论上 ensure_hypothesis_chinese 后应为空）。
#     """
#     hits: List[str] = []

#     for lvl_name, paths in (("一级", h.一级), ("二级", h.二级), ("三级", h.三级)):
#         for pi, path in enumerate(paths or []):
#             for si, step in enumerate(path or []):
#                 for fn in ("head", "relation", "tail", "claim"):
#                     val = (getattr(step, fn, "") or "").strip()
#                     if val and _has_latin_letters(val):
#                         hits.append(f"{lvl_name}[{pi}].step{si+1}.{fn}")

#     for sum_name, summaries in (("一级总结", h.一级总结), ("二级总结", h.二级总结), ("三级总结", h.三级总结)):
#         for i, s in enumerate(summaries or []):
#             s = (s or "").strip()
#             if s and _has_latin_letters(s):
#                 hits.append(f"{sum_name}[{i}]")

#     return hits


# # ----------------------------
# # Prompt（假设要求中文；不允许英文）
# # ----------------------------
# SYSTEM_PROMPT_HYP = """你是一名跨学科科研假设构建助手。
# 任务：给定某篇论文的“结构化摘要”和已经确定好的三级查询（Query3Levels），
# 为每一级查询生成对应的“知识路径形式”的假设结构（Hypothesis3Levels）。

# 【语言要求（必须满足）】
# - 你生成的“假设”内容必须为中文；
# - 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。
# -（注意：这里只约束“假设部分”，不要求你改写其它模块如概念/关系的语言。）

# 1) 输入：
#    - meta: {title, primary, secondary_list}
#    - primary_concepts: 主学科关键概念列表
#    - secondary_concepts: { 学科名: 概念列表 }
#    - relations: 若干跨学科关系 {head, tail, relation, relation_type}
#    - 查询(Query3Levels): { 一级, 二级[], 三级[] }

# 2) 输出：
#    顶层只输出：
#    {
#      "假设": Hypothesis3Levels
#    }

#    其中 Hypothesis3Levels = {
#      "一级": [ [HypothesisStep,...], ... ],
#      "二级": [ [HypothesisStep,...], ... ],
#      "三级": [ [HypothesisStep,...], ... ],
#      "一级总结": [string,...],
#      "二级总结": [string,...],
#      "三级总结": [string,...]
#    }

#    HypothesisStep = { step:int, head, relation, tail, claim }

# 3) 对齐约束（必须满足）：
#    - 假设.一级 至少包含一条路径，对应地回答 查询.一级；
#    - 查询.二级 的问题数 == 假设.二级 的路径数，按顺序一一对应；
#    - 查询.三级 的问题数 == 假设.三级 的路径数，按顺序一一对应；
#    - 一级总结/二级总结/三级总结 必须是列表（而不是单个字符串），
#      列表长度分别等于对应层级的路径数，并一一对应；
#    - 总结语必须基于对应路径的三步链条进行概括，不得引入新事实。

# 4) 【硬性结构约束（必须满足）】：
#    - 每一条知识路径必须恰好包含 3 个 step，且 step 必须严格为 1, 2, 3。
#    - 链式一致性：step2.head 必须等于 step1.tail；step3.head 必须等于 step2.tail。
#    - 禁止出现“跳链”、禁止多于或少于 3 步。
#    - 每条路径的最后一步（step3）的 claim 必须是一句完整、可检验、专业的总结性假设陈述。

# 5) 学科/逻辑要求：
#    - H1（一级路径）：
#      - 从主学科视角出发，用若干条“粗粒度”3-step 链条刻画当前临床/科学瓶颈；
#      - 每条路径的最后一步必须明确指出“需要某个辅学科来补位”的角色（写进 claim）；
#      - 若存在多个辅学科，强烈建议一级至少给出与辅学科数量相当的路径。
#    - H2（二级路径）：
#      - 每条路径对应 Query.二级 中的一个具体问题；
#      - 用 3-step 链条表达“辅学科工具/机制 → 关键中介（特征/模型/通路） → 主学科可改进目标/指标”。
#    - H3（三级路径）：
#      - 每条路径对应 Query.三级 中的一个更具体、更操作化的问题；
#      - 用 3-step 链条表达“前提 → 方法介入 → 可观察验证闭环”。

# 6) 总结写法（必须一一对应）：
#    - 一级总结：对应一级路径，概括“主学科瓶颈 + 哪个辅学科补位 + 预期改进”；
#    - 二级总结：对应二级路径，概括“辅学科如何把问题变成可操作机制/建模问题，并指向主学科改进”；
#    - 三级总结：对应三级路径，概括“跨学科三步工作流如何闭环验证假设”。

# 输出要求：
# - 严格输出一个 JSON 对象，仅包含键："假设"。
# - 禁止输出任何说明文字或 Markdown 代码块。
# """

# HYP_USER_TEMPLATE = """输入：
# - 结构化摘要：
# {summary_json}

# - 查询结构：
# {query_json}

# - 学科信息：
#   * 主学科: {primary}
#   * 辅学科数量: {n_secondary}
#   * 辅学科列表: {secondary_list_str}

# 请严格遵守系统提示中的约束与学科要求：
# - “假设部分”必须为中文（禁止 A-Z/a-z）；
# - 每条路径恰好 3 个 step（1/2/3）；
# - step2.head==step1.tail，step3.head==step2.tail；
# - 查询.二级/三级 与 假设.二级/三级 一一对应；
# - 总结列表长度与路径数一致，并基于对应 3-step 路径，不得引入新事实。

# 生成完整的“假设”结构（Hypothesis3Levels），并放入顶层键 "假设" 中。"""


# def build_hypothesis_messages(
#     struct: StructExtraction,
#     query: Query3Levels,
# ) -> List[Dict[str, str]]:
#     # 不再因为查询含英文而抛错导致整条记录失败；兜底清洗后继续
#     _ensure_chinese_query_inplace(query)

#     summary_json = build_struct_summary_json(struct)
#     query_json = json.dumps(query.model_dump(), ensure_ascii=False, indent=2)

#     primary = struct.meta.primary
#     sec_list = [s.strip() for s in (struct.meta.secondary_list or []) if s.strip()]
#     n_secondary = len(sec_list)
#     secondary_list_str = ", ".join(sec_list) if sec_list else "（无辅学科）"

#     user_content = HYP_USER_TEMPLATE.format(
#         summary_json=summary_json,
#         query_json=query_json,
#         primary=primary,
#         n_secondary=n_secondary,
#         secondary_list_str=secondary_list_str,
#     )

#     return [
#         {"role": "system", "content": SYSTEM_PROMPT_HYP},
#         {"role": "user", "content": user_content},
#     ]



# def _deterministic_repair_hypothesis_links(hdict: dict) -> dict:
#     """
#     在 Pydantic 校验前对 3-step 路径做确定性链路对齐（deterministic repair）。
#     目的：避免由于轻微改写（如增删“相关/机制/方面”等）导致 step2.tail != step3.head 的硬失败。
#     修复规则（逐路径）：
#     - step2.head  := step1.tail（若 step1.tail 非空）
#     - step3.head  := step2.tail（若 step2.tail 非空）
#     """
#     if not isinstance(hdict, dict):
#         return hdict
#     for lvl in ("一级", "二级", "三级"):
#         paths = hdict.get(lvl)
#         if not isinstance(paths, list):
#             continue
#         for path in paths:
#             if not isinstance(path, list) or len(path) < 3:
#                 continue
#             s1, s2, s3 = path[0], path[1], path[2]
#             if isinstance(s1, dict) and isinstance(s2, dict):
#                 t1 = (s1.get("tail") or "").strip()
#                 if t1:
#                     s2["head"] = t1
#             if isinstance(s2, dict) and isinstance(s3, dict):
#                 t2 = (s2.get("tail") or "").strip()
#                 if t2:
#                     s3["head"] = t2
#     return hdict

# def parse_hypothesis_output(
#     text: str,
#     struct: Optional[StructExtraction] = None,
# ) -> Hypothesis3Levels:
#     """
#     重要变化：
#     - 不再因为“假设中含英文”而抛错导致整条记录失败；
#     - 发现英文时会自动替换/清洗，并返回修复后的 Hypothesis3Levels。
#     """
#     obj = coerce_json_object(text, required_top_keys={"假设"})
#     if not isinstance(obj, dict) or "假设" not in obj:
#         raise ValueError("假设生成输出缺少 '假设' 字段")

#     # 先做 Schema 校验（含 3-step + 链式一致性等硬约束）
#     # 在 Schema 校验前做确定性链路对齐，降低因轻微改写导致的硬失败
#     hyp_dict = obj["假设"]
#     if isinstance(hyp_dict, dict):
#         hyp_dict = _deterministic_repair_hypothesis_links(hyp_dict)
#     h = Hypothesis3Levels.model_validate(hyp_dict)

#     # 总结只补齐不覆盖；并保证逐路径对齐
#     h = ensure_hypothesis_summaries(h)

#     # 发现英文：自动修复（不报错）
#     if _collect_latin_positions(h):
#         h = ensure_hypothesis_chinese(h, struct=struct)
#         remaining = _collect_latin_positions(h)
#         if remaining:
#             # 理论上不应发生；发生时也不抛错，只记录，避免整条失败
#             logger.warning("假设字段清洗后仍残留英文位置：%s", "; ".join(remaining))
#         else:
#             logger.warning("检测到假设中含英文，已自动清洗为中文（不再报错）。")

#     return h



# crossdisc_extractor/prompts/hypothesis_prompt.py
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from crossdisc_extractor.schemas import StructExtraction, Query3Levels, Hypothesis3Levels, HypothesisStep
from crossdisc_extractor.utils.summarize import build_struct_summary_json
from crossdisc_extractor.utils.parsing import coerce_json_object, ensure_hypothesis_summaries

logger = logging.getLogger("crossdisc.hypothesis_prompt")

_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\/\.]*")


def _has_latin_letters(s: str) -> bool:
    return bool(_LATIN_RE.search(s or ""))


# ----------------------------
# 术语替换：尽量把英文术语替换成结构化抽取里已有的中文 normalized
# ----------------------------
def _build_term_replacements_from_struct(struct: Optional[StructExtraction]) -> List[Tuple[str, str]]:
    """
    构建“英文术语 -> 中文归一化术语”的替换表（尽力而为）。
    只用于清洗“假设”里的英文残留，避免简单粗暴删除导致语义损失。
    """
    if struct is None:
        return []

    reps: List[Tuple[str, str]] = []

    def add_pair(term: str, normalized: str):
        term = (term or "").strip()
        normalized = (normalized or "").strip()
        if not term or not normalized:
            return
        # 只收集：term 含英文、normalized 不含英文 的映射
        if _has_latin_letters(term) and (not _has_latin_letters(normalized)):
            reps.append((term, normalized))

    # 概念：主学科 + 辅学科
    concepts = struct.概念
    for e in (concepts.主学科 or []):
        add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")
    for _, lst in (concepts.辅学科 or {}).items():
        for e in (lst or []):
            add_pair(getattr(e, "term", ""), getattr(e, "normalized", "") or "")

    # 去重（保序）+ 长词优先替换
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for a, b in reps:
        key = (a.lower(), b)
        if key not in seen:
            seen.add(key)
            uniq.append((a, b))
    uniq.sort(key=lambda x: len(x[0]), reverse=True)
    return uniq


def _apply_replacements(text: str, reps: List[Tuple[str, str]]) -> str:
    s = text or ""
    for src, tgt in reps:
        s = re.sub(re.escape(src), tgt, s, flags=re.IGNORECASE)
    return s


def _strip_remaining_latin_tokens(text: str) -> str:
    """
    兜底：移除仍残留的英文 token，确保最终“假设”不含拉丁字母。
    """
    s = text or ""
    s = _LATIN_TOKEN_RE.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    # 清理一些英文 token 删除后留下的空括号/多余符号
    s = re.sub(r"[（）\(\)]\s*[）\)]", "）", s)
    s = re.sub(r"[\(（]\s*[\)）]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


# ----------------------------
# 查询中文要求：不再报错；若含英文，做轻量清洗后继续
# ----------------------------
def _ensure_chinese_query_inplace(query: Query3Levels) -> Query3Levels:
    """
    build_hypothesis_messages 阶段的兜底：
    - 查询理论上已在“查询阶段”被强制清洗为中文；
    - 若仍含英文，这里不再抛错导致整条记录失败，而是轻量清洗后继续。
    """
    def fix_one(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        if _has_latin_letters(s):
            s = _strip_remaining_latin_tokens(s)
        return s

    query.一级 = fix_one(query.一级 or "")
    query.二级 = [fix_one(x or "") for x in (query.二级 or [])]
    query.三级 = [fix_one(x or "") for x in (query.三级 or [])]
    return query


# ----------------------------
# 假设中文清洗：发现英文则修复并返回，不抛错
# ----------------------------
def _fix_step_text(
    s: str,
    reps: List[Tuple[str, str]],
) -> str:
    s2 = _apply_replacements(s or "", reps) if reps else (s or "")
    if _has_latin_letters(s2):
        s2 = _strip_remaining_latin_tokens(s2)
    return (s2 or "").strip()


def _fallback_fill_path_3steps(path: List[HypothesisStep]) -> List[HypothesisStep]:
    """
    保守兜底（一般不触发）：若清洗导致关键字段为空，填充最小中文占位，尽量保持链式一致性。
    注意：这里不引入具体论文新事实，只提供结构性占位，避免后续崩溃。
    """
    # 期望 path 已经是 3 steps（你的 schema 若已硬约束，这里主要用于“字段为空”的兜底）
    if not path or len(path) != 3:
        return path

    s1, s2, s3 = path[0], path[1], path[2]

    # step1
    if not (s1.head or "").strip():
        s1.head = "关键前提"
    if not (s1.relation or "").strip():
        s1.relation = "影响"
    if not (s1.tail or "").strip():
        s1.tail = "关键中介"

    # chain
    s2.head = (s1.tail or "").strip() or "关键中介"

    # step2
    if not (s2.relation or "").strip():
        s2.relation = "导致"
    if not (s2.tail or "").strip():
        s2.tail = "关键结果"

    # chain
    s3.head = (s2.tail or "").strip() or "关键结果"

    # step3
    if not (s3.relation or "").strip():
        s3.relation = "促进"
    if not (s3.tail or "").strip():
        s3.tail = "疗效改进"

    # claims：若为空，给最小可读句，不引入论文外新实体
    if not (s1.claim or "").strip():
        s1.claim = f"{s1.head}{s1.relation}{s1.tail}，构成该路径的关键前提。"
    if not (s2.claim or "").strip():
        s2.claim = f"{s2.head}{s2.relation}{s2.tail}，形成可操作的中介环节。"
    if not (s3.claim or "").strip():
        s3.claim = f"如果{s3.head}{s3.relation}{s3.tail}，则该路径的假设得到可检验的支持。"

    # 强制 step 编号一致（仅防御性）
    s1.step, s2.step, s3.step = 1, 2, 3
    return [s1, s2, s3]


def ensure_hypothesis_chinese(
    h: Hypothesis3Levels,
    struct: Optional[StructExtraction] = None,
) -> Hypothesis3Levels:
    """
    当“假设”中出现英文时：
    1) 优先用 struct 中的“英文 term -> 中文 normalized”做替换；
    2) 再兜底删除残留英文 token；
    3) 若删除后出现空字段，则用最小中文占位补齐，并强制链式一致性；
    4) 不抛错，确保不会因英文导致整条记录失败。
    """
    reps = _build_term_replacements_from_struct(struct)

    def fix_path(path: List[HypothesisStep]) -> List[HypothesisStep]:
        if not path:
            return path
        # 先逐字段清洗
        for step in path:
            step.head = _fix_step_text(getattr(step, "head", ""), reps)
            step.relation = _fix_step_text(getattr(step, "relation", ""), reps)
            step.tail = _fix_step_text(getattr(step, "tail", ""), reps)
            step.claim = _fix_step_text(getattr(step, "claim", ""), reps)

        # 强制链式一致性（避免“英文替换/剥离”后出现不一致）
        if len(path) >= 2:
            path[1].head = (path[0].tail or "").strip()
        if len(path) >= 3:
            path[2].head = (path[1].tail or "").strip()

        # 若你的 schema 已硬约束每条路径必须 3 steps，这里主要做“字段为空”兜底
        if len(path) == 3:
            path = _fallback_fill_path_3steps(path)

        return path

    # levels
    h.一级 = [fix_path(p) for p in (h.一级 or [])]
    h.二级 = [fix_path(p) for p in (h.二级 or [])]
    h.三级 = [fix_path(p) for p in (h.三级 or [])]

    # summaries
    def fix_summaries(lst: List[str]) -> List[str]:
        out: List[str] = []
        for s in (lst or []):
            s2 = _fix_step_text(s or "", reps)
            out.append(s2)
        return out

    h.一级总结 = fix_summaries(h.一级总结 or [])
    h.二级总结 = fix_summaries(h.二级总结 or [])
    h.三级总结 = fix_summaries(h.三级总结 or [])

    # 如果清洗后有空总结，用“对应路径 step3.claim”自动补齐（只补齐，不覆盖）
    h = ensure_hypothesis_summaries(h)

    return h


def _collect_latin_positions(h: Hypothesis3Levels) -> List[str]:
    """
    仅用于日志：定位哪些字段还残留英文（理论上 ensure_hypothesis_chinese 后应为空）。
    """
    hits: List[str] = []

    for lvl_name, paths in (("一级", h.一级), ("二级", h.二级), ("三级", h.三级)):
        for pi, path in enumerate(paths or []):
            for si, step in enumerate(path or []):
                for fn in ("head", "relation", "tail", "claim"):
                    val = (getattr(step, fn, "") or "").strip()
                    if val and _has_latin_letters(val):
                        hits.append(f"{lvl_name}[{pi}].step{si+1}.{fn}")

    for sum_name, summaries in (("一级总结", h.一级总结), ("二级总结", h.二级总结), ("三级总结", h.三级总结)):
        for i, s in enumerate(summaries or []):
            s = (s or "").strip()
            if s and _has_latin_letters(s):
                hits.append(f"{sum_name}[{i}]")

    return hits


# ----------------------------
# Prompt（假设要求中文；不允许英文）
# ----------------------------
SYSTEM_PROMPT_HYP = """你是一名跨学科科研假设构建助手。
任务：给定某篇论文的“结构化摘要”和已经确定好的三级查询（Query3Levels），
为每一级查询生成对应的“知识路径形式”的假设结构（Hypothesis3Levels）。

【语言要求（必须满足）】
- 你生成的“假设”内容必须为中文；
- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。
-（注意：这里只约束“假设部分”，不要求你改写其它模块如概念/关系的语言。）

1) 输入：
   - meta: {title, primary, secondary_list}
   - primary_concepts: 主学科关键概念列表
   - secondary_concepts: { 学科名: 概念列表 }
   - relations: 若干跨学科关系 {head, tail, relation, relation_type}
   - 查询(Query3Levels): { 一级, 二级[], 三级[] }

2) 输出：
   顶层只输出：
   {
     "假设": Hypothesis3Levels
   }

   其中 Hypothesis3Levels = {
     "一级": [ [HypothesisStep,...], ... ],
     "二级": [ [HypothesisStep,...], ... ],
     "三级": [ [HypothesisStep,...], ... ],
     "一级总结": [string,...],
     "二级总结": [string,...],
     "三级总结": [string,...]
   }

   HypothesisStep = { step:int, head, relation, tail, claim }

3) 对齐约束（必须满足）：
   - 假设.一级 至少包含一条路径，对应地回答 查询.一级；
   - 查询.二级 的问题数 == 假设.二级 的路径数，按顺序一一对应；
   - 查询.三级 的问题数 == 假设.三级 的路径数，按顺序一一对应；
   - 一级总结/二级总结/三级总结 必须是列表（而不是单个字符串），
     列表长度分别等于对应层级的路径数，并一一对应；
   - 总结语必须基于对应路径的三步链条进行概括，不得引入新事实。

4) 【硬性结构约束（必须满足）】：
   - 每一条知识路径必须恰好包含 3 个 step，且 step 必须严格为 1, 2, 3。
   - 链式一致性：step2.head 必须等于 step1.tail；step3.head 必须等于 step2.tail。
   - 禁止出现“跳链”、禁止多于或少于 3 步。
   - 每条路径的最后一步（step3）的 claim 必须是一句完整、可检验、专业的总结性假设陈述。

5) 学科/逻辑要求：
   - H1（一级路径）：
     - 从主学科视角出发，用若干条“粗粒度”3-step 链条刻画当前临床/科学瓶颈；
     - 每条路径的最后一步必须明确指出“需要某个辅学科来补位”的角色（写进 claim）；
     - 若存在多个辅学科，强烈建议一级至少给出与辅学科数量相当的路径。
   - H2（二级路径）：
     - 每条路径对应 Query.二级 中的一个具体问题；
     - 用 3-step 链条表达“辅学科工具/机制 → 关键中介（特征/模型/通路） → 主学科可改进目标/指标”。
   - H3（三级路径）：
     - 每条路径对应 Query.三级 中的一个更具体、更操作化的问题；
     - 用 3-step 链条表达“前提 → 方法介入 → 可观察验证闭环”。

6) 总结写法（必须一一对应）：
   - 一级总结：对应一级路径，概括“主学科瓶颈 + 哪个辅学科补位 + 预期改进”；
   - 二级总结：对应二级路径，概括“辅学科如何把问题变成可操作机制/建模问题，并指向主学科改进”；
   - 三级总结：对应三级路径，概括“跨学科三步工作流如何闭环验证假设”。

输出要求：
- 严格输出一个 JSON 对象，仅包含键："假设"。
- 禁止输出任何说明文字或 Markdown 代码块。
"""

HYP_USER_TEMPLATE = """输入：
- 结构化摘要：
{summary_json}

- 查询结构：
{query_json}

- 学科信息：
  * 主学科: {primary}
  * 辅学科数量: {n_secondary}
  * 辅学科列表: {secondary_list_str}

请严格遵守系统提示中的约束与学科要求：
- “假设部分”必须为中文（禁止 A-Z/a-z）；
- 每条路径恰好 3 个 step（1/2/3）；
- step2.head==step1.tail，step3.head==step2.tail；
- 查询.二级/三级 与 假设.二级/三级 一一对应；
- 总结列表长度与路径数一致，并基于对应 3-step 路径，不得引入新事实。

生成完整的“假设”结构（Hypothesis3Levels），并放入顶层键 "假设" 中。"""


def build_hypothesis_messages(
    struct: StructExtraction,
    query: Query3Levels,
) -> List[Dict[str, str]]:
    # 不再因为查询含英文而抛错导致整条记录失败；兜底清洗后继续
    _ensure_chinese_query_inplace(query)

    summary_json = build_struct_summary_json(struct)
    query_json = json.dumps(query.model_dump(), ensure_ascii=False, indent=2)

    primary = struct.meta.primary
    sec_list = [s.strip() for s in (struct.meta.secondary_list or []) if s.strip()]
    n_secondary = len(sec_list)
    secondary_list_str = ", ".join(sec_list) if sec_list else "（无辅学科）"

    user_content = HYP_USER_TEMPLATE.format(
        summary_json=summary_json,
        query_json=query_json,
        primary=primary,
        n_secondary=n_secondary,
        secondary_list_str=secondary_list_str,
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT_HYP},
        {"role": "user", "content": user_content},
    ]


def parse_hypothesis_output(
    text: str,
    struct: Optional[StructExtraction] = None,
) -> Hypothesis3Levels:
    """
    重要变化：
    - 不再因为“假设中含英文”而抛错导致整条记录失败；
    - 发现英文时会自动替换/清洗，并返回修复后的 Hypothesis3Levels。
    """
    obj = coerce_json_object(text, required_top_keys={"假设"})
    if not isinstance(obj, dict) or "假设" not in obj:
        raise ValueError("假设生成输出缺少 '假设' 字段")

    # 先做 Schema 校验（含 3-step + 链式一致性等硬约束）
    h = Hypothesis3Levels.model_validate(obj["假设"])

    # 总结只补齐不覆盖；并保证逐路径对齐
    h = ensure_hypothesis_summaries(h)

    # 发现英文：自动修复（不报错）
    if _collect_latin_positions(h):
        h = ensure_hypothesis_chinese(h, struct=struct)
        remaining = _collect_latin_positions(h)
        if remaining:
            # 理论上不应发生；发生时也不抛错，只记录，避免整条失败
            logger.warning("假设字段清洗后仍残留英文位置：%s", "; ".join(remaining))
        else:
            logger.warning("检测到假设中含英文，已自动清洗为中文（不再报错）。")

    return h
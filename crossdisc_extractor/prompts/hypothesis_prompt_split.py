# crossdisc_extractor/prompts/hypothesis_prompt_split.py
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Any

from crossdisc_extractor.schemas import StructExtraction, Query3Levels, HypothesisStep
from crossdisc_extractor.utils.summarize import build_struct_summary_json
from crossdisc_extractor.prompts.hypothesis_prompt import (
    _ensure_chinese_query_inplace,
    HYP_USER_TEMPLATE,
    _collect_latin_positions,
    ensure_hypothesis_chinese,
    ensure_hypothesis_summaries,
    coerce_json_object
)
from crossdisc_extractor.schemas import Hypothesis3Levels

logger = logging.getLogger("crossdisc.hypothesis_prompt_split")

# ----------------------------
# Level 1 System Prompt
# ----------------------------
SYSTEM_PROMPT_HYP_L1 = """你是一名跨学科科研假设构建助手。
任务：给定某篇论文的“结构化摘要”和已经确定好的三级查询（Query3Levels），
请仅针对【一级查询】（宏观/整篇论文层面）生成对应的“知识路径形式”的假设结构。

【语言要求（必须满足）】
- 你生成的“假设”内容必须为中文；
- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。

1) 输入：
   - meta: {title, primary, secondary_list}
   - primary_concepts: 主学科关键概念列表
   - secondary_concepts: { 学科名: 概念列表 }
   - relations: 若干跨学科关系 {head, tail, relation, relation_type}
   - 查询(Query3Levels): { 一级, 二级[], 三级[] }

2) 输出：
   顶层只输出：
   {
     "假设": {
       "一级": [ [HypothesisStep, HypothesisStep, HypothesisStep], ... ],
       "一级总结": [string, ...]
     }
   }

   HypothesisStep = { step:int, head, relation, tail, claim }

3) 对齐约束（必须满足）：
   - 假设.一级 至少包含一条路径，对应地回答 查询.一级；
   - 一级总结 必须是列表，长度等于 一级 的路径数，并一一对应；
   - 总结语必须基于对应路径的三步链条进行概括，不得引入新事实。

4) 【硬性结构约束（必须满足）】：
   - 每一条知识路径必须恰好包含 3 个 step，且 step 必须严格为 1, 2, 3。
   - 链式一致性：step2.head 必须等于 step1.tail；step3.head 必须等于 step2.tail。
   - 禁止出现“跳链”、禁止多于或少于 3 步。
   - 每条路径的最后一步（step3）的 claim 必须是一句完整、可检验、专业的总结性假设陈述。

5) 【实体对齐硬性约束（至关重要 — 违反此约束将导致输出无效）】：
   - **Head/Tail 必须逐字复用概念词表**：路径中的 `head` 和 `tail` 字段必须**严格逐字**从用户消息中”允许使用的概念词表”中选取，不允许做任何修改。
   - **判断标准**：如果你输出的 head 或 tail 不能在”允许使用的概念词表”中找到完全相同的字符串，则该输出无效。
   - **禁止的修改形式**（以下全部违规）：
     * 添加后缀：”催化剂” → “催化剂稳定性” ✗
     * 添加前缀：”污染物” → “难降解污染物” ✗
     * 拼接组合：”纳米颗粒” + “氧化锌” → “氧化锌纳米颗粒稳定性” ✗
     * 概括改写：”硫酸根自由基” → “活性物种” ✗
     * 自创新词：使用词表中不存在的任何词 ✗
   - **禁止使用通用占位符**：严禁使用如”关键前提”、”关键中介”、”关键结果”、”疗效改进”、”前提”、”结论”等非具体学科概念的词汇。
   - **逻辑外移**：如果需要表达动作、状态或变化（如”激活”、”抑制”、”检测”、”提升”），请将这些词汇放入 `relation` 字段，或在 `claim` 字段的自然语言描述中体现。
   - **示例**（假设词表中有”耐药性癫痫”和”深部脑刺激”）：
     - 错误：head: “识别耐药性癫痫”, tail: “治疗效果提升”（”识别...”和”...提升”是自创修改）
     - 正确：head: “耐药性癫痫”, relation: “可通过...改善治疗效果”, tail: “深部脑刺激”
   - 从主学科视角出发，用若干条“粗粒度”3-step 链条刻画当前临床/科学瓶颈；
   - 每条路径的最后一步必须明确指出“需要某个辅学科来补位”的角色（写进 claim）；
   - 若存在多个辅学科，强烈建议一级至少给出与辅学科数量相当的路径。

7) 总结写法：
   - 一级总结：对应一级路径，概括“主学科瓶颈 + 哪个辅学科补位 + 预期改进”。

输出要求：
- 严格输出一个 JSON 对象，仅包含键 "假设"，内部包含 "一级" 和 "一级总结"。
- 禁止输出任何说明文字或 Markdown 代码块。
"""

# ----------------------------
# Level 2 System Prompt
# ----------------------------
SYSTEM_PROMPT_HYP_L2 = """你是一名跨学科科研假设构建助手。
任务：给定某篇论文的“结构化摘要”和已经确定好的三级查询（Query3Levels），
请仅针对【二级查询】（辅助学科层面）生成对应的“知识路径形式”的假设结构。

【语言要求（必须满足）】
- 你生成的“假设”内容必须为中文；
- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。

1) 输入：
   - 查询(Query3Levels): { 一级, 二级[], 三级[] }
   ... (其他同上)

2) 输出：
   顶层只输出：
   {
     "假设": {
       "二级": [ [HypothesisStep, HypothesisStep, HypothesisStep], ... ],
       "二级总结": [string, ...]
     }
   }

3) 对齐约束（必须满足）：
   - 查询.二级 的问题数 == 假设.二级 的路径数，按顺序一一对应；
   - 二级总结 必须是列表，长度等于 二级 的路径数，并一一对应；
   - 总结语必须基于对应路径的三步链条进行概括，不得引入新事实。

4) 【硬性结构约束（必须满足）】：
   - 每一条知识路径必须恰好包含 3 个 step，且 step 必须严格为 1, 2, 3。
   - 链式一致性：step2.head 必须等于 step1.tail；step3.head 必须等于 step2.tail。

5) 【实体对齐硬性约束（至关重要 — 违反此约束将导致输出无效）】：
   - **Head/Tail 必须逐字复用概念词表**：路径中的 `head` 和 `tail` 字段必须**严格逐字**从用户消息中”允许使用的概念词表”中选取，不允许做任何修改。
   - **判断标准**：如果你输出的 head 或 tail 不能在”允许使用的概念词表”中找到完全相同的字符串，则该输出无效。
   - **禁止的修改形式**：添加前缀/后缀、拼接组合、概括改写、自创新词——全部违规。
   - **禁止使用通用占位符**：严禁使用”关键前提”、”关键中介”、”关键结果”等非具体学科概念的词汇。
   - **逻辑外移**：动作、状态、变化词（如”激活”、”抑制”、”提升”）放入 `relation` 或 `claim`，不要放入 head/tail。

6) 学科/逻辑要求（H2 二级路径）：
   - 每条路径对应 Query.二级 中的一个具体问题；
   - 用 3-step 链条表达“辅学科工具/机制 → 关键中介（特征/模型/通路） → 主学科可改进目标/指标”。

7) 总结写法：
   - 二级总结：对应二级路径，概括“辅学科如何把问题变成可操作机制/建模问题，并指向主学科改进”。

输出要求：
- 严格输出一个 JSON 对象，仅包含键 "假设"，内部包含 "二级" 和 "二级总结"。
"""

# ----------------------------
# Level 3 System Prompt
# ----------------------------
SYSTEM_PROMPT_HYP_L3 = """你是一名跨学科科研假设构建助手。
任务：给定某篇论文的“结构化摘要”和已经确定好的三级查询（Query3Levels），
请仅针对【三级查询】（具体操作/方法层面）生成对应的“知识路径形式”的假设结构。

【语言要求（必须满足）】
- 你生成的“假设”内容必须为中文；
- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。

1) 输入：
   - 查询(Query3Levels): { 一级, 二级[], 三级[] }
   ... (其他同上)

2) 输出：
   顶层只输出：
   {
     "假设": {
       "三级": [ [HypothesisStep, HypothesisStep, HypothesisStep], ... ],
       "三级总结": [string, ...]
     }
   }

3) 对齐约束（必须满足）：
   - 查询.三级 的问题数 == 假设.三级 的路径数，按顺序一一对应；
   - 三级总结 必须是列表，长度等于 三级 的路径数，并一一对应；
   - 总结语必须基于对应路径的三步链条进行概括，不得引入新事实。

4) 【硬性结构约束（必须满足）】：
   - 每一条知识路径必须恰好包含 3 个 step，且 step 必须严格为 1, 2, 3。
   - 链式一致性：step2.head 必须等于 step1.tail；step3.head 必须等于 step2.tail。

5) 【实体对齐硬性约束（至关重要 — 违反此约束将导致输出无效）】：
   - **Head/Tail 必须逐字复用概念词表**：路径中的 `head` 和 `tail` 字段必须**严格逐字**从用户消息中”允许使用的概念词表”中选取，不允许做任何修改。
   - **判断标准**：如果你输出的 head 或 tail 不能在”允许使用的概念词表”中找到完全相同的字符串，则该输出无效。
   - **禁止的修改形式**：添加前缀/后缀、拼接组合、概括改写、自创新词——全部违规。
   - **禁止使用通用占位符**：严禁使用”关键前提”、”关键中介”、”关键结果”等非具体学科概念的词汇。
   - **逻辑外移**：动作、状态、变化词放入 `relation` 或 `claim`，不要放入 head/tail。

6) 学科/逻辑要求（H3 三级路径）：
   - 每条路径对应 Query.三级 中的一个更具体、更操作化的问题；
   - 用 3-step 链条表达“前提 → 方法介入 → 可观察验证闭环”。

7) 总结写法：
   - 三级总结：对应三级路径，概括“跨学科三步工作流如何闭环验证假设”。

输出要求：
- 严格输出一个 JSON 对象，仅包含键 "假设"，内部包含 "三级" 和 "三级总结"。
"""


def _collect_allowed_normalized(struct: StructExtraction) -> List[str]:
    """从 struct 的概念中收集所有 normalized 值，作为假设 head/tail 的允许词表。"""
    allowed = []
    seen = set()
    concepts = struct.概念
    if concepts and concepts.主学科:
        for c in concepts.主学科:
            n = (c.normalized or c.term or "").strip()
            if n and n not in seen:
                allowed.append(n)
                seen.add(n)
    if concepts and concepts.辅学科:
        for disc, lst in concepts.辅学科.items():
            for c in lst:
                n = (c.normalized or c.term or "").strip()
                if n and n not in seen:
                    allowed.append(n)
                    seen.add(n)
    return allowed


def _build_user_content(struct: StructExtraction, query: Query3Levels) -> str:
    # 复用原有的 user template 逻辑
    _ensure_chinese_query_inplace(query)
    summary_json = build_struct_summary_json(struct)
    query_json = json.dumps(query.model_dump(), ensure_ascii=False, indent=2)

    primary = struct.meta.primary
    sec_list = [s.strip() for s in (struct.meta.secondary_list or []) if s.strip()]
    n_secondary = len(sec_list)
    secondary_list_str = ", ".join(sec_list) if sec_list else "（无辅学科）"

    # 构建允许的 normalized 概念列表
    allowed_terms = _collect_allowed_normalized(struct)
    allowed_list_str = "\n".join(f"  - {t}" for t in allowed_terms) if allowed_terms else "  （无）"

    base_info = f"""输入：
- 结构化摘要：
{summary_json}

- 查询结构：
{query_json}

- 学科信息：
  * 主学科: {primary}
  * 辅学科数量: {n_secondary}
  * 辅学科列表: {secondary_list_str}

- 【允许使用的概念词表（head/tail 必须从中选取，严禁自创）】：
{allowed_list_str}

请严格遵守系统提示中的约束与学科要求。
特别提醒：每个 step 的 head 和 tail 必须**逐字**从上方"允许使用的概念词表"中选取，
不得做任何修改、拼接、添加后缀或自行创造新词。
"""
    return base_info


def build_hypothesis_messages_l1(
    struct: StructExtraction,
    query: Query3Levels,
) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_HYP_L1
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("【语言要求（必须满足）】", "【语言要求】")
        prompt = prompt.replace("- 你生成的“假设”内容必须为中文；", "")
        prompt = prompt.replace("- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。", "- 请保留原文语言，不要强制翻译。")
    
    user_content = _build_user_content(struct, query) + "\n请生成【一级假设】及其总结。"
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def build_hypothesis_messages_l2(
    struct: StructExtraction,
    query: Query3Levels,
) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_HYP_L2
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("【语言要求（必须满足）】", "【语言要求】")
        prompt = prompt.replace("- 你生成的“假设”内容必须为中文；", "")
        prompt = prompt.replace("- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。", "- 请保留原文语言，不要强制翻译。")

    user_content = _build_user_content(struct, query) + "\n请生成【二级假设】及其总结。"
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def build_hypothesis_messages_l3(
    struct: StructExtraction,
    query: Query3Levels,
) -> List[Dict[str, str]]:
    from crossdisc_extractor.config import get_language_mode, LanguageMode

    prompt = SYSTEM_PROMPT_HYP_L3
    if get_language_mode() == LanguageMode.ORIGINAL:
        prompt = prompt.replace("【语言要求（必须满足）】", "【语言要求】")
        prompt = prompt.replace("- 你生成的“假设”内容必须为中文；", "")
        prompt = prompt.replace("- 禁止出现任何英文单词、英文缩写或拉丁字母（A-Z/a-z）。", "- 请保留原文语言，不要强制翻译。")

    user_content = _build_user_content(struct, query) + "\n请生成【三级假设】及其总结。"
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]


def _coerce_flat_steps_to_nested(hdict: dict) -> dict:
    """
    兼容弱模型（如 qwen-turbo）将 "一级": [{step1}, {step2}, {step3}]
    输出为扁平列表而非嵌套列表 "一级": [[{step1}, {step2}, {step3}]] 的情况。
    检测方式：如果列表元素全部是 dict 且含有 "step" 键，则认为是扁平 step 列表。
    """
    if not isinstance(hdict, dict):
        return hdict
    for lvl in ("一级", "二级", "三级"):
        paths = hdict.get(lvl)
        if not isinstance(paths, list) or not paths:
            continue
        # 检测是否为扁平 step 列表（所有元素是 dict 且有 "step" 或 "head" 键）
        if all(isinstance(s, dict) and ("step" in s or "head" in s) for s in paths):
            # 按每 3 个一组切分为路径
            grouped = [paths[i:i+3] for i in range(0, len(paths), 3)]
            hdict[lvl] = [g for g in grouped if len(g) == 3]
            logger.warning("假设.%s 检测到扁平 step 列表，已自动包装为嵌套路径列表", lvl)
    return hdict


def _deterministic_repair_hypothesis_links(hdict: dict) -> dict:
    """
    在 Pydantic 校验前对 3-step 路径做确定性链路对齐（deterministic repair）。
    同时确保每个 step 都有必要的字段（claim, step, head, relation, tail）。
    """
    if not isinstance(hdict, dict):
        return hdict
    # 先修复扁平 step 列表
    hdict = _coerce_flat_steps_to_nested(hdict)
    for lvl in ("一级", "二级", "三级"):
        paths = hdict.get(lvl)
        if not isinstance(paths, list):
            continue
        for path in paths:
            if not isinstance(path, list) or len(path) < 3:
                continue
            
            # 确保每个 step 都是 dict 且包含 claim
            for i, step in enumerate(path):
                if not isinstance(step, dict):
                    # 如果是其他类型（如 str），尝试转换或跳过，但通常这里是 dict
                    continue
                if "claim" not in step:
                    step["claim"] = ""  # 补全缺失字段
                if "step" not in step:
                    step["step"] = i + 1
                if "head" not in step:
                    step["head"] = ""
                if "relation" not in step:
                    step["relation"] = ""
                if "tail" not in step:
                    step["tail"] = ""

            s1, s2, s3 = path[0], path[1], path[2]
            if isinstance(s1, dict) and isinstance(s2, dict):
                t1 = (s1.get("tail") or "").strip()
                if t1:
                    s2["head"] = t1
            if isinstance(s2, dict) and isinstance(s3, dict):
                t2 = (s2.get("tail") or "").strip()
                if t2:
                    s3["head"] = t2
    return hdict


def parse_partial_hypothesis(
    text: str,
    level: int,
    struct: Optional[StructExtraction] = None,
) -> Dict[str, Any]:
    """
    解析 partial output，返回字典，例如 {"一级": [...], "一级总结": [...]}
    """
    try:
        obj = coerce_json_object(text, required_top_keys={"假设"})
    except ValueError:
        # JSON 解析失败，尝试不带 required_top_keys 再解析一次
        try:
            obj = coerce_json_object(text)
        except ValueError:
            # 彻底失败，尝试用正则提取 step 结构做降级处理
            obj = _fallback_extract_steps_from_text(text, level)
            if obj is None:
                raise ValueError(f"假设 L{level} 生成输出无法解析为合法 JSON")

    if not isinstance(obj, dict) or "假设" not in obj:
        # 宽容处理：如果 LLM 忘了包 "假设"，直接看顶层
        if isinstance(obj, dict) and (f"{level_map[level]}" in obj):
            hyp_dict = obj
        else:
            # 再尝试把整个 obj 当作假设内容
            hyp_dict = {"假设": obj} if isinstance(obj, dict) else {}
            if level_map[level] not in hyp_dict:
                hyp_dict = obj if isinstance(obj, dict) else {}
    else:
        hyp_dict = obj["假设"]

    if not isinstance(hyp_dict, dict):
        hyp_dict = {}

    # 确定性修复
    hyp_dict = _deterministic_repair_hypothesis_links(hyp_dict)
    
    # 构造一个临时的 Hypothesis3Levels 用于复用清洗逻辑
    # 注意：我们只填充当前 level，其他留空
    h_temp = Hypothesis3Levels()
    
    key_path = level_map[level]       # e.g. "一级"
    key_summ = f"{level_map[level]}总结" # e.g. "一级总结"

    if key_path in hyp_dict:
        # 手动赋值给 model，需确保转换为对象，否则后续处理（如 ensure_hypothesis_summaries）会报错
        raw_paths = hyp_dict.get(key_path) or []
        obj_paths = []
        if isinstance(raw_paths, list):
            for path in raw_paths:
                if not isinstance(path, list):
                    continue
                path_objs = []
                for i, step in enumerate(path):
                    if isinstance(step, dict):
                        # 强力修复 claim：若为空，用三元组拼接
                        claim_val = str(step.get("claim", "")).strip()
                        if not claim_val:
                            h = str(step.get("head", "")).strip()
                            r = str(step.get("relation", "")).strip()
                            t = str(step.get("tail", "")).strip()
                            claim_val = f"{h} {r} {t}".strip()
                            step["claim"] = claim_val

                        try:
                            # 尝试标准转换
                            s_obj = HypothesisStep(**step)
                        except Exception:
                            # 兜底：强制构造
                            s_obj = HypothesisStep.model_construct(
                                step=step.get("step", i + 1),
                                head=step.get("head", ""),
                                relation=step.get("relation", ""),
                                tail=step.get("tail", ""),
                                claim=step.get("claim", "")
                            )
                        path_objs.append(s_obj)
                    elif isinstance(step, HypothesisStep):
                        if not step.claim:
                             step.claim = f"{step.head} {step.relation} {step.tail}"
                        path_objs.append(step)
                
                # 过滤掉不完整的路径（必须恰好 3 步）
                if len(path_objs) == 3:
                    obj_paths.append(path_objs)

        setattr(h_temp, key_path, obj_paths)
        setattr(h_temp, key_summ, hyp_dict.get(key_summ) or [])

    # 执行清洗
    # Note: ensure_hypothesis_chinese handles all levels present in h_temp
    # collect_latin_positions checks all levels
    
    # Before cleaning, we might need to cast lists to proper types if they are dicts
    # But ensure_hypothesis_chinese iterates over them. 
    # Actually, coerce_json_object returns dicts/lists of primitives.
    # We should convert them to HypothesisStep objects first?
    # No, ensure_hypothesis_chinese expects Hypothesis3Levels object which has Pydantic models inside.
    
    # So we MUST create a valid Hypothesis3Levels object.
    # The safest way is to use model_validate with the partial dict, as missing fields get defaults.
    try:
        h_temp = Hypothesis3Levels.model_validate(hyp_dict)
    except Exception:
        # If strict validation fails (e.g. alignment checks in model_validator), 
        # we might need to bypass it or construct it manually.
        # Hypothesis3Levels has _enforce_three_step_chain validator.
        # It also has _check_alignment validator? No, that's in Extraction.
        # Hypothesis3Levels only checks internal structure.
        
        # If model_validate fails, we try to construct manually
        # But for now let's assume LLM output is structurally correct enough or we catch error
        pass

    # Re-construct if model_validate failed or just to be safe with partial data
    # Actually, we can just use the Pydantic model we created above?
    # No, we need to populate it.
    
    # Let's trust model_validate for the partial dict. 
    # Since other levels are missing in hyp_dict, they will be empty lists in h_temp, which is valid.
    
    h_temp = ensure_hypothesis_summaries(h_temp) # Align summaries
    
    # Cleaning
    if _collect_latin_positions(h_temp):
        h_temp = ensure_hypothesis_chinese(h_temp, struct=struct)
        
    # Extract back the cleaned data
    return {
        key_path: getattr(h_temp, key_path),
        key_summ: getattr(h_temp, key_summ)
    }

level_map = {1: "一级", 2: "二级", 3: "三级"}


def _fallback_extract_steps_from_text(text: str, level: int) -> Optional[Dict]:
    """
    降级方案：当 JSON 整体不合法时，用正则逐个提取 step dict，
    按每 3 个一组组装为路径，构造出最小可用的假设结构。
    """
    import re as _re
    step_pattern = _re.compile(
        r'\{\s*"step"\s*:\s*\d.*?\}',
        _re.DOTALL
    )
    matches = step_pattern.findall(text)
    if not matches:
        return None

    steps = []
    for m in matches:
        try:
            d = json.loads(m)
            if isinstance(d, dict) and "step" in d:
                steps.append(d)
        except Exception:
            continue

    if not steps:
        return None

    # 按每 3 个一组切分为路径
    paths = [steps[i:i+3] for i in range(0, len(steps), 3)]
    paths = [p for p in paths if len(p) == 3]

    if not paths:
        return None

    key = level_map[level]
    logger.warning("假设 L%d JSON 不合法，降级提取到 %d 条路径", level, len(paths))
    return {
        "假设": {
            key: paths,
            f"{key}总结": []
        }
    }

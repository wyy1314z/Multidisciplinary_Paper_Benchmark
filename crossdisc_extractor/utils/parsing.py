# crossdisc_extractor/utils/parsing.py
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from crossdisc_extractor.schemas import HypothesisStep, Hypothesis3Levels

logger = logging.getLogger("crossdisc.parsing")


def strip_code_fences(s: str) -> str:
    s = re.sub(r"^```(?:json)?\s*", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s.strip())
    return s.strip()


def _extract_first_balanced_json_object(s: str) -> Optional[str]:
    """从文本中提取第一个“括号配平”的 JSON 对象字符串（以 '{' 开头，以配平的 '}' 结束）。

    - 忽略字符串字面量中的花括号；
    - 支持输出前后夹杂说明文字、日志等（只要中间有完整 JSON 对象）；
    - 若未找到完整对象则返回 None（常见于模型输出被截断）。
    """
    if not isinstance(s, str):
        return None

    start = s.find("{")
    if start < 0:
        return None

    in_str = False
    esc = False
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":  # escape
                esc = True
            elif ch == '"':
                in_str = False
            continue

        # not in string
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
            continue

    # 走到末尾仍未配平：大概率输出被截断
    return None


def coerce_json_object(text: str, required_top_keys: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    尝试从模型输出中“捞出”一个 JSON 对象。

    - required_top_keys=None：只要能解析成 dict 就接受；
    - required_top_keys=集合：必须满足这些顶层键都存在（用于多阶段输出的强约束）。

    注意：不要在这里做结构层面的“严格校验”（那是 Pydantic 的职责），
    这里只做“尽最大努力提取 JSON 对象”与“可选的顶层键存在性检查”。
    """
    if not isinstance(text, str):
        raise ValueError("模型返回内容不是字符串")
    s = strip_code_fences(text)

    def ok_keys(obj: Dict[str, Any]) -> bool:
        if required_top_keys is None:
            return True
        return all(k in obj for k in required_top_keys)

    def try_parse(candidate: str):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and ok_keys(obj):
                return obj
        except Exception:
            return None
        return None

    # 1) 直接尝试解析（模型恰好只输出 JSON）
    direct = try_parse(s.strip())
    if direct is not None:
        return direct

    # 2) 对常见标点做轻微归一化再试
    candidate = (
        s.strip()
        .replace("\ufeff", "")
        .replace("，", ",")
        .replace("：", ":")
        .replace("“", "\"")
        .replace("”", "\"")
    )
    direct2 = try_parse(candidate)
    if direct2 is not None:
        return direct2

    # 3) 提取第一个“配平”的 JSON 对象并解析（最稳健的提取方式）
    obj_str = _extract_first_balanced_json_object(candidate)
    if obj_str is not None:
        parsed = try_parse(obj_str)
        if parsed is not None:
            return parsed

    # 4) 退而求其次：如果存在 '}'，尝试从第一个 '{' 截取到最后一个 '}'（处理尾随文本）
    last = candidate.rfind("}")
    first = candidate.find("{")
    if first >= 0 and last > first:
        parsed = try_parse(candidate[first : last + 1])
        if parsed is not None:
            return parsed

    # 5) 仍失败：输出很可能被截断或包含未转义引号等导致 JSON 非法
    snippet = candidate[:400]
    if "{" in candidate and "}" not in candidate:
        logger.error("无法提取完整 JSON：疑似模型输出被截断（缺少闭合 '}'）。原始前 400 字符: %r", snippet)
        raise ValueError("无法从模型输出中提取合法 JSON 对象：疑似输出被截断")
    logger.error("无法从模型输出中提取合法 JSON 对象，原始内容前 400 字符: %r", snippet)
    raise ValueError("无法从模型输出中提取合法 JSON 对象")


# ------------------ 假设总结：只补齐，不覆盖（并强化“路径一致性总结”） ------------------


def _shorten(s: str, max_len: int = 80) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip() + "..."


def _validate_three_step_chain(path: List[HypothesisStep]) -> bool:
    """
    校验“3-step + head/tail 链式一致性”。
    这里不抛异常，仅用于总结时的防御性处理（硬约束应由 schemas.py 校验）。
    """
    if not isinstance(path, list) or len(path) != 3:
        return False

    # step 编号最好是 1,2,3
    steps = [getattr(x, "step", None) for x in path]
    if steps != [1, 2, 3]:
        return False

    # head/tail 链式一致性
    t1 = (path[0].tail or "").strip()
    h2 = (path[1].head or "").strip()
    t2 = (path[1].tail or "").strip()
    h3 = (path[2].head or "").strip()
    if t1 != h2:
        return False
    if t2 != h3:
        return False

    # 最后一步 claim 必须可用
    if not (path[2].claim or "").strip():
        return False

    return True


def _summary_from_one_path(path: List[HypothesisStep]) -> str:
    """
    从一条完整路径生成总结：
    - 以 step3.claim 为核心（结论/可检验假设）
    - step1/2 的 claim 作为铺垫（压缩），但不引入新事实
    """
    if not path:
        return ""

    # 如果不满足 3-step chain，就退化为“最后一步 claim”
    last_claim = (path[-1].claim or "").strip()
    if not last_claim:
        return ""

    if not _validate_three_step_chain(path):
        return _shorten(last_claim, 120)

    c1 = _shorten(getattr(path[0], "claim", ""), 60)
    c2 = _shorten(getattr(path[1], "claim", ""), 60)
    c3 = last_claim.strip()

    lead = "；".join([x for x in [c1, c2] if x])
    if lead:
        # “铺垫 + 结论”，确保总结仍围绕最后一步结论
        out = f"{lead}；因此，{c3}"
    else:
        out = c3

    return _shorten(out, 200)


def _auto_summaries_from_paths(paths: List[List[HypothesisStep]]) -> List[str]:
    summaries: List[str] = []
    for path in paths or []:
        if not path:
            summaries.append("")
            continue
        summaries.append(_summary_from_one_path(path))
    return summaries


def _merge_summaries(
    paths: List[List[HypothesisStep]],
    existing: Any,
) -> List[str]:
    """
    - existing 可能是 str / list / None；
    - 保留已有的非空总结（按顺序对齐）；注意：不覆盖用户/模型已给出的内容；
    - 若数量少于路径数，则为缺失部分用 _auto_summaries_from_paths 补齐；
    - 若 existing 比路径数更多，则截断到路径数。
    """
    n = len(paths or [])
    if n == 0:
        return []

    if isinstance(existing, str):
        cur = [existing.strip()] if existing.strip() else []
    elif isinstance(existing, list):
        cur = [(str(s) or "").strip() for s in existing]
        # 注意：保留位置，但过滤纯空字符串会导致“错位”，因此只在末尾补齐时处理
        # 这里不直接过滤掉中间空值：用 None 占位更合理
        cur = [s if s else "" for s in cur]
    else:
        cur = []

    # 截断
    if len(cur) > n:
        cur = cur[:n]

    auto = _auto_summaries_from_paths(paths)

    # 对齐补齐：逐位保留已有非空，缺失/空则用 auto
    merged: List[str] = []
    for i in range(n):
        if i < len(cur) and isinstance(cur[i], str) and cur[i].strip():
            merged.append(cur[i].strip())
        else:
            merged.append(auto[i] if i < len(auto) else "")

    return merged


def ensure_hypothesis_summaries(h: Hypothesis3Levels) -> Hypothesis3Levels:
    """
    只补齐，不覆盖：
    - 确保 每个层级的总结列表长度 == 对应层级路径数；
    - 每条总结与该路径一致（以最后一步 claim 为核心，前两步作铺垫）。
    """
    h.一级总结 = _merge_summaries(h.一级, h.一级总结)
    h.二级总结 = _merge_summaries(h.二级, h.二级总结)
    h.三级总结 = _merge_summaries(h.三级, h.三级总结)
    return h

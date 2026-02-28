from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from crossdisc_extractor.schemas import (
    StructExtraction,
    QueryAndBuckets,
    Extraction,
    MetaInfo,
    Hypothesis3Levels,
)
from crossdisc_extractor.utils.llm import chat_completion_with_retry, ModelTransportError, ModelOutputError
from crossdisc_extractor.utils.pdf_utils import fetch_pdf_and_extract_intro
from crossdisc_extractor.prompts.struct_prompt_split import (
    build_concepts_messages,
    parse_concepts_output,
    build_relations_messages,
    parse_relations_output,
)
from crossdisc_extractor.prompts.query_prompt import build_query_messages, parse_query_output
from crossdisc_extractor.prompts.hypothesis_prompt_split import (
    build_hypothesis_messages_l1,
    build_hypothesis_messages_l2,
    build_hypothesis_messages_l3,
    parse_partial_hypothesis,
)
from crossdisc_extractor.graph_builder import build_graph_and_metrics

logger = logging.getLogger("crossdisc.main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ---------------------- 输入解析（与原脚本兼容） ----------------------

def _extract_L1_list(levels_text: str) -> List[str]:
    import re

    pattern = re.compile(r"L1\s*[:：]\s*([^;；\n]+)")
    if not levels_text or not isinstance(levels_text, str):
        return []
    vals = [m.group(1).strip() for m in pattern.finditer(levels_text)]
    out, seen = [], set()
    for v in vals:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _extract_fields(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    尝试从多种字段名中抽取 title / abstract / pdf_url / main_levels / non_main_levels / primary / secondary。
    """
    if not isinstance(obj, dict):
        return None
    title = (obj.get("title") or obj.get("题目") or "").strip()
    abstract = (obj.get("abstract") or obj.get("摘要") or "").strip()
    pdf_url = (obj.get("pdf_url") or obj.get("pdf") or "").strip()

    main_levels = (obj.get("main_levels") or obj.get("主学科层级") or "").strip()
    non_main_levels = (obj.get("non_main_levels") or obj.get("非主学科层级") or "").strip()

    primary = ""
    secondary_list: List[str] = []

    if main_levels:
        l1s = _extract_L1_list(main_levels)
        if l1s:
            primary = l1s[0]

    if non_main_levels:
        secondary_list = _extract_L1_list(non_main_levels)

    if not primary:
        primary = (obj.get("primary_discipline") or obj.get("主学科") or "").strip()

    if not secondary_list:
        sec_raw = (obj.get("secondary_disciplines") or obj.get("辅学科") or "").strip()
        if sec_raw:
            import re

            secondary_list = [s.strip() for s in re.split(r"[;,，]", sec_raw) if s.strip()]

    secondary_str = ", ".join(secondary_list)

    if title and abstract:
        return {
            "title": title,
            "abstract": abstract,
            "pdf_url": pdf_url,
            "primary": primary,
            "secondary": secondary_str,
            "secondary_list": secondary_list,
        }
    return None


def _extract_list_from_container(d: Dict[str, Any]) -> Optional[List[Any]]:
    for key in ("items", "data", "records", "samples"):
        if isinstance(d.get(key), list):
            return d[key]
    return None


def _try_parse_json_container(text: str) -> Optional[List[Dict[str, Any]]]:
    try:
        payload = json.loads(text)
    except Exception:
        return None

    items: List[Dict[str, Any]] = []

    def add(obj: Any):
        rec = _extract_fields(obj)
        if rec:
            items.append(rec)

    if isinstance(payload, list):
        for obj in payload:
            add(obj)
        return items if items else None

    if isinstance(payload, dict):
        found = _extract_list_from_container(payload)
        if isinstance(found, list):
            for obj in found:
                add(obj)
            return items if items else None
        else:
            add(payload)
            if items:
                return items
    return None


def _parse_as_jsonl_text(text: str) -> List[Dict[str, Any]]:
    data: List[Dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception as e:
            raise ValueError(f"作为 JSONL 解析失败：第 {idx} 行无法解析为 JSON：{e}")
        rec = _extract_fields(obj)
        if rec:
            data.append(rec)
    if not data:
        raise ValueError("作为 JSONL 解析后没有获得任何有效记录")
    return data


def load_inputs(path: str) -> List[Dict[str, Any]]:
    lower = path.lower()

    if lower.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        items = _try_parse_json_container(text)
        if items:
            return items
        return _parse_as_jsonl_text(text)

    if lower.endswith(".jsonl"):
        data = []
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except Exception as e:
                    raise ValueError(f"{path} 第 {idx} 行无法解析为 JSON：{e}")
                rec = _extract_fields(obj)
                if rec:
                    data.append(rec)
        if not data:
            raise ValueError(f"{path} 未解析到任何记录")
        return data

    if lower.endswith(".csv"):
        data = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = _extract_fields(row)
                if rec:
                    data.append(rec)
        if not data:
            raise ValueError(f"{path} 未解析到任何记录")
        return data

    raise ValueError("仅支持 .json / .jsonl / .csv 输入")


# ---------------------- 表格化输出（保留你原来的风格） ----------------------

TABULAR_COLUMNS = [
    "title",
    "abstract",
    "introduction",
    "primary",
    "secondary",
    "pdf_url",
    "ok",
    "error",
    # 概念
    "概念.主学科(术语清单)",
    "概念.辅学科(分组-术语清单)",
    # 关系
    "跨学科关系(总数)",
    "跨学科关系(示例前3条)",
    # 分类
    "按辅助学科分类(概念-分组)",
    "按辅助学科分类(关系索引-分组)",
    # 查询/假设
    "查询.一级",
    "查询.二级",
    "查询.三级",
    "假设.一级(路径数)",
    "假设.二级(路径数)",
    "假设.三级(路径数)",
    "假设.一级总结",
    "假设.二级总结",
    "假设.三级总结",
    "raw",
]


def _dict_to_inline_json(d: Dict[str, Any]) -> str:
    try:
        return json.dumps(d, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ""


def _concept_terms_list_from_raw(lst: List[Dict[str, Any]]) -> List[str]:
    terms = []
    for it in lst or []:
        t = (it.get("normalized") or it.get("term") or "").strip()
        if t:
            terms.append(t)
    out, seen = [], set()
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _flatten_record_for_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "title": rec.get("title", ""),
        "abstract": rec.get("abstract", ""),
        "introduction": rec.get("introduction", ""),
        "primary": rec.get("primary", ""),
        "secondary": rec.get("secondary", ""),
        "pdf_url": rec.get("pdf_url", ""),
        "ok": bool(rec.get("ok", False)),
        "error": rec.get("error", ""),
        "概念.主学科(术语清单)": "",
        "概念.辅学科(分组-术语清单)": "",
        "跨学科关系(总数)": "",
        "跨学科关系(示例前3条)": "",
        "按辅助学科分类(概念-分组)": "",
        "按辅助学科分类(关系索引-分组)": "",
        "查询.一级": "",
        "查询.二级": "",
        "查询.三级": "",
        "假设.一级(路径数)": "",
        "假设.二级(路径数)": "",
        "假设.三级(路径数)": "",
        "假设.一级总结": "",
        "假设.二级总结": "",
        "假设.三级总结": "",
        "raw": rec.get("raw", ""),
    }

    parsed = rec.get("parsed") or {}
    if not isinstance(parsed, dict):
        return row

    concepts = parsed.get("概念") or {}
    if isinstance(concepts, dict):
        prim_terms = _concept_terms_list_from_raw(concepts.get("主学科") or [])
        row["概念.主学科(术语清单)"] = " | ".join(prim_terms)

        sec = concepts.get("辅学科") or {}
        sec_terms_map: Dict[str, List[str]] = {}
        if isinstance(sec, dict):
            for k, v in sec.items():
                sec_terms_map[k] = _concept_terms_list_from_raw(v or [])
        row["概念.辅学科(分组-术语清单)"] = _dict_to_inline_json(sec_terms_map)

    rels = parsed.get("跨学科关系") or []
    if isinstance(rels, list):
        row["跨学科关系(总数)"] = len(rels)
        preview = []
        for r in rels[:3]:
            try:
                head = r.get("head", "")
                tail = r.get("tail", "")
                rtype = r.get("relation_type", "")
                rtxt = r.get("relation", "")
                if rtxt:
                    preview.append(f"{head} -{rtype}({rtxt})-> {tail}")
                else:
                    preview.append(f"{head} -{rtype}-> {tail}")
            except Exception:
                continue
        row["跨学科关系(示例前3条)"] = " || ".join(preview)

    cat = parsed.get("按辅助学科分类") or {}
    if isinstance(cat, dict):
        concept_map: Dict[str, List[str]] = {}
        rel_index_map: Dict[str, List[int]] = {}
        for k, v in cat.items():
            if isinstance(v, dict):
                concept_map[k] = v.get("概念") or []
                rel_index_map[k] = v.get("关系") or []
        row["按辅助学科分类(概念-分组)"] = _dict_to_inline_json(concept_map)
        row["按辅助学科分类(关系索引-分组)"] = _dict_to_inline_json(rel_index_map)

    q = parsed.get("查询") or {}
    if isinstance(q, dict):
        row["查询.一级"] = q.get("一级", "") or ""
        row["查询.二级"] = " | ".join(q.get("二级", []) or [])
        row["查询.三级"] = " | ".join(q.get("三级", []) or [])

    h = parsed.get("假设") or {}
    if isinstance(h, dict):
        for lvl, col in [("一级", "假设.一级(路径数)"), ("二级", "假设.二级(路径数)"), ("三级", "假设.三级(路径数)")]:
            paths = h.get(lvl) or []
            if isinstance(paths, list):
                row[col] = len(paths)

        def _join_summary(val) -> str:
            if isinstance(val, list):
                return " | ".join(str(s) for s in val)
            if isinstance(val, str):
                return val
            return ""

        row["假设.一级总结"] = _join_summary(h.get("一级总结", []))
        row["假设.二级总结"] = _join_summary(h.get("二级总结", []))
        row["假设.三级总结"] = _join_summary(h.get("三级总结", []))

    return row


def write_outputs(output_path: str, records: List[Dict[str, Any]]) -> None:
    lower = output_path.lower()

    if lower.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as wf:
            json.dump(records, wf, ensure_ascii=False, indent=2)
        return

    if lower.endswith(".jsonl"):
        with open(output_path, "w", encoding="utf-8") as wf:
            for rec in records:
                wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return

    if lower.endswith(".csv"):
        rows = [_flatten_record_for_row(r) for r in records]
        with open(output_path, "w", encoding="utf-8", newline="") as wf:
            writer = csv.DictWriter(
                wf,
                fieldnames=TABULAR_COLUMNS,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
        return

    if lower.endswith(".xlsx"):
        try:
            import pandas as _pd  # type: ignore
        except Exception:
            raise RuntimeError("写入 .xlsx 需要 pandas：请先 `pip install pandas`")
        rows = [_flatten_record_for_row(r) for r in records]
        df = _pd.DataFrame(rows, columns=TABULAR_COLUMNS)
        df.to_excel(output_path, index=False)
        return

    raise ValueError("输出仅支持 .json / .jsonl / .csv / .xlsx")


def write_single_output(output_path: str, record: Dict[str, Any]) -> None:
    lower = output_path.lower()

    if lower.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as wf:
            json.dump(record, wf, ensure_ascii=False, indent=2)
        return
    if lower.endswith(".jsonl"):
        with open(output_path, "a", encoding="utf-8") as wf:
            wf.write(json.dumps(record, ensure_ascii=False) + "\n")
        return
    if lower.endswith(".csv"):
        file_exists = os.path.isfile(output_path)
        row = _flatten_record_for_row(record)
        with open(output_path, "a", encoding="utf-8", newline="") as wf:
            writer = csv.DictWriter(
                wf,
                fieldnames=TABULAR_COLUMNS,
                extrasaction="ignore",
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        return
    if lower.endswith(".xlsx"):
        try:
            import pandas as _pd  # type: ignore
        except Exception:
            raise RuntimeError("写入 .xlsx 需要 pandas：请先 `pip install pandas`")
        row = _flatten_record_for_row(record)
        if os.path.isfile(output_path):
            try:
                old = _pd.read_excel(output_path, dtype=str)
            except Exception:
                old = _pd.DataFrame(columns=TABULAR_COLUMNS)
            new = _pd.concat([old, _pd.DataFrame([row])], ignore_index=True)
            for col in TABULAR_COLUMNS:
                if col not in new.columns:
                    new[col] = ""
            new = new[TABULAR_COLUMNS]
            new.to_excel(output_path, index=False)
        else:
            _pd.DataFrame([row], columns=TABULAR_COLUMNS).to_excel(
                output_path, index=False
            )
        return
    raise ValueError("输出仅支持 .json / .jsonl / .csv / .xlsx")


# ---------------------- 三阶段 LLM 调用 ----------------------


def run_pipeline_for_item(
    title: str,
    abstract: str,
    primary: str,
    secondary_list: List[str],
    pdf_url: str,
    temperature_struct: float = 0.2,
    temperature_query: float = 0.2,
    temperature_hyp: float = 0.3,
    seed: Optional[int] = 42,
    max_tokens_struct: int = 4096,
    max_tokens_query: int = 4096,
    max_tokens_hyp: int = 4096,
    language_mode: str = "chinese",
) -> Tuple[Extraction, str, str]:
    """
    核心多阶段 pipeline：
    1) struct: meta + 概念 + 跨学科关系
    2) query: 按辅助学科分类 + 查询
    3) hyp:   假设 (知识路径 + 总结)
    """
    from crossdisc_extractor.config import set_language_mode
    set_language_mode(language_mode)

    introduction = ""
    if pdf_url:
        introduction = fetch_pdf_and_extract_intro(pdf_url) or ""

    # Stage 1: Concepts
    messages_concepts = build_concepts_messages(
        title=title,
        abstract=abstract,
        introduction=introduction,
        primary=primary,
        secondary_list=secondary_list,
    )
    raw_concepts = chat_completion_with_retry(
        messages_concepts,
        temperature=temperature_struct,
        seed=seed,
        max_tokens=max_tokens_struct,
    )
    concepts_obj = parse_concepts_output(raw_concepts)

    # Stage 2: Relations
    messages_relations = build_relations_messages(
        title=title,
        abstract=abstract,
        introduction=introduction,
        primary=primary,
        secondary_list=secondary_list,
        concepts_obj=concepts_obj,
    )
    raw_relations = chat_completion_with_retry(
        messages_relations,
        temperature=temperature_struct,
        seed=(None if seed is None else seed + 1),
        max_tokens=max_tokens_struct,
    )
    relations_list = parse_relations_output(raw_relations)

    # Assemble StructExtraction
    struct = StructExtraction(
        meta=concepts_obj["meta"],
        概念=concepts_obj["概念"],
        跨学科关系=relations_list,
    )
    
    # Concatenate raw output for debugging
    raw_struct = (
        "/* concepts */\n" + raw_concepts + 
        "\n\n/* relations */\n" + raw_relations
    )

    # Stage 2
    messages_query = build_query_messages(struct)
    raw_query = chat_completion_with_retry(
        messages_query,
        temperature=temperature_query,
        seed=(None if seed is None else seed + 1),
        max_tokens=max_tokens_query,
    )
    qa = parse_query_output(raw_query)

    # Stage 3: Hypothesis (Split into L1, L2, L3)
    # L1
    messages_hyp_l1 = build_hypothesis_messages_l1(struct, qa.查询)
    raw_hyp_l1 = chat_completion_with_retry(
        messages_hyp_l1,
        temperature=temperature_hyp,
        seed=(None if seed is None else seed + 2),
        max_tokens=max_tokens_hyp,
    )
    hyp_l1_dict = parse_partial_hypothesis(raw_hyp_l1, level=1, struct=struct)

    # L2
    messages_hyp_l2 = build_hypothesis_messages_l2(struct, qa.查询)
    raw_hyp_l2 = chat_completion_with_retry(
        messages_hyp_l2,
        temperature=temperature_hyp,
        seed=(None if seed is None else seed + 3),
        max_tokens=max_tokens_hyp,
    )
    hyp_l2_dict = parse_partial_hypothesis(raw_hyp_l2, level=2, struct=struct)

    # L3
    messages_hyp_l3 = build_hypothesis_messages_l3(struct, qa.查询)
    raw_hyp_l3 = chat_completion_with_retry(
        messages_hyp_l3,
        temperature=temperature_hyp,
        seed=(None if seed is None else seed + 4),
        max_tokens=max_tokens_hyp,
    )
    hyp_l3_dict = parse_partial_hypothesis(raw_hyp_l3, level=3, struct=struct)

    # Assemble
    hyp_args = {}
    hyp_args.update(hyp_l1_dict)
    hyp_args.update(hyp_l2_dict)
    hyp_args.update(hyp_l3_dict)
    hyp = Hypothesis3Levels(**hyp_args)

    # 聚合为最终 Extraction
    meta = struct.meta
    final = Extraction(
        meta=meta,
        概念=struct.概念,
        跨学科关系=struct.跨学科关系,
        按辅助学科分类=qa.按辅助学科分类,
        查询=qa.查询,
        假设=hyp,
    )
    
    # Stage 4: Build Graph & Metrics
    final = build_graph_and_metrics(final)

    # 把三个阶段的原始输出拼在一起（方便调试）
    raw_all = (
        "/* stage1: struct */\n"
        + raw_struct
        + "\n\n/* stage2: query */\n"
        + raw_query
        + "\n\n/* stage3: hypothesis L1 */\n"
        + raw_hyp_l1
        + "\n\n/* stage3: hypothesis L2 */\n"
        + raw_hyp_l2
        + "\n\n/* stage3: hypothesis L3 */\n"
        + raw_hyp_l3
    )

    return final, raw_all, introduction


# ---------------------- 串行/并行调度 ----------------------


def _process_one_item(
    idx: int,
    total: int,
    it: Dict[str, Any],
    sleep_s: float = 0.0,
    max_tokens_struct: int = 12000,
    max_tokens_query: int = 12000,
    max_tokens_hyp: int = 12000,
    language_mode: str = "chinese",
) -> Tuple[int, Dict[str, Any], bool]:
    title, abstract = it["title"], it["abstract"]
    pdf_url = it.get("pdf_url", "")
    primary = it.get("primary", "")
    secondary = it.get("secondary", "")
    secondary_list = it.get("secondary_list", [])

    rec: Dict[str, Any] = {
        "title": title,
        "abstract": abstract,
        "pdf_url": pdf_url,
        "primary": primary,
        "secondary": secondary,
        "secondary_list": secondary_list,
        "introduction": "",
    }

    ok_flag = False
    try:
        result, raw, introduction = run_pipeline_for_item(
            title=title,
            abstract=abstract,
            primary=primary,
            secondary_list=secondary_list,
            pdf_url=pdf_url,
            max_tokens_struct=max_tokens_struct,
            max_tokens_query=max_tokens_query,
            max_tokens_hyp=max_tokens_hyp,
        )
        rec["introduction"] = introduction
        rec["parsed"] = result.model_dump()
        rec["raw"] = raw
        rec["ok"] = True
        rec["error"] = ""
        ok_flag = True
    except (ModelTransportError, ModelOutputError, Exception) as e:
        logger.warning(f"[{idx}/{total}] 记录处理失败：{e}")
        rec["parsed"] = None
        rec["raw"] = ""
        rec["ok"] = False
        rec["error"] = str(e)

    if sleep_s > 0:
        time.sleep(sleep_s)

    return idx, rec, ok_flag


def run_benchmark(
    input_path: str,
    output_path: str,
    max_items: Optional[int] = None,
    sleep_s: float = 0.0,
    num_workers: int = 1,
    max_tokens_struct: int = 8192,
    max_tokens_query: int = 4096,
    max_tokens_hyp: int = 4096,
    language_mode: str = "chinese",
):
    items = load_inputs(input_path)
    if max_items is not None:
        items = items[:max_items]

    total = len(items)
    logger.info(f"开始处理 {total} 条记录... (num_workers={num_workers}, language_mode={language_mode})")

    if total == 0:
        write_outputs(output_path, [])
        logger.info(f"没有记录需要处理，已输出空文件 -> {output_path}")
        return

    if num_workers <= 1:
        ok_cnt = 0
        out_records: List[Dict[str, Any]] = []
        for i, it in enumerate(items, 1):
            idx, rec, ok_flag = _process_one_item(
                i,
                total,
                it,
                sleep_s=sleep_s,
                max_tokens_struct=max_tokens_struct,
                max_tokens_query=max_tokens_query,
                max_tokens_hyp=max_tokens_hyp,
                language_mode=language_mode,
            )
            out_records.append(rec)
            if ok_flag:
                ok_cnt += 1
            if i % 10 == 0 or i == total:
                logger.info(f"[{i}/{total}] 当前成功 {ok_cnt}")
        write_outputs(output_path, out_records)
        logger.info(
            f"完成：总计 {total}，成功 {ok_cnt}，失败 {total - ok_cnt}。输出 -> {output_path}"
        )
        return

    out_records: List[Optional[Dict[str, Any]]] = [None] * total
    ok_cnt = 0
    processed = 0
    max_workers = max(1, min(num_workers, total))

    logger.info(f"使用 ThreadPoolExecutor 并行处理，max_workers={max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_one_item,
                i,
                total,
                it,
                sleep_s,
                max_tokens_struct,
                max_tokens_query,
                max_tokens_hyp,
            ): i
            for i, it in enumerate(items, 1)
        }

        for future in as_completed(futures):
            try:
                idx, rec, ok_flag = future.result()
            except Exception as e:
                idx = futures[future]
                rec = {
                    "title": items[idx - 1].get("title", ""),
                    "abstract": items[idx - 1].get("abstract", ""),
                    "pdf_url": items[idx - 1].get("pdf_url", ""),
                    "primary": items[idx - 1].get("primary", ""),
                    "secondary": items[idx - 1].get("secondary", ""),
                    "secondary_list": items[idx - 1].get("secondary_list", []),
                    "introduction": "",
                    "parsed": None,
                    "raw": "",
                    "ok": False,
                    "error": f"并行执行异常: {e}",
                }
                ok_flag = False
                logger.warning(f"[{idx}/{total}] 并行执行异常：{e}")

            out_records[idx - 1] = rec
            processed += 1
            if ok_flag:
                ok_cnt += 1
            if processed % 10 == 0 or processed == total:
                logger.info(f"[{processed}/{total}] 当前成功 {ok_cnt}")

    final_records = [
        r if r is not None else {"ok": False, "error": "内部错误：记录缺失"}
        for r in out_records
    ]

    write_outputs(output_path, final_records)
    logger.info(
        f"完成：总计 {total}，成功 {ok_cnt}，失败 {total - ok_cnt}。输出 -> {output_path}"
    )


def _format_paths(paths: List[List[Dict[str, Any]]]) -> str:
    """将假设路径列表格式化为易读字符串"""
    if not paths:
        return ""
    lines = []
    for i, path in enumerate(paths, 1):
        lines.append(f"[Path {i}]")
        for step in path:
            s_idx = step.get("step")
            claim = step.get("claim", "")
            lines.append(f"  Step {s_idx}: {claim}")
    return "\n".join(lines)


def handle_export(input_path: str, output_path: str):
    """从结构化结果中提取学科、Query、假设内容并导出"""
    if not os.path.exists(input_path):
        logger.error(f"输入文件不存在: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"正在处理 {len(data)} 条记录...")
    rows = []
    for item in data:
        # 跳过处理失败的记录
        if not item.get("ok") or not item.get("parsed"):
            continue

        parsed = item["parsed"]
        meta = parsed.get("meta", {})
        query = parsed.get("查询", {})
        hyp = parsed.get("假设", {})

        # 学科
        primary = meta.get("primary", "")
        secondary = ", ".join(meta.get("secondary_list", []))

        # Query
        q1 = query.get("一级", "")
        q2 = "; ".join(query.get("二级", []))
        q3 = "; ".join(query.get("三级", []))

        # Hypothesis
        # 优先使用总结，如果没有则格式化路径
        h1_sum = "; ".join(hyp.get("一级总结", []))
        h1_paths = _format_paths(hyp.get("一级", []))
        h1 = h1_sum if h1_sum else h1_paths

        h2_sum = "; ".join(hyp.get("二级总结", []))
        h2_paths = _format_paths(hyp.get("二级", []))
        h2 = h2_sum if h2_sum else h2_paths

        h3_sum = "; ".join(hyp.get("三级总结", []))
        h3_paths = _format_paths(hyp.get("三级", []))
        h3 = h3_sum if h3_sum else h3_paths

        rows.append({
            "title": item.get("title", ""),
            "primary_discipline": primary,
            "secondary_disciplines": secondary,
            "L1_query": q1,
            "L2_queries": q2,
            "L3_queries": q3,
            "L1_hypotheses": h1,
            "L2_hypotheses": h2,
            "L3_hypotheses": h3
        })

    # 导出 CSV
    if output_path.endswith(".csv"):
        keys = [
            "title", "primary_discipline", "secondary_disciplines",
            "L1_query", "L2_queries", "L3_queries",
            "L1_hypotheses", "L2_hypotheses", "L3_hypotheses"
        ]
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
    # 导出 JSON
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

    logger.info(f"导出完成: {len(rows)} 条记录 -> {output_path}")


# ---------------------- CLI ----------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "跨学科论文：三阶段 LLM（结构抽取 + 分类/查询 + 知识路径假设）生成器"
        )
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    one = sub.add_parser("one", help="处理单条")
    one.add_argument("--title", required=True, help="论文题目")
    one.add_argument("--abstract", required=True, help="论文摘要")
    one.add_argument(
        "--primary",
        default="",
        help="主学科（可选；若提供 main_levels 则以 main_levels 的 L1 为准）",
    )
    one.add_argument(
        "--secondary",
        default="",
        help="辅学科，逗号/分号/中文逗号分隔（可选；若提供 non_main_levels 则以其中所有 L1 为准）",
    )
    one.add_argument(
        "--pdf-url",
        default="",
        help="论文 PDF 链接（可选；用于自动抽取 Introduction）",
    )
    one.add_argument("--language-mode", choices=["chinese", "original"], default="chinese", help="输出语言模式：chinese=强制中文，original=保留原文")
    one.add_argument("--max-tokens-struct", type=int, default=8192, help="Stage1(struct) 最大生成 token（避免输出截断）")
    one.add_argument("--max-tokens-query", type=int, default=4096, help="Stage2(query) 最大生成 token")
    one.add_argument("--max-tokens-hyp", type=int, default=4096, help="Stage3(hypothesis) 最大生成 token")
    one.add_argument(
        "--show-raw",
        action="store_true",
        help="显示三个阶段的模型原始响应",
    )
    one.add_argument(
        "--main-levels",
        default="",
        help="如：L1:生物学; L2:生物物理学; L3:生物工程",
    )
    one.add_argument(
        "--non-main-levels",
        default="",
        help="如：L1:物理学; L2:光学; L1:计算机科学技术; L2:人工智能",
    )
    one.add_argument("--output", help="可选：输出到 .json/.jsonl/.csv/.xlsx 文件")

    bat = sub.add_parser("batch", help="批量处理（CSV/JSONL/JSON）")
    bat.add_argument(
        "--input",
        required=True,
        help="输入文件： .json / .jsonl / .csv（字段 title/abstract，建议包含 pdf_url/main_levels/non_main_levels）",
    )
    bat.add_argument(
        "--output",
        required=True,
        help="输出路径：.json/.jsonl/.csv/.xlsx",
    )
    bat.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="最多处理多少条（可用于抽样）",
    )
    bat.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="每条之间的休眠秒数（限速时使用）",
    )
    bat.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="并行 worker 数量，默认 1（串行）；建议根据 API 限流设置为 2-4",
    )
    bat.add_argument("--language-mode", choices=["chinese", "original"], default="chinese", help="输出语言模式：chinese=强制中文，original=保留原文")
    bat.add_argument("--max-tokens-struct", type=int, default=12000, help="Stage1(struct) 最大生成 token（避免输出截断）")
    bat.add_argument("--max-tokens-query", type=int, default=12000, help="Stage2(query) 最大生成 token")
    bat.add_argument("--max-tokens-hyp", type=int, default=12000, help="Stage3(hypothesis) 最大生成 token")

    exp = sub.add_parser("export", help="导出摘要信息（CSV/JSON）")
    exp.add_argument("--input", required=True, help="结构化结果 JSON 文件")
    exp.add_argument("--output", required=True, help="导出路径 (.csv/.json)")

    return p


def main():
    parser = build_argparser()
    args = parser.parse_args()

    if args.cmd == "one":
        primary = args.primary
        secondary_list = []
        if getattr(args, "secondary", ""):
            import re

            secondary_list = [
                s.strip() for s in re.split(r"[;,，]", args.secondary or "") if s.strip()
            ]
        if args.main_levels:
            l1s = _extract_L1_list(args.main_levels)
            if l1s:
                primary = l1s[0]
        if args.non_main_levels:
            secondary_list = _extract_L1_list(args.non_main_levels)

        try:
            result, raw_all, introduction = run_pipeline_for_item(
                title=args.title,
                abstract=args.abstract,
                primary=primary,
                secondary_list=secondary_list,
                pdf_url=args.pdf_url,
                max_tokens_struct=args.max_tokens_struct,
                max_tokens_query=args.max_tokens_query,
                max_tokens_hyp=args.max_tokens_hyp,
                language_mode=args.language_mode,
            )
            packed = {
                "title": args.title,
                "abstract": args.abstract,
                "primary": primary,
                "secondary": ", ".join(secondary_list),
                "secondary_list": secondary_list,
                "pdf_url": args.pdf_url,
                "introduction": introduction,
                "parsed": result.model_dump(),
                "raw": raw_all,
                "ok": True,
                "error": "",
            }
        except Exception as e:
            packed = {
                "title": args.title,
                "abstract": args.abstract,
                "primary": primary,
                "secondary": ", ".join(secondary_list),
                "secondary_list": secondary_list,
                "pdf_url": args.pdf_url,
                "introduction": "",
                "parsed": None,
                "raw": "",
                "ok": False,
                "error": str(e),
            }

        if args.output:
            write_single_output(args.output, packed)
            print(f"已写出 -> {args.output}")
        else:
            if packed["ok"]:
                print(json.dumps(packed["parsed"], ensure_ascii=False, indent=2))
                if args.show_raw:
                    print("\n--- raw model output (3 stages) ---\n")
                    print(packed["raw"])
            else:
                print(json.dumps(packed, ensure_ascii=False, indent=2), file=sys.stderr)
                sys.exit(1)

    elif args.cmd == "batch":
        run_benchmark(
            input_path=args.input,
            output_path=args.output,
            max_items=args.max_items,
            sleep_s=args.sleep,
            num_workers=args.num_workers,
            max_tokens_struct=args.max_tokens_struct,
            max_tokens_query=args.max_tokens_query,
            max_tokens_hyp=args.max_tokens_hyp,
            language_mode=args.language_mode,
        )
    elif args.cmd == "export":
        handle_export(args.input, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

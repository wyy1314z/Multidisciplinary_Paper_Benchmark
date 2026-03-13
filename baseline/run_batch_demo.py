#!/usr/bin/env python3
"""
baseline/run_batch_demo.py

批量运行：多篇论文 × (6 baseline + P1–P5) 对比，后台友好。

流程：
  对每篇论文:
    1) 运行 CrossDisc 完整管线 → 得到 Extraction（含概念/关系/查询/假设）
    2) 用 Extraction 中的结构化数据驱动 P1–P5 五级 prompt 生成假设
    3) 运行 6 个外部 baseline（IdeaBench / VanillaLLM / AI-Scientist / SciMON / MOOSE-Chem / SciAgents）

用法:
    # 默认: 6篇论文 × 11种方法
    nohup python -m baseline.run_batch_demo \
        --output baseline/outputs/batch_results.json \
        > baseline/outputs/batch_run.log 2>&1 &

    # 只跑 P1-P5（不跑外部 baseline）
    nohup python -m baseline.run_batch_demo \
        --baselines P1,P2,P3,P4,P5 \
        > baseline/outputs/batch_run.log 2>&1 &

    # 只跑外部 baseline（不跑 P1-P5）
    nohup python -m baseline.run_batch_demo \
        --baselines IdeaBench,VanillaLLM,AI-Scientist,SciMON,MOOSE-Chem,SciAgents \
        > baseline/outputs/batch_run.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── 复用已有模块 ──────────────────────────────────────────────────────
from baseline.run_single_paper_demo import PROMPTS, run_baseline

# ── P1-P5 所需 ───────────────────────────────────────────────────────
from crossdisc_extractor.prompts.hypothesis_prompt_levels import (
    PromptLevel,
    build_messages,
    build_p5_all_levels,
)

# ── 默认论文集 ────────────────────────────────────────────────────────
ALPHAFOLD_PAPER = {
    "title": "Accurate structure prediction of biomolecular interactions with AlphaFold 3",
    "abstract": (
        "The introduction of AlphaFold 2 has spurred a revolution in modelling "
        "the structure of proteins and their interactions, enabling a huge range "
        "of applications in protein modelling and design. Here we describe our "
        "AlphaFold 3 model with a substantially updated diffusion-based "
        "architecture that is capable of predicting the joint structure of "
        "complexes including proteins, nucleic acids, small molecules, ions and "
        "modified residues. The new AlphaFold model demonstrates substantially "
        "improved accuracy over many previous specialized tools: far greater "
        "accuracy for protein-ligand interactions compared with state-of-the-art "
        "docking tools, much higher accuracy for protein-nucleic acid "
        "interactions compared with nucleic-acid-specific predictors and "
        "substantially higher antibody-antigen prediction accuracy compared with "
        "AlphaFold-Multimer v.2.3. Together, these results show that "
        "high-accuracy modelling across biomolecular space is possible within a "
        "single unified deep-learning framework."
    ),
    "primary_discipline": "Computational Biology",
    "secondary_disciplines": ["Biochemistry", "Machine Learning", "Structural Biology"],
}

# 所有支持的方法名
ALL_EXTERNAL_BASELINES = list(PROMPTS.keys())  # IdeaBench, VanillaLLM, ...
ALL_PROMPT_LEVELS = ["P1", "P2", "P3", "P4", "P5"]
ALL_METHODS = ALL_EXTERNAL_BASELINES + ALL_PROMPT_LEVELS


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# =====================================================================
#  论文加载
# =====================================================================

def load_paper_from_jsonl(input_path: str, index: int) -> Dict[str, Any]:
    """从 paper_1.json (JSONL) 加载一篇论文并统一格式。"""
    with open(input_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == index:
                raw = json.loads(line.strip())
                disc_str = raw.get("main_discipline", "")
                primary = ""
                secondaries = []
                if disc_str:
                    cleaned = disc_str.strip()
                    if cleaned.startswith("[") and cleaned.endswith("]"):
                        cleaned = cleaned[1:-1]
                    parts = re.findall(r"\[([^\]]+)\]", cleaned)
                    if parts:
                        primary = parts[0].strip()
                        secondaries = [p.strip() for p in parts[1:]]
                    elif cleaned:
                        primary = cleaned
                field_str = raw.get("field", "")
                if field_str and not secondaries:
                    secondaries = [f.strip() for f in field_str.split("|") if f.strip()]
                return {
                    "title": raw["title"],
                    "abstract": raw["abstract"],
                    "primary_discipline": primary,
                    "secondary_disciplines": secondaries,
                }
    raise IndexError(f"paper index {index} out of range")


# =====================================================================
#  CrossDisc Pipeline: 抽取结构化数据（概念/关系/查询）+ P5 假设
# =====================================================================

def run_crossdisc_extraction(paper: dict) -> Tuple[Optional[Any], Optional[dict]]:
    """
    运行 CrossDisc 完整管线，返回 (Extraction 对象, parsed dict)。
    如果失败，返回 (None, None)。
    """
    from crossdisc_extractor.extractor_multi_stage import run_pipeline_for_item

    final, raw_all, introduction = run_pipeline_for_item(
        title=paper["title"],
        abstract=paper["abstract"],
        primary=paper.get("primary_discipline", ""),
        secondary_list=paper.get("secondary_disciplines", []),
        pdf_url="",
    )
    parsed = final.model_dump() if hasattr(final, "model_dump") else {}
    return final, parsed


def format_crossdisc_hypothesis(parsed: dict) -> str:
    """从 parsed dict 中格式化 CrossDisc/P5 假设为展示文本。"""
    hyp_data = parsed.get("假设", {})
    lines = []
    for level, cn_key, sum_key in [("L1", "一级", "一级总结"),
                                    ("L2", "二级", "二级总结"),
                                    ("L3", "三级", "三级总结")]:
        paths = hyp_data.get(cn_key, [])
        summaries = hyp_data.get(sum_key, [])
        for i, path in enumerate(paths):
            lines.append(f"── {level} 假设路径 {i+1} ──")
            if isinstance(path, list):
                for step in path:
                    if isinstance(step, dict):
                        h = step.get("head", step.get("头实体", ""))
                        r = step.get("relation", step.get("关系", ""))
                        tail = step.get("tail", step.get("尾实体", ""))
                        claim = step.get("claim", step.get("科学主张", ""))
                        lines.append(f"  {h} --[{r}]--> {tail}")
                        if claim:
                            lines.append(f"    claim: {claim}")
            summary = summaries[i] if i < len(summaries) else ""
            if summary:
                lines.append(f"  Summary: {summary}")
            lines.append("")
    return "\n".join(lines) if lines else "(empty)"


# =====================================================================
#  P1–P4: 使用 CrossDisc 抽取的结构化数据 + 对应 prompt 级别
# =====================================================================

def run_prompt_level(level_name: str, paper: dict,
                     extraction_parsed: Optional[dict]) -> dict:
    """
    运行 P1–P4 级别的 prompt 假设生成。
    需要从 extraction_parsed 中提取查询/概念/关系。
    """
    from crossdisc_extractor.utils.llm import chat_completion_with_retry

    level = PromptLevel(level_name)
    t0 = time.time()

    # 从 extraction 中提取结构化数据
    if extraction_parsed is None:
        return {
            "method": level_name,
            "ref": f"CrossDisc prompt ablation ({level_name})",
            "desc": f"P-level {level_name}: CrossDisc extraction failed, cannot generate",
            "hypotheses_text": "[ERROR] CrossDisc extraction not available",
            "raw_response": "",
            "elapsed": 0,
        }

    queries = extraction_parsed.get("查询", {})
    l1_query = queries.get("一级", "")
    l2_queries = queries.get("二级", [])
    l3_queries = queries.get("三级", [])

    if not l1_query:
        return {
            "method": level_name,
            "ref": f"CrossDisc prompt ablation ({level_name})",
            "desc": f"P-level {level_name}: no L1 query extracted",
            "hypotheses_text": "[ERROR] No L1 query available from extraction",
            "raw_response": "",
            "elapsed": 0,
        }

    concepts = extraction_parsed.get("概念", {})
    relations = extraction_parsed.get("跨学科关系", [])

    primary = paper.get("primary_discipline", "")
    secondary_list = paper.get("secondary_disciplines", [])

    # 构建 messages
    messages = build_messages(
        level,
        l1_query=l1_query,
        l2_queries=l2_queries if level.value >= "P2" else None,
        l3_queries=l3_queries if level.value >= "P3" else None,
        abstract=paper["abstract"] if level.value >= "P2" else "",
        primary=primary,
        secondary_list=secondary_list,
        concepts=concepts if level.value >= "P3" else None,
        relations=relations if level.value >= "P4" else None,
    )

    try:
        resp = chat_completion_with_retry(messages, temperature=0.7)
        hyp_text = resp.strip()
        raw = resp
    except Exception as e:
        hyp_text = f"[ERROR] {e}"
        raw = str(e)

    elapsed = time.time() - t0

    level_descs = {
        "P1": "仅 L1 查询，无论文信息，自由文本",
        "P2": "+ L2 查询 + abstract + 学科角色",
        "P3": "+ L3 查询 + 概念列表",
        "P4": "+ 跨学科关系，含推理链",
        "P5": "完整结构化管线（3-step 路径）",
    }
    return {
        "method": level_name,
        "ref": f"CrossDisc prompt ablation ({level_name})",
        "desc": level_descs.get(level_name, ""),
        "hypotheses_text": hyp_text,
        "raw_response": raw,
        "elapsed": round(elapsed, 1),
    }


# =====================================================================
#  P5: 用 CrossDisc 管线的结构化假设
# =====================================================================

def make_p5_result(parsed: dict, elapsed: float) -> dict:
    """从 CrossDisc 管线结果中直接构建 P5 结果。"""
    hyp_text = format_crossdisc_hypothesis(parsed)
    return {
        "method": "P5",
        "ref": "CrossDisc full pipeline (P5)",
        "desc": "完整结构化管线（3-step 路径）— 等价于 CrossDisc 输出",
        "hypotheses_text": hyp_text,
        "raw_response": json.dumps(parsed.get("假设", {}), ensure_ascii=False),
        "elapsed": round(elapsed, 1),
    }


# =====================================================================
#  主调度: 对单篇论文运行所有方法
# =====================================================================

def run_all_methods_for_paper(
    paper: dict,
    method_names: List[str],
) -> List[dict]:
    """
    对一篇论文运行所有指定方法。

    方法名包括:
    - 外部 baseline: IdeaBench, VanillaLLM, AI-Scientist, SciMON, MOOSE-Chem, SciAgents
    - P1–P5: CrossDisc prompt 消融级别
    """
    results = []
    extraction_parsed = None
    crossdisc_elapsed = 0.0
    need_extraction = any(m in ALL_PROMPT_LEVELS for m in method_names)

    # ── Step 1: 如果需要 P1-P5，先运行 CrossDisc extraction ──────────
    if need_extraction:
        log("    Running CrossDisc extraction pipeline (for P1-P5)...")
        t0 = time.time()
        try:
            _final, extraction_parsed = run_crossdisc_extraction(paper)
            crossdisc_elapsed = time.time() - t0
            log(f"    CrossDisc extraction done ({crossdisc_elapsed:.1f}s)")
            log(f"      L1 query: {str(extraction_parsed.get('查询', {}).get('一级', ''))[:60]}...")
            l2_count = len(extraction_parsed.get("查询", {}).get("二级", []))
            l3_count = len(extraction_parsed.get("查询", {}).get("三级", []))
            log(f"      L2 queries: {l2_count}, L3 queries: {l3_count}")
        except Exception as e:
            crossdisc_elapsed = time.time() - t0
            log(f"    CrossDisc extraction FAILED ({crossdisc_elapsed:.1f}s): {e}")
            traceback.print_exc()
            extraction_parsed = None

    # ── Step 2: 逐个运行方法 ────────────────────────────────────────
    for name in method_names:
        if name in ALL_PROMPT_LEVELS:
            # P1-P5
            if name == "P5":
                # P5 直接用 CrossDisc 管线输出
                if extraction_parsed:
                    r = make_p5_result(extraction_parsed, crossdisc_elapsed)
                    log(f"    {name} (from extraction) done ({r['elapsed']}s)")
                else:
                    r = {
                        "method": "P5",
                        "ref": "CrossDisc full pipeline (P5)",
                        "desc": "完整结构化管线",
                        "hypotheses_text": "[ERROR] CrossDisc extraction failed",
                        "raw_response": "",
                        "elapsed": 0,
                    }
                    log(f"    {name} SKIPPED (extraction failed)")
            else:
                # P1-P4
                log(f"    Running {name}...")
                r = run_prompt_level(name, paper, extraction_parsed)
                log(f"    {name} done ({r['elapsed']}s)")
            results.append(r)

        elif name in PROMPTS:
            # 外部 baseline
            log(f"    Running {name}...")
            try:
                r = run_baseline(name, PROMPTS[name], paper)
                results.append(r)
                log(f"    {name} done ({r['elapsed']}s)")
            except Exception as e:
                log(f"    {name} FAILED: {e}")
                results.append({
                    "method": name,
                    "ref": PROMPTS[name].get("ref", ""),
                    "desc": PROMPTS[name].get("desc", ""),
                    "hypotheses_text": f"[ERROR] {e}",
                    "raw_response": str(e),
                    "elapsed": 0,
                })
        else:
            log(f"    [WARN] Unknown method: {name}, skipping")

    return results


# =====================================================================
#  展示
# =====================================================================

def display_summary(all_results: List[dict]):
    """打印最终汇总表。"""
    print()
    print("=" * 96)
    print("  全部论文 × 全部方法 — 运行结果汇总")
    print("=" * 96)

    for entry in all_results:
        paper = entry["paper"]
        results = entry["results"]
        print()
        title_short = paper['title'][:75]
        print(f"  论文: {title_short}")
        print(f"  学科: {paper.get('primary_discipline', 'N/A')}")
        print()

        # 分组显示: 外部 baseline 和 P1-P5
        externals = [r for r in results if r["method"] not in ALL_PROMPT_LEVELS]
        plevels = [r for r in results if r["method"] in ALL_PROMPT_LEVELS]

        if externals:
            print(f"  ── 外部 Baseline ──")
            print(f"  ┌{'─'*40}┬{'─'*10}┬{'─'*8}┐")
            print(f"  │{'Method':<40}│{'耗时(s)':<10}│{'状态':<8}│")
            print(f"  ├{'─'*40}┼{'─'*10}┼{'─'*8}┤")
            for r in externals:
                status = "ERROR" if r["hypotheses_text"].startswith("[ERROR]") else "OK"
                print(f"  │ {r['method']:<38} │ {r['elapsed']:<8} │ {status:<6} │")
            print(f"  └{'─'*40}┴{'─'*10}┴{'─'*8}┘")

        if plevels:
            print(f"  ── P1-P5 Prompt 消融 ──")
            print(f"  ┌{'─'*40}┬{'─'*10}┬{'─'*8}┐")
            print(f"  │{'Method':<40}│{'耗时(s)':<10}│{'状态':<8}│")
            print(f"  ├{'─'*40}┼{'─'*10}┼{'─'*8}┤")
            for r in plevels:
                status = "ERROR" if r["hypotheses_text"].startswith("[ERROR]") else "OK"
                print(f"  │ {r['method']:<38} │ {r['elapsed']:<8} │ {status:<6} │")
            print(f"  └{'─'*40}┴{'─'*10}┴{'─'*8}┘")

        print()

    # 总计统计
    total_papers = len(all_results)
    total_methods = sum(len(e["results"]) for e in all_results)
    total_ok = sum(
        1 for e in all_results for r in e["results"]
        if not r["hypotheses_text"].startswith("[ERROR]")
    )
    total_err = total_methods - total_ok
    print(f"  汇总: {total_papers} 篇论文, {total_methods} 次方法调用, "
          f"{total_ok} 成功, {total_err} 失败")
    print()


# =====================================================================
#  主函数
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="批量运行: 多篇论文 × (6 baseline + P1–P5) 假设生成对比"
    )
    parser.add_argument("--input", default="data/paper_1.json",
                        help="Input JSONL file (paper_1.json)")
    parser.add_argument("--paper-indices", default="0,3,9,13,14",
                        help="逗号分隔的论文索引 (0-based)，默认: 0,3,9,13,14")
    parser.add_argument("--no-alphafold", action="store_true",
                        help="不包含 AlphaFold 3 论文")
    parser.add_argument("--baselines", default=None,
                        help="逗号分隔的方法名 (默认: 全部 11 种)")
    parser.add_argument("--output", default="baseline/outputs/batch_results.json",
                        help="保存结果的 JSON 路径")
    args = parser.parse_args()

    # 确定方法列表
    if args.baselines:
        method_names = [b.strip() for b in args.baselines.split(",")]
    else:
        method_names = ALL_EXTERNAL_BASELINES + ALL_PROMPT_LEVELS

    # 加载论文
    papers = []
    indices = [int(x.strip()) for x in args.paper_indices.split(",")]
    for idx in indices:
        try:
            p = load_paper_from_jsonl(args.input, idx)
            papers.append((f"paper_1[{idx}]", p))
        except Exception as e:
            log(f"[WARN] Failed to load paper index {idx}: {e}")

    if not args.no_alphafold:
        papers.append(("AlphaFold3", ALPHAFOLD_PAPER))

    log(f"共 {len(papers)} 篇论文, {len(method_names)} 种方法")
    log(f"方法列表: {method_names}")
    log(f"论文列表:")
    for tag, p in papers:
        log(f"  - [{tag}] {p['title'][:70]}")
    log("")
    log(f"预计总调用: {len(papers)} × {len(method_names)} = {len(papers) * len(method_names)} 次")
    log("")

    # 逐篇运行
    all_results = []
    total_t0 = time.time()

    for paper_idx, (tag, paper) in enumerate(papers):
        log(f"{'═'*80}")
        log(f"[{paper_idx+1}/{len(papers)}] {tag}: {paper['title'][:60]}...")
        log(f"{'═'*80}")
        results = run_all_methods_for_paper(paper, method_names)
        all_results.append({
            "tag": tag,
            "paper": paper,
            "results": results,
        })
        ok_count = sum(1 for r in results if not r["hypotheses_text"].startswith("[ERROR]"))
        log(f"[{paper_idx+1}/{len(papers)}] 完成: {ok_count}/{len(results)} 成功")
        log("")

        # 每篇论文完成后保存中间结果（防止中途中断丢失数据）
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - total_t0
    log(f"全部完成! 总耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")

    # 展示汇总
    display_summary(all_results)

    # 最终保存
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    log(f"结果已保存到 {args.output}")


if __name__ == "__main__":
    main()

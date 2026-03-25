#!/usr/bin/env python3
"""
baseline/run_6paper_experiment.py

对6篇2025年论文运行完整对比实验：
- 6个外部 baseline (IdeaBench, VanillaLLM, AI-Scientist, SciMON, MOOSE-Chem, SciAgents)
- 5级 CrossDisc prompt 消融 (P1-P5)
- 统一评估

这是 run_batch_demo.py 的定制版本，直接读取 papers_6_2025.json。

用法:
    # 完整运行 (6篇 × 11方法)
    nohup python -m baseline.run_6paper_experiment \
        --output baseline/outputs/comparison_2025/results.json \
        > baseline/outputs/comparison_2025/run.log 2>&1 &

    # 小规模测试 (前2篇 × 11方法)
    python -m baseline.run_6paper_experiment \
        --max-papers 2 \
        --output baseline/outputs/comparison_2025/phase1_results.json

    # 只跑外部 baseline (不跑 P1-P5)
    python -m baseline.run_6paper_experiment \
        --methods IdeaBench,VanillaLLM,AI-Scientist,SciMON,MOOSE-Chem,SciAgents

    # 只跑 P1-P5
    python -m baseline.run_6paper_experiment --methods P1,P2,P3,P4,P5
"""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── 复用已有模块 ──────────────────────────────────────────────────────
from baseline.run_single_paper_demo import PROMPTS, run_baseline
from baseline.run_batch_demo import (
    ALL_EXTERNAL_BASELINES,
    ALL_PROMPT_LEVELS,
    run_crossdisc_extraction,
    format_crossdisc_hypothesis,
    run_prompt_level,
    make_p5_result,
)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_papers_json(path: str, max_papers: int = 0) -> List[Dict[str, Any]]:
    """从 papers_6_2025.json 加载论文。"""
    with open(path, encoding="utf-8") as f:
        papers = json.load(f)
    if max_papers > 0:
        papers = papers[:max_papers]
    return papers


def run_all_methods_for_paper(
    paper: Dict[str, Any],
    method_names: List[str],
) -> List[Dict[str, Any]]:
    """对一篇论文运行所有指定方法。"""
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
            if extraction_parsed:
                queries = extraction_parsed.get("查询", {})
                log(f"      L1 query: {str(queries.get('一级', ''))[:60]}...")
                log(f"      L2 queries: {len(queries.get('二级', []))}, L3 queries: {len(queries.get('三级', []))}")
        except Exception as e:
            crossdisc_elapsed = time.time() - t0
            log(f"    CrossDisc extraction FAILED ({crossdisc_elapsed:.1f}s): {e}")
            traceback.print_exc()
            extraction_parsed = None

    # ── Step 2: 逐个运行方法 ────────────────────────────────────────
    for name in method_names:
        if name in ALL_PROMPT_LEVELS:
            if name == "P5":
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
                log(f"    Running {name}...")
                r = run_prompt_level(name, paper, extraction_parsed)
                log(f"    {name} done ({r['elapsed']}s)")
            results.append(r)

        elif name in PROMPTS:
            log(f"    Running {name}...")
            try:
                r = run_baseline(name, PROMPTS[name], paper)
                results.append(r)
                log(f"    {name} done ({r['elapsed']}s)")
            except Exception as e:
                log(f"    {name} FAILED: {e}")
                results.append({
                    "method": name,
                    "hypotheses_text": f"[ERROR] {e}",
                    "elapsed": 0,
                })
        else:
            log(f"    [WARN] Unknown method: {name}, skipping")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="6篇2025论文 × 11种方法 对比实验"
    )
    parser.add_argument("--input", default="baseline/data/papers_6_2025.json",
                        help="论文 JSON 路径")
    parser.add_argument("--max-papers", type=int, default=0,
                        help="最多处理 N 篇论文 (0=全部)")
    parser.add_argument("--methods", default=None,
                        help="逗号分隔的方法名 (默认: 全部 11 种)")
    parser.add_argument("--output", default="baseline/outputs/comparison_2025/results.json",
                        help="输出 JSON 路径")
    args = parser.parse_args()

    # 确定方法列表
    if args.methods:
        method_names = [m.strip() for m in args.methods.split(",")]
    else:
        method_names = ALL_EXTERNAL_BASELINES + ALL_PROMPT_LEVELS

    # 加载论文
    papers = load_papers_json(args.input, args.max_papers)

    log(f"共 {len(papers)} 篇论文, {len(method_names)} 种方法")
    log(f"方法: {method_names}")
    log(f"论文:")
    for i, p in enumerate(papers):
        log(f"  [{i+1}] {p['title'][:65]}  ({p.get('primary_discipline', 'N/A')})")
    log(f"预计总调用: {len(papers)} × {len(method_names)} = {len(papers) * len(method_names)} 次")
    log("")

    # 逐篇运行
    all_results = []
    total_t0 = time.time()

    for paper_idx, paper in enumerate(papers):
        log(f"{'═'*80}")
        log(f"[{paper_idx+1}/{len(papers)}] {paper['title'][:60]}...")
        log(f"  主学科: {paper.get('primary_discipline', 'N/A')}")
        log(f"  辅学科: {paper.get('secondary_disciplines', [])}")
        log(f"{'═'*80}")

        results = run_all_methods_for_paper(paper, method_names)
        all_results.append({
            "tag": f"paper_{paper_idx}",
            "paper": paper,
            "results": results,
        })

        ok_count = sum(1 for r in results if not r.get("hypotheses_text", "").startswith("[ERROR]"))
        log(f"[{paper_idx+1}/{len(papers)}] 完成: {ok_count}/{len(results)} 成功")
        log("")

        # 每篇论文完成后保存中间结果
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - total_t0
    log(f"全部完成! 总耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")

    # 最终保存
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    log(f"结果已保存到 {args.output}")

    # 打印汇总
    print()
    print("=" * 96)
    print("  对比实验汇总")
    print("=" * 96)
    for entry in all_results:
        paper = entry["paper"]
        results = entry["results"]
        print(f"\n  论文: {paper['title'][:75]}")
        print(f"  学科: {paper.get('primary_discipline', 'N/A')}")
        for r in results:
            status = "ERROR" if r.get("hypotheses_text", "").startswith("[ERROR]") else "OK"
            print(f"    {r['method']:<20} {r.get('elapsed',0):>6.1f}s  {status}")

    total = sum(len(e["results"]) for e in all_results)
    total_ok = sum(
        1 for e in all_results for r in e["results"]
        if not r.get("hypotheses_text", "").startswith("[ERROR]")
    )
    print(f"\n  总计: {len(all_results)} 篇 × {len(method_names)} 方法 = {total} 次调用, {total_ok} 成功, {total-total_ok} 失败")


if __name__ == "__main__":
    main()

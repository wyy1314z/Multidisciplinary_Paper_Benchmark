"""
baseline/run_comparison.py — 入口脚本：运行多个 baseline 并统一评估。

用法:
    # 1. 转换输入数据
    python -m baseline.convert_input \
        --input data/paper_1.json \
        --output baseline/data/papers_unified.json \
        --max-papers 5

    # 2. 运行对比实验
    python -m baseline.run_comparison \
        --input baseline/data/papers_unified.json \
        --output baseline/outputs/ \
        --baselines ideabench,vanilla,crossdisc \
        --model gpt-4o-mini \
        --num-hypotheses 3 \
        [--no-llm-judge]  # 跳过 LLM 评分（省钱/快速测试）

    # 3. 仅评估已有结果
    python -m baseline.run_comparison \
        --eval-only \
        --results baseline/outputs/all_results.json \
        --input baseline/data/papers_unified.json \
        --output baseline/outputs/
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Dict, List

from baseline.common import PaperInput, HypothesisOutput, save_outputs
from baseline.evaluate_all import (
    evaluate_all_outputs,
    aggregate_by_method,
    print_comparison_table,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("baseline.run")

def load_papers(path: str) -> List[PaperInput]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [PaperInput(**item) for item in data]


def build_adapters(baseline_names: List[str], model: str):
    adapters = []
    for name in baseline_names:
        name = name.strip().lower()
        if name == "ideabench":
            from baseline.adapters.ideabench import IdeaBenchAdapter
            adapters.append(IdeaBenchAdapter(model_name=model))
        elif name == "vanilla":
            from baseline.adapters.vanilla_llm import VanillaLLMAdapter
            adapters.append(VanillaLLMAdapter(model_name=model))
        elif name == "crossdisc":
            from baseline.adapters.crossdisc import CrossDiscAdapter
            adapters.append(CrossDiscAdapter(model_name=model))
        elif name in ("ai_scientist", "ai-scientist"):
            from baseline.adapters.ai_scientist import AiScientistAdapter
            adapters.append(AiScientistAdapter(model_name=model))
        elif name == "scimon":
            from baseline.adapters.scimon import SciMonAdapter
            adapters.append(SciMonAdapter(model_name=model))
        elif name in ("moose_chem", "moose-chem"):
            from baseline.adapters.moose_chem import MooseChemAdapter
            adapters.append(MooseChemAdapter(model_name=model))
        elif name == "sciagents":
            from baseline.adapters.sciagents import SciAgentsAdapter
            adapters.append(SciAgentsAdapter(model_name=model))
        else:
            logger.warning("Unknown baseline: %s, skipping", name)
    return adapters


def run_generation(
    papers: List[PaperInput],
    baseline_names: List[str],
    model: str,
    num_hypotheses: int,
) -> List[HypothesisOutput]:
    adapters = build_adapters(baseline_names, model)
    all_outputs: List[HypothesisOutput] = []

    for adapter in adapters:
        logger.info("Running baseline: %s", adapter.name)
        for i, paper in enumerate(papers):
            logger.info("  [%d/%d] Paper: %s", i + 1, len(papers), paper.title[:60])
            try:
                output = adapter.generate(paper, num_hypotheses=num_hypotheses)
                all_outputs.append(output)
                logger.info(
                    "    Generated %d hypotheses in %.1fs",
                    len(output.free_text_hypotheses),
                    output.elapsed_seconds,
                )
            except Exception as e:
                logger.error("    Failed: %s", e)
                all_outputs.append(HypothesisOutput(
                    paper_id=paper.paper_id,
                    method_name=adapter.name,
                    free_text_hypotheses=[f"[ERROR] {e}"],
                ))

    return all_outputs


def main():
    parser = argparse.ArgumentParser(description="Run multi-baseline hypothesis comparison")
    parser.add_argument("--input", required=True, help="Unified papers JSON")
    parser.add_argument("--output", default="baseline/outputs/", help="Output directory")
    parser.add_argument("--baselines",
                        default="ideabench,vanilla,ai_scientist,scimon,moose_chem,sciagents,crossdisc",
                        help="Comma-separated baseline names: ideabench,vanilla,ai_scientist,scimon,moose_chem,sciagents,crossdisc")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model name")
    parser.add_argument("--num-hypotheses", type=int, default=3)
    parser.add_argument("--no-llm-judge", action="store_true", help="Skip LLM judge evaluation")
    parser.add_argument("--eval-only", action="store_true", help="Only evaluate existing results")
    parser.add_argument("--results", default=None, help="Path to existing results (for --eval-only)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 加载论文
    papers = load_papers(args.input)
    papers_dict = {p.paper_id: p.to_dict() for p in papers}
    logger.info("Loaded %d papers", len(papers))

    if args.eval_only:
        # 仅评估模式
        results_path = args.results or os.path.join(args.output, "all_results.json")
        with open(results_path, encoding="utf-8") as f:
            all_output_dicts = json.load(f)
    else:
        # 运行生成
        baseline_names = [b.strip() for b in args.baselines.split(",")]
        outputs = run_generation(papers, baseline_names, args.model, args.num_hypotheses)

        # 保存原始结果
        all_output_dicts = [o.to_dict() for o in outputs]
        results_path = os.path.join(args.output, "all_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(all_output_dicts, f, ensure_ascii=False, indent=2)
        logger.info("Saved %d results to %s", len(all_output_dicts), results_path)

    # 评估
    logger.info("Running evaluation...")
    eval_results = evaluate_all_outputs(
        all_output_dicts, papers_dict, use_llm_judge=not args.no_llm_judge,
    )

    # 保存评估结果
    eval_path = os.path.join(args.output, "eval_results.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, ensure_ascii=False, indent=2)

    # 聚合并打印对比表
    aggregated = aggregate_by_method(eval_results)
    print_comparison_table(aggregated)

    # 保存聚合结果
    agg_path = os.path.join(args.output, "comparison_summary.json")
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2)
    logger.info("Comparison summary saved to %s", agg_path)


if __name__ == "__main__":
    main()

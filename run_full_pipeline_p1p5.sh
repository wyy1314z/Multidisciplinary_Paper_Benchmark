#!/bin/bash
# ============================================================================
# CrossDisc Benchmark 全套流程 (P1–P5 五级 Prompt 消融实验)
# ============================================================================
#
# 输入: data/paper_1.json (92篇已分类的跨学科论文)
#
# 流程:
#   Step 1: 筛选跨学科论文 (92篇均有 non_main_levels → 全部跨学科)
#   Step 2: 对全部 92 篇跑 CrossDisc 三阶段抽取 (概念/关系/查询/假设)
#   Step 3: 划分数据集 — 前 89 篇构建 GT, 后 3 篇作为测试集
#   Step 4: 构建 Benchmark GT 数据集 (evidence-grounded)
#   Step 5: 对测试集的 3 篇论文, 分别用 P1-P5 五级 prompt 生成假设
#   Step 6: 评测 — 对每个层级 (P1-P5) 的假设进行多维度评估
#   Step 7: 汇总对比结果
# ============================================================================

set -e

# ── 颜色输出 ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_step() { echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"; echo -e "${GREEN}[STEP] $1${NC}"; echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"; }
log_info() { echo -e "${YELLOW}[INFO] $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $1${NC}"; }

# ── 工作目录 ────────────────────────────────────────────────────────
PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

# ── 环境变量检查 ────────────────────────────────────────────────────
if [ -z "$OPENAI_API_KEY" ]; then
    log_error "OPENAI_API_KEY 未设置！请先执行:"
    echo '  export OPENAI_API_KEY="your-api-key"'
    echo '  export OPENAI_MODEL="genmini-2.5-pro"'
    echo '  export OPENAI_BASE_URL="http://api.shubiaobiao.cn/v1"'
    exit 1
fi

log_info "OPENAI_MODEL = ${OPENAI_MODEL:-qwen3-235b-a22b (默认)}"
log_info "OPENAI_BASE_URL = ${OPENAI_BASE_URL:-http://api.shubiaobiao.cn/v1 (默认)}"

# ── 配置参数 ────────────────────────────────────────────────────────
INPUT_FILE="data/paper_1.json"
OUTPUT_DIR="outputs/p1p5_pipeline_run"
NUM_WORKERS=2
LANGUAGE_MODE="chinese"
TEST_COUNT=3         # 测试集论文数 (取最后N篇)

mkdir -p "$OUTPUT_DIR"


# ============================================================================
# Step 1: 确认跨学科论文
# ============================================================================
log_step "Step 1: 确认跨学科论文"

TOTAL_PAPERS=$(python3 -c "
import json
with open('$INPUT_FILE') as f:
    lines = [l.strip() for l in f if l.strip()]
cross = sum(1 for l in lines if json.loads(l).get('non_main_levels', '').strip())
print(f'{len(lines)} 篇论文中有 {cross} 篇跨学科论文')
print(cross)
" | tail -1)

GT_COUNT=$((TOTAL_PAPERS - TEST_COUNT))
log_info "共 $TOTAL_PAPERS 篇跨学科论文"
log_info "GT 集: 前 $GT_COUNT 篇 | 测试集: 后 $TEST_COUNT 篇"


# ============================================================================
# Step 2: 三阶段知识抽取 (全部92篇)
# ============================================================================
log_step "Step 2: 三阶段知识抽取 (概念→关系→查询→假设)"
log_info "输入: $INPUT_FILE"
log_info "输出: $OUTPUT_DIR/extraction_results.jsonl"

python run.py batch \
    --input "$INPUT_FILE" \
    --output "$OUTPUT_DIR/extraction_results.jsonl" \
    --num-workers "$NUM_WORKERS" \
    --resume \
    --language-mode "$LANGUAGE_MODE"

log_info "抽取完成"


# ============================================================================
# Step 3: 划分数据集
# ============================================================================
log_step "Step 3: 划分数据集 (GT集 $GT_COUNT 篇 + 测试集 $TEST_COUNT 篇)"

python3 << 'SPLIT_EOF'
import json, sys, os

output_dir = os.environ.get("OUTPUT_DIR", "outputs/p1p5_pipeline_run")
test_count = int(os.environ.get("TEST_COUNT", "3"))
extraction_file = os.path.join(output_dir, "extraction_results.jsonl")

results = []
with open(extraction_file, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            results.append(json.loads(line))

ok_results = [r for r in results if r.get("ok")]
print(f"总共 {len(results)} 条, 成功 {len(ok_results)} 条")

if len(ok_results) < test_count + 1:
    print(f"ERROR: 成功数 ({len(ok_results)}) 不足 (需 >= {test_count + 1})")
    sys.exit(1)

gt_items = ok_results[:-test_count]
test_items = ok_results[-test_count:]

print(f"GT 集: {len(gt_items)} 篇")
print(f"测试集: {len(test_items)} 篇")
for t in test_items:
    print(f"  测试: {t.get('title', '')[:60]}")

# 保存
for name, items in [("gt_extraction.json", gt_items),
                     ("test_extraction.json", test_items),
                     ("extraction_results.json", ok_results)]:
    path = os.path.join(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"已保存: {path}")
SPLIT_EOF

log_info "数据集划分完成"


# ============================================================================
# Step 4: 构建 Benchmark GT 数据集 (evidence-grounded)
# ============================================================================
log_step "Step 4: 构建 Benchmark GT 数据集"

python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$OUTPUT_DIR/gt_extraction.json" \
    --output "$OUTPUT_DIR/benchmark_dataset.json" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

log_info "Benchmark GT 已构建: $OUTPUT_DIR/benchmark_dataset.json"


# ============================================================================
# Step 5: 对测试集 3 篇论文，分别运行 P1-P5 五级 Prompt 假设生成
# ============================================================================
log_step "Step 5: P1-P5 五级 Prompt 假设生成 (测试集 $TEST_COUNT 篇 × 5 级)"

python3 << 'P1P5_EOF'
"""
对测试集的每篇论文, 运行 P1-P5 五级 prompt 生成假设。
P1-P4: 自由文本假设
P5:    结构化 3-step 路径假设 (直接复用 CrossDisc 抽取结果)

结果同时输出两种格式:
  1) batch_demo 格式 → p1p5_batch_results.json   (用于查看/汇报)
  2) evaluate_all 格式 → p1p5_eval_input.json     (用于统一评测)
"""
import json
import hashlib
import os
import sys
import time
import traceback
from datetime import datetime

output_dir = os.environ.get("OUTPUT_DIR", "outputs/p1p5_pipeline_run")

# 加载测试集 (已经含 parsed 抽取结果)
test_file = os.path.join(output_dir, "test_extraction.json")
with open(test_file, encoding="utf-8") as f:
    test_items = json.load(f)

print(f"测试集论文数: {len(test_items)}")

from crossdisc_extractor.prompts.hypothesis_prompt_levels import (
    PromptLevel, build_messages, build_p5_all_levels,
)
from crossdisc_extractor.utils.llm import chat_completion_with_retry

all_batch_results = []   # batch_demo 格式
all_eval_inputs = []     # evaluate_all 格式

for paper_idx, item in enumerate(test_items):
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    abstract = item.get("abstract", "")
    primary = meta.get("primary", item.get("primary", ""))
    secondary_list = meta.get("secondary_list", item.get("secondary_list", []))
    paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]

    print(f"\n{'='*70}")
    print(f"[{paper_idx+1}/{len(test_items)}] {title[:60]}...")
    print(f"  主学科: {primary} | 辅学科: {secondary_list}")
    print(f"{'='*70}")

    # 提取结构化数据
    queries = parsed.get("查询", {})
    l1_query = queries.get("一级", "")
    l2_queries = queries.get("二级", [])
    l3_queries = queries.get("三级", [])
    concepts = parsed.get("概念", {})
    relations = parsed.get("跨学科关系", [])

    paper_results = []

    for level_name in ["P1", "P2", "P3", "P4", "P5"]:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] 运行 {level_name}...", end="", flush=True)
        t0 = time.time()

        try:
            if level_name == "P5":
                # P5: 直接复用 CrossDisc 抽取结果中的假设
                hyp_data = parsed.get("假设", {})
                hyp_lines = []
                structured_paths = {}
                for level_key, cn_key, sum_key in [("L1","一级","一级总结"),
                                                     ("L2","二级","二级总结"),
                                                     ("L3","三级","三级总结")]:
                    paths = hyp_data.get(cn_key, [])
                    summaries = hyp_data.get(sum_key, [])
                    level_paths = []
                    for i, path in enumerate(paths):
                        if isinstance(path, list):
                            steps = []
                            for step in path:
                                if isinstance(step, dict):
                                    steps.append(step)
                                elif hasattr(step, "model_dump"):
                                    steps.append(step.model_dump())
                            level_paths.append({"steps": steps,
                                                "summary": summaries[i] if i < len(summaries) else ""})
                            # 格式化显示
                            for step in steps:
                                h = step.get("head", step.get("头实体", ""))
                                r = step.get("relation", step.get("关系", ""))
                                tail = step.get("tail", step.get("尾实体", ""))
                                hyp_lines.append(f"  [{level_key}] {h} --[{r}]--> {tail}")
                    if level_paths:
                        structured_paths[level_key] = level_paths

                hyp_text = "\n".join(hyp_lines) if hyp_lines else "(empty)"
                elapsed = time.time() - t0

                result = {
                    "method": "P5",
                    "hypotheses_text": hyp_text,
                    "elapsed": round(elapsed, 1),
                }
                # evaluate_all 格式
                eval_entry = {
                    "paper_id": paper_id,
                    "method_name": "P5",
                    "free_text_hypotheses": [summaries[i] if i < len(summaries) else ""
                                             for cn_key_inner in ["一级总结","二级总结","三级总结"]
                                             for i, _ in enumerate(hyp_data.get(cn_key_inner, []))],
                    "structured_paths": {
                        level: [p for p in paths_list]
                        for level, paths_list in structured_paths.items()
                    },
                    "raw_responses": [],
                    "elapsed_seconds": elapsed,
                }

            else:
                # P1-P4: 自由文本生成
                level = PromptLevel(level_name)
                messages = build_messages(
                    level,
                    l1_query=l1_query,
                    l2_queries=l2_queries if level.value >= "P2" else None,
                    l3_queries=l3_queries if level.value >= "P3" else None,
                    abstract=abstract if level.value >= "P2" else "",
                    primary=primary,
                    secondary_list=secondary_list,
                    concepts=concepts if level.value >= "P3" else None,
                    relations=relations if level.value >= "P4" else None,
                )
                resp = chat_completion_with_retry(messages, temperature=0.7)
                hyp_text = resp.strip()
                elapsed = time.time() - t0

                result = {
                    "method": level_name,
                    "hypotheses_text": hyp_text,
                    "elapsed": round(elapsed, 1),
                }
                eval_entry = {
                    "paper_id": paper_id,
                    "method_name": level_name,
                    "free_text_hypotheses": [hyp_text],
                    "structured_paths": {},
                    "raw_responses": [resp],
                    "elapsed_seconds": elapsed,
                }

            paper_results.append(result)
            all_eval_inputs.append(eval_entry)
            print(f" 完成 ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - t0
            print(f" 失败 ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            paper_results.append({
                "method": level_name,
                "hypotheses_text": f"[ERROR] {e}",
                "elapsed": round(elapsed, 1),
            })
            all_eval_inputs.append({
                "paper_id": paper_id,
                "method_name": level_name,
                "free_text_hypotheses": [f"[ERROR] {e}"],
                "structured_paths": {},
                "raw_responses": [],
                "elapsed_seconds": elapsed,
            })

    all_batch_results.append({
        "tag": f"test_{paper_idx}",
        "paper": {
            "paper_id": paper_id,
            "title": title,
            "abstract": abstract[:200] + "...",
            "primary_discipline": primary,
            "secondary_disciplines": secondary_list,
        },
        "results": paper_results,
    })

# 保存结果
batch_path = os.path.join(output_dir, "p1p5_batch_results.json")
with open(batch_path, "w", encoding="utf-8") as f:
    json.dump(all_batch_results, f, ensure_ascii=False, indent=2)
print(f"\nP1-P5 生成结果已保存: {batch_path}")

eval_path = os.path.join(output_dir, "p1p5_eval_input.json")
with open(eval_path, "w", encoding="utf-8") as f:
    json.dump(all_eval_inputs, f, ensure_ascii=False, indent=2)
print(f"评测输入已保存: {eval_path}")

# 构建论文 ID → 论文信息的映射 (供 evaluate_all 使用)
papers_dict = {}
for item in test_items:
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    pid = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
    papers_dict[pid] = {
        "paper_id": pid,
        "title": title,
        "abstract": item.get("abstract", ""),
        "primary_discipline": meta.get("primary", ""),
        "secondary_disciplines": meta.get("secondary_list", []),
    }

papers_map_path = os.path.join(output_dir, "test_papers_map.json")
with open(papers_map_path, "w", encoding="utf-8") as f:
    json.dump(papers_dict, f, ensure_ascii=False, indent=2)
print(f"论文映射已保存: {papers_map_path}")

P1P5_EOF

log_info "P1-P5 假设生成完成"


# ============================================================================
# Step 6: 多维度评测 (对 P1-P5 每个层级的假设)
# ============================================================================
log_step "Step 6: 多维度评测 (LLM-as-Judge + 文本相似度 + 结构化指标)"

python3 << 'EVAL_EOF'
"""
对 P1-P5 的每条假设进行多维度评测:
  A) LLM-as-Judge: novelty, specificity, feasibility, relevance, cross_disciplinary (1-10)
  B) 文本相似度: BERTScore (降级为 sentence-transformers cosine)
  C) 结构化指标 (仅 P5): chain_coherence, entity_grounding_rate, relation_diversity
"""
import json, os, sys
import numpy as np

output_dir = os.environ.get("OUTPUT_DIR", "outputs/p1p5_pipeline_run")

# 加载数据
eval_input_path = os.path.join(output_dir, "p1p5_eval_input.json")
papers_map_path = os.path.join(output_dir, "test_papers_map.json")

with open(eval_input_path, encoding="utf-8") as f:
    eval_inputs = json.load(f)

with open(papers_map_path, encoding="utf-8") as f:
    papers_map = json.load(f)

print(f"待评测条目: {len(eval_inputs)} (来自 {len(papers_map)} 篇论文 × 5 级)")

# 导入评测模块
from baseline.evaluate_all import (
    evaluate_single_output,
    aggregate_by_method,
    print_comparison_table,
)

# 逐条评测
all_eval_results = []
for i, output in enumerate(eval_inputs):
    pid = output.get("paper_id", "")
    method = output.get("method_name", "")
    paper = papers_map.get(pid, {})

    if not paper:
        print(f"  [{i+1}/{len(eval_inputs)}] {method}: 论文 {pid} 未找到, 跳过")
        continue

    print(f"  [{i+1}/{len(eval_inputs)}] {method} - {paper['title'][:50]}...", flush=True)

    result = evaluate_single_output(output, paper, use_llm_judge=True)
    all_eval_results.append(result)

# 保存详细评测结果
eval_results_path = os.path.join(output_dir, "p1p5_eval_results.json")
with open(eval_results_path, "w", encoding="utf-8") as f:
    json.dump(all_eval_results, f, ensure_ascii=False, indent=2)
print(f"\n评测结果已保存: {eval_results_path}")

# 按方法聚合
aggregated = aggregate_by_method(all_eval_results)

# 打印对比表
print_comparison_table(aggregated)

# 保存聚合对比
summary_path = os.path.join(output_dir, "p1p5_comparison_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(aggregated, f, ensure_ascii=False, indent=2)
print(f"对比汇总已保存: {summary_path}")

EVAL_EOF

log_info "评测完成"


# ============================================================================
# Step 7: 用 KG-based 评测框架再跑一次 (evaluate_benchmark.py)
# ============================================================================
log_step "Step 7: KG-based 结构化评测 (P5 假设 vs GT 知识图谱)"
log_info "此步骤针对 P5 结构化路径假设, 使用 GT 知识图谱进行深度评测"

python -m crossdisc_extractor.benchmark.evaluate_benchmark \
    --benchmark "$OUTPUT_DIR/benchmark_dataset.json" \
    --predictions "$OUTPUT_DIR/test_extraction.json" \
    --output "$OUTPUT_DIR/p5_kg_eval_results.json" \
    --taxonomy data/msc_converted.json

log_info "KG-based 评测完成: $OUTPUT_DIR/p5_kg_eval_results.json"


# ============================================================================
# 最终汇总
# ============================================================================
log_step "全套流程完成！输出文件汇总"

echo -e "  📂 ${GREEN}$OUTPUT_DIR/${NC}"
echo -e "  │"
echo -e "  ├── ${YELLOW}抽取结果${NC}"
echo -e "  │   ├── extraction_results.jsonl     — 全部92篇论文的抽取结果 (JSONL, 支持断点续传)"
echo -e "  │   ├── extraction_results.json      — 全部成功论文的抽取结果 (JSON)"
echo -e "  │   ├── gt_extraction.json           — GT集 (前${GT_COUNT}篇) 的抽取结果"
echo -e "  │   └── test_extraction.json         — 测试集 (后${TEST_COUNT}篇) 的抽取结果"
echo -e "  │"
echo -e "  ├── ${YELLOW}Benchmark GT${NC}"
echo -e "  │   └── benchmark_dataset.json       — Evidence-Grounded GT 数据集"
echo -e "  │"
echo -e "  ├── ${YELLOW}P1-P5 假设生成${NC}"
echo -e "  │   ├── p1p5_batch_results.json      — P1-P5 各级假设文本 (可读格式)"
echo -e "  │   ├── p1p5_eval_input.json         — P1-P5 假设 (评测输入格式)"
echo -e "  │   └── test_papers_map.json         — 测试论文ID映射"
echo -e "  │"
echo -e "  └── ${YELLOW}评测结果${NC}"
echo -e "      ├── p1p5_eval_results.json       — P1-P5 多维度评测详细结果"
echo -e "      ├── p1p5_comparison_summary.json  — P1-P5 方法对比汇总 ⭐"
echo -e "      └── p5_kg_eval_results.json      — P5 KG-based 深度评测结果"

echo ""
echo -e "${GREEN}查看 P1-P5 对比汇总:${NC}"
echo "  cat $OUTPUT_DIR/p1p5_comparison_summary.json | python3 -m json.tool"
echo ""
echo -e "${GREEN}全套流程运行完毕！${NC}"

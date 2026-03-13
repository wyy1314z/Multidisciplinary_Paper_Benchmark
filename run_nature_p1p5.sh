#!/bin/bash
# ============================================================================
# CrossDisc Benchmark 全套流程 (P1–P5) — Nature 系列论文
# ============================================================================
#
# 输入: data/nature_springer_2025.csv (OpenAlex 数据)
#
# 流程:
#   Step 0: CSV → JSONL 转换 (筛选 Nature 系列 + 有摘要 + 英文)
#   Step 1: 学科分类 + 跨学科筛选 (LLM 3层分类)
#   Step 2: 对跨学科论文运行三阶段知识抽取
#   Step 3: 划分数据集 — 除最后3篇外构建 GT, 后3篇作为测试集
#   Step 4: 构建 Benchmark GT 数据集
#   Step 5: 对测试集 3 篇论文, 分别用 P1-P5 五级 Prompt 生成假设
#   Step 6: 多维度评测
#   Step 7: P5 KG-based 深度评测
# ============================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_step() { echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"; echo -e "${GREEN}[STEP] $1${NC}"; echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"; }
log_info() { echo -e "${YELLOW}[INFO] $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $1${NC}"; }

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

log_info "OPENAI_MODEL = ${OPENAI_MODEL:-deepseek-v3 (默认)}"
log_info "OPENAI_BASE_URL = ${OPENAI_BASE_URL:-http://api.shubiaobiao.cn/v1 (默认)}"

# ── 配置参数 ────────────────────────────────────────────────────────
CSV_INPUT="data/nature_springer_2025.csv"
OUTPUT_DIR="outputs/nature_p1p5_run"
NUM_WORKERS=2
LANGUAGE_MODE="chinese"
TEST_COUNT=3

mkdir -p "$OUTPUT_DIR"

JSONL_RAW="$OUTPUT_DIR/nature_raw.jsonl"
JSONL_CLASSIFIED="$OUTPUT_DIR/nature_classified.jsonl"


# ============================================================================
# Step 0: CSV → JSONL 转换
# ============================================================================
log_step "Step 0: CSV → JSONL 转换 (筛选 Nature 系列 + 有摘要 + 英文)"

python3 << 'CSV2JSONL_EOF'
import csv, json, os

csv_path = os.environ.get("CSV_INPUT", "data/nature_springer_2025.csv")
output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_p1p5_run")
jsonl_path = os.path.join(output_dir, "nature_raw.jsonl")

count = 0
with open(csv_path, encoding="utf-8") as f_in, \
     open(jsonl_path, "w", encoding="utf-8") as f_out:
    reader = csv.DictReader(f_in)
    for row in reader:
        journal = row.get("primary_location.source.display_name", "")
        abstract = row.get("abstract", "").strip()
        title = row.get("display_name", "").strip()
        lang = row.get("language", "")

        # 筛选: Nature 系列 + 有摘要 + 英文
        if not journal.lower().startswith("nature"):
            continue
        if not abstract or not title:
            continue
        if lang and lang != "en":
            continue

        record = {
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "doi": row.get("doi", ""),
            "primary_topic": row.get("primary_topic.display_name", ""),
            "cited_by_count": int(row.get("cited_by_count", 0) or 0),
            "publication_date": row.get("publication_date", ""),
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        count += 1

print(f"转换完成: {count} 篇 Nature 系列英文论文 → {jsonl_path}")
CSV2JSONL_EOF

TOTAL_RAW=$(wc -l < "$JSONL_RAW")
log_info "原始论文数: $TOTAL_RAW 篇"


# ============================================================================
# Step 1: 学科分类 + 跨学科筛选
# ============================================================================
log_step "Step 1: 学科分类 + 跨学科筛选 (每篇 ~3 次 LLM 调用)"
log_info "输入: $JSONL_RAW ($TOTAL_RAW 篇)"
log_info "输出: $JSONL_CLASSIFIED (仅跨学科论文)"
log_info "预计 LLM 调用: ~$((TOTAL_RAW * 3)) 次"

python -m crossdisc_extractor.pipeline classify \
    --input "$JSONL_RAW" \
    --output "$JSONL_CLASSIFIED" \
    --config configs/default.yaml

TOTAL_CROSS=$(wc -l < "$JSONL_CLASSIFIED")
log_info "跨学科论文: $TOTAL_CROSS 篇 (从 $TOTAL_RAW 篇中筛出)"


# ============================================================================
# Step 2: 三阶段知识抽取
# ============================================================================
log_step "Step 2: 三阶段知识抽取 (概念→关系→查询→假设)"
log_info "输入: $JSONL_CLASSIFIED ($TOTAL_CROSS 篇跨学科论文)"
log_info "输出: $OUTPUT_DIR/extraction_results.jsonl"

python run.py batch \
    --input "$JSONL_CLASSIFIED" \
    --output "$OUTPUT_DIR/extraction_results.jsonl" \
    --num-workers "$NUM_WORKERS" \
    --resume \
    --language-mode "$LANGUAGE_MODE"

log_info "抽取完成"


# ============================================================================
# Step 3: 划分数据集
# ============================================================================
log_step "Step 3: 划分数据集 (GT集 + 测试集)"

python3 << 'SPLIT_EOF'
import json, sys, os

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_p1p5_run")
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
# Step 4: 构建 Benchmark GT 数据集
# ============================================================================
log_step "Step 4: 构建 Benchmark GT 数据集 (evidence-grounded)"

python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$OUTPUT_DIR/gt_extraction.json" \
    --output "$OUTPUT_DIR/benchmark_dataset.json" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

log_info "Benchmark GT 已构建"


# ============================================================================
# Step 5: P1-P5 五级 Prompt 假设生成
# ============================================================================
log_step "Step 5: P1-P5 五级 Prompt 假设生成 (测试集 $TEST_COUNT 篇 × 5 级)"

python3 << 'P1P5_EOF'
import json, hashlib, os, sys, time, traceback
from datetime import datetime

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_p1p5_run")

test_file = os.path.join(output_dir, "test_extraction.json")
with open(test_file, encoding="utf-8") as f:
    test_items = json.load(f)

print(f"测试集论文数: {len(test_items)}")

from crossdisc_extractor.prompts.hypothesis_prompt_levels import (
    PromptLevel, build_messages,
)
from crossdisc_extractor.utils.llm import chat_completion_with_retry

all_batch_results = []
all_eval_inputs = []

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
                            steps = [s if isinstance(s, dict) else s.model_dump() if hasattr(s, "model_dump") else {} for s in path]
                            level_paths.append({"steps": steps, "summary": summaries[i] if i < len(summaries) else ""})
                            for step in steps:
                                h = step.get("head", step.get("头实体", ""))
                                r = step.get("relation", step.get("关系", ""))
                                tail = step.get("tail", step.get("尾实体", ""))
                                hyp_lines.append(f"  [{level_key}] {h} --[{r}]--> {tail}")
                    if level_paths:
                        structured_paths[level_key] = level_paths

                hyp_text = "\n".join(hyp_lines) if hyp_lines else "(empty)"
                elapsed = time.time() - t0
                result = {"method": "P5", "hypotheses_text": hyp_text, "elapsed": round(elapsed, 1)}
                all_summaries = []
                for sk in ["一级总结", "二级总结", "三级总结"]:
                    all_summaries.extend(hyp_data.get(sk, []))
                eval_entry = {
                    "paper_id": paper_id, "method_name": "P5",
                    "free_text_hypotheses": [s for s in all_summaries if s],
                    "structured_paths": structured_paths,
                    "raw_responses": [], "elapsed_seconds": elapsed,
                }
            else:
                level = PromptLevel(level_name)
                messages = build_messages(
                    level, l1_query=l1_query,
                    l2_queries=l2_queries if level.value >= "P2" else None,
                    l3_queries=l3_queries if level.value >= "P3" else None,
                    abstract=abstract if level.value >= "P2" else "",
                    primary=primary, secondary_list=secondary_list,
                    concepts=concepts if level.value >= "P3" else None,
                    relations=relations if level.value >= "P4" else None,
                )
                resp = chat_completion_with_retry(messages, temperature=0.7)
                hyp_text = resp.strip()
                elapsed = time.time() - t0
                result = {"method": level_name, "hypotheses_text": hyp_text, "elapsed": round(elapsed, 1)}
                eval_entry = {
                    "paper_id": paper_id, "method_name": level_name,
                    "free_text_hypotheses": [hyp_text],
                    "structured_paths": {}, "raw_responses": [resp], "elapsed_seconds": elapsed,
                }

            paper_results.append(result)
            all_eval_inputs.append(eval_entry)
            print(f" 完成 ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - t0
            print(f" 失败 ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            paper_results.append({"method": level_name, "hypotheses_text": f"[ERROR] {e}", "elapsed": round(elapsed, 1)})
            all_eval_inputs.append({
                "paper_id": paper_id, "method_name": level_name,
                "free_text_hypotheses": [f"[ERROR] {e}"],
                "structured_paths": {}, "raw_responses": [], "elapsed_seconds": elapsed,
            })

    all_batch_results.append({
        "tag": f"test_{paper_idx}",
        "paper": {"paper_id": paper_id, "title": title, "abstract": abstract[:200] + "...",
                  "primary_discipline": primary, "secondary_disciplines": secondary_list},
        "results": paper_results,
    })

# 保存
for name, data in [("p1p5_batch_results.json", all_batch_results),
                    ("p1p5_eval_input.json", all_eval_inputs)]:
    path = os.path.join(output_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存: {path}")

# 论文映射
papers_dict = {}
for item in test_items:
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    pid = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
    papers_dict[pid] = {
        "paper_id": pid, "title": title, "abstract": item.get("abstract", ""),
        "primary_discipline": meta.get("primary", ""),
        "secondary_disciplines": meta.get("secondary_list", []),
    }
with open(os.path.join(output_dir, "test_papers_map.json"), "w", encoding="utf-8") as f:
    json.dump(papers_dict, f, ensure_ascii=False, indent=2)
print(f"已保存: test_papers_map.json")
P1P5_EOF

log_info "P1-P5 假设生成完成"


# ============================================================================
# Step 6: 多维度评测
# ============================================================================
log_step "Step 6: 多维度评测 (LLM-as-Judge + 文本相似度 + 结构化指标)"

python3 << 'EVAL_EOF'
import json, os
import numpy as np

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_p1p5_run")

with open(os.path.join(output_dir, "p1p5_eval_input.json"), encoding="utf-8") as f:
    eval_inputs = json.load(f)
with open(os.path.join(output_dir, "test_papers_map.json"), encoding="utf-8") as f:
    papers_map = json.load(f)

print(f"待评测条目: {len(eval_inputs)}")

from baseline.evaluate_all import evaluate_single_output, aggregate_by_method, print_comparison_table

all_eval_results = []
for i, output in enumerate(eval_inputs):
    pid = output.get("paper_id", "")
    method = output.get("method_name", "")
    paper = papers_map.get(pid, {})
    if not paper:
        continue
    print(f"  [{i+1}/{len(eval_inputs)}] {method} - {paper['title'][:50]}...", flush=True)
    result = evaluate_single_output(output, paper, use_llm_judge=True)
    all_eval_results.append(result)

with open(os.path.join(output_dir, "p1p5_eval_results.json"), "w", encoding="utf-8") as f:
    json.dump(all_eval_results, f, ensure_ascii=False, indent=2)

aggregated = aggregate_by_method(all_eval_results)
print_comparison_table(aggregated)

with open(os.path.join(output_dir, "p1p5_comparison_summary.json"), "w", encoding="utf-8") as f:
    json.dump(aggregated, f, ensure_ascii=False, indent=2)
print(f"对比汇总已保存")
EVAL_EOF

log_info "评测完成"


# ============================================================================
# Step 7: P5 KG-based 深度评测
# ============================================================================
log_step "Step 7: KG-based 结构化评测 (P5 假设 vs GT 知识图谱)"

python -m crossdisc_extractor.benchmark.evaluate_benchmark \
    --benchmark "$OUTPUT_DIR/benchmark_dataset.json" \
    --predictions "$OUTPUT_DIR/test_extraction.json" \
    --output "$OUTPUT_DIR/p5_kg_eval_results.json" \
    --taxonomy data/msc_converted.json

log_info "KG-based 评测完成"


# ============================================================================
# 最终汇总
# ============================================================================
log_step "全套流程完成！"

echo -e "  📂 ${GREEN}$OUTPUT_DIR/${NC}"
echo -e "  ├── nature_raw.jsonl              — CSV 转换后的原始论文 (JSONL)"
echo -e "  ├── nature_classified.jsonl        — 分类后的跨学科论文"
echo -e "  ├── extraction_results.jsonl       — 全部抽取结果 (断点续传)"
echo -e "  ├── gt_extraction.json             — GT 集"
echo -e "  ├── test_extraction.json           — 测试集 (后${TEST_COUNT}篇)"
echo -e "  ├── benchmark_dataset.json         — Evidence-Grounded GT"
echo -e "  ├── p1p5_batch_results.json        — P1-P5 假设文本"
echo -e "  ├── p1p5_eval_results.json         — P1-P5 评测详细结果"
echo -e "  ├── p1p5_comparison_summary.json   — P1-P5 方法对比汇总 ⭐"
echo -e "  └── p5_kg_eval_results.json        — P5 KG 深度评测"
echo ""
echo -e "${GREEN}全套流程运行完毕！${NC}"

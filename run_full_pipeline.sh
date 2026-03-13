#!/bin/bash
# ============================================================================
# CrossDisc Benchmark 全套流程运行脚本
# ============================================================================
# 输入: data/paper_1.json (92篇已分类的跨学科论文)
# 流程:
#   Step 1: 筛选跨学科论文 (本数据集92篇均为跨学科，直接使用)
#   Step 2: 对所有跨学科论文运行三阶段知识抽取 (概念→关系→查询→假设)
#   Step 3: 划分数据集 — 前N-3篇构建 Ground Truth，后3篇作为测试集
#   Step 4: 构建 Benchmark 数据集 (Ground Truth)
#   Step 5: 运行评测 (Evaluate)
# ============================================================================

set -e  # 遇到错误即停止

# ── 颜色输出 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_step() { echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"; echo -e "${GREEN}[STEP] $1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"; }
log_info() { echo -e "${YELLOW}[INFO] $1${NC}"; }
log_error() { echo -e "${RED}[ERROR] $1${NC}"; }

# ── 工作目录 ─────────────────────────────────────────────────────────────
PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

# ── 环境变量检查 ─────────────────────────────────────────────────────────
if [ -z "$OPENAI_API_KEY" ]; then
    log_error "OPENAI_API_KEY 未设置！请先执行:"
    echo '  export OPENAI_API_KEY="your-api-key"'
    echo '  export OPENAI_MODEL="genmini-2.5-pro"  # 或其他模型'
    echo '  export OPENAI_BASE_URL="http://api.shubiaobiao.cn/v1"  # 或其他API地址'
    exit 1
fi

log_info "OPENAI_MODEL = ${OPENAI_MODEL:-qwen3-235b-a22b (默认)}"
log_info "OPENAI_BASE_URL = ${OPENAI_BASE_URL:-http://api.shubiaobiao.cn/v1 (默认)}"

# ── 配置参数 ─────────────────────────────────────────────────────────────
INPUT_FILE="data/paper_1.json"
OUTPUT_DIR="outputs/full_pipeline_run"
NUM_WORKERS=2           # 并行worker数，根据API限流调整 (1=串行)
LANGUAGE_MODE="chinese"  # chinese | original
TEST_COUNT=3             # 测试集论文数量（取最后N篇）

mkdir -p "$OUTPUT_DIR"

# ── 文件路径定义 ─────────────────────────────────────────────────────────
EXTRACTION_RESULTS="$OUTPUT_DIR/extraction_results.jsonl"
EXTRACTION_JSON="$OUTPUT_DIR/extraction_results.json"
GT_PAPERS="$OUTPUT_DIR/gt_papers.json"
TEST_PAPERS="$OUTPUT_DIR/test_papers.json"
GT_EXTRACTION="$OUTPUT_DIR/gt_extraction.json"
TEST_EXTRACTION="$OUTPUT_DIR/test_extraction.json"
BENCHMARK_DATASET="$OUTPUT_DIR/benchmark_dataset.json"
TEST_PREDICTIONS="$OUTPUT_DIR/test_predictions.json"
EVAL_RESULTS="$OUTPUT_DIR/eval_results.json"


# ============================================================================
# Step 1: 确认跨学科论文
# ============================================================================
log_step "Step 1: 确认跨学科论文"

TOTAL_PAPERS=$(python3 -c "
import json
with open('$INPUT_FILE') as f:
    lines = [l.strip() for l in f if l.strip()]
cross = 0
for line in lines:
    paper = json.loads(line)
    if paper.get('non_main_levels', '').strip():
        cross += 1
print(f'{len(lines)} 篇论文中有 {cross} 篇跨学科论文')
print(cross)
" | tail -1)

log_info "共 $TOTAL_PAPERS 篇跨学科论文"
log_info "将使用前 $((TOTAL_PAPERS - TEST_COUNT)) 篇构建 Ground Truth"
log_info "后 $TEST_COUNT 篇作为测试集"


# ============================================================================
# Step 2: 三阶段知识抽取 (对全部92篇论文)
# ============================================================================
log_step "Step 2: 三阶段知识抽取 (概念→关系→查询→假设)"
log_info "输入: $INPUT_FILE"
log_info "输出: $EXTRACTION_RESULTS"
log_info "并行度: $NUM_WORKERS workers"
log_info "每篇论文约 9-11 次 LLM 调用，共 $TOTAL_PAPERS 篇"

python run.py batch \
    --input "$INPUT_FILE" \
    --output "$EXTRACTION_RESULTS" \
    --num-workers "$NUM_WORKERS" \
    --resume \
    --language-mode "$LANGUAGE_MODE"

log_info "抽取完成！结果: $EXTRACTION_RESULTS"


# ============================================================================
# Step 3: 划分数据集 — GT集 + 测试集
# ============================================================================
log_step "Step 3: 划分数据集 (GT集 + 测试集)"

python3 << 'SPLIT_SCRIPT'
import json
import sys
import os

output_dir = os.environ.get("OUTPUT_DIR", "outputs/full_pipeline_run")
extraction_file = os.path.join(output_dir, "extraction_results.jsonl")
test_count = int(os.environ.get("TEST_COUNT", "3"))

# 读取所有抽取结果
results = []
with open(extraction_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            results.append(json.loads(line))

# 仅保留成功的结果
ok_results = [r for r in results if r.get("ok")]
print(f"总共 {len(results)} 条记录，成功 {len(ok_results)} 条")

if len(ok_results) < test_count + 1:
    print(f"ERROR: 成功记录数 ({len(ok_results)}) 不足以划分 (需要至少 {test_count + 1} 条)")
    sys.exit(1)

# 划分: 后 test_count 篇为测试集，其余为 GT 集
gt_items = ok_results[:-test_count]
test_items = ok_results[-test_count:]

print(f"GT 集: {len(gt_items)} 篇")
print(f"测试集: {len(test_items)} 篇")

# 保存 GT 集和测试集 (JSON格式，供后续步骤使用)
gt_file = os.path.join(output_dir, "gt_extraction.json")
test_file = os.path.join(output_dir, "test_extraction.json")

with open(gt_file, "w", encoding="utf-8") as f:
    json.dump(gt_items, f, ensure_ascii=False, indent=2)
print(f"GT 集已保存: {gt_file}")

with open(test_file, "w", encoding="utf-8") as f:
    json.dump(test_items, f, ensure_ascii=False, indent=2)
print(f"测试集已保存: {test_file}")

# 同时保存完整结果为 JSON (build_dataset 需要)
all_file = os.path.join(output_dir, "extraction_results.json")
with open(all_file, "w", encoding="utf-8") as f:
    json.dump(ok_results, f, ensure_ascii=False, indent=2)
print(f"完整结果 JSON: {all_file}")
SPLIT_SCRIPT

log_info "数据集划分完成"


# ============================================================================
# Step 4: 构建 Benchmark 数据集 (Ground Truth)
# ============================================================================
log_step "Step 4: 构建 Benchmark 数据集 (Evidence-Grounded Ground Truth)"
log_info "使用 GT 集 ($GT_EXTRACTION) 构建知识图谱"
log_info "模式: evidence (基于证据的 GT 构建)"

python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$GT_EXTRACTION" \
    --output "$BENCHMARK_DATASET" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

log_info "Benchmark 数据集已构建: $BENCHMARK_DATASET"


# ============================================================================
# Step 5: 准备测试集预测文件 + 运行评测
# ============================================================================
log_step "Step 5: 运行评测 (Evaluate)"

# 测试集的 extraction 结果就是 predictions
# evaluate_benchmark.py 支持 parsed 格式 (即抽取结果)
log_info "Benchmark (GT): $BENCHMARK_DATASET"
log_info "Predictions (测试集): $TEST_EXTRACTION"

python -m crossdisc_extractor.benchmark.evaluate_benchmark \
    --benchmark "$BENCHMARK_DATASET" \
    --predictions "$TEST_EXTRACTION" \
    --output "$EVAL_RESULTS" \
    --taxonomy data/msc_converted.json

log_info "评测完成！结果: $EVAL_RESULTS"


# ============================================================================
# 最终输出汇总
# ============================================================================
log_step "全套流程完成！输出文件汇总"

echo -e "  📂 ${GREEN}$OUTPUT_DIR/${NC}"
echo -e "  ├── extraction_results.jsonl   — 全部论文的抽取结果 (JSONL, 断点续传用)"
echo -e "  ├── extraction_results.json    — 全部论文的抽取结果 (JSON)"
echo -e "  ├── gt_extraction.json         — GT集论文的抽取结果 (前N-3篇)"
echo -e "  ├── test_extraction.json       — 测试集论文的抽取结果 (后3篇)"
echo -e "  ├── benchmark_dataset.json     — Evidence-Grounded Benchmark 数据集"
echo -e "  └── eval_results.json          — 最终评测结果"

echo ""
log_info "评测结果预览:"
python3 -c "
import json
with open('$EVAL_RESULTS') as f:
    results = json.load(f)
print(f'评测论文数: {len(results)}')
for r in results:
    print(f\"\\n论文 ID: {r['id']}\")
    scores = r.get('scores', {})
    for key in sorted(scores.keys()):
        print(f'  {key}: {scores[key]:.4f}')
" 2>/dev/null || echo "  (评测结果文件将在运行完成后生成)"

echo ""
echo -e "${GREEN}全套流程运行完毕！${NC}"

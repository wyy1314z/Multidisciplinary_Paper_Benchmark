#!/bin/bash
# ============================================================================
# 基于 outputs/nature_nc_2024_gt_1000 的 GT 与抽取结果继续执行：
#   1) 用 benchmark 评估真实论文 hypothesis 的有效性
#   2) 做 query 驱动的模型能力 benchmark
#   3) 将自由文本 hypothesis 解析回结构化路径并统一打分
#   4) 对多模型做横向对比和雷达图分析
#
# 默认会先做 train/test 切分，避免用同一篇论文既构建 benchmark 又评估自身。
#
# 可配置环境变量：
#   SOURCE_DIR=outputs/nature_nc_2024_gt_1000
#   EVAL_DIR=outputs/nature_nc_2024_gt_1000/downstream_eval
#   TEST_COUNT=80
#   SPLIT_SEED=42
#   QUERY_MODELS="deepseek-v3,qwen3-235b-a22b"
#   PROMPT_LEVEL=all
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

SOURCE_DIR="${SOURCE_DIR:-outputs/nature_nc_2024_gt_1000}"
EVAL_DIR="${EVAL_DIR:-$SOURCE_DIR/downstream_eval}"
TEST_COUNT="${TEST_COUNT:-80}"
SPLIT_SEED="${SPLIT_SEED:-42}"
QUERY_MODELS="${QUERY_MODELS:-${OPENAI_MODEL:-deepseek-v3}}"
PROMPT_LEVEL="${PROMPT_LEVEL:-all}"

SOURCE_BENCHMARK="$SOURCE_DIR/benchmark_dataset_2024_nature_nc_1000.json"
SOURCE_EXTRACTIONS="$SOURCE_DIR/benchmark_extractions_2024_nature_nc_1000.jsonl"

TRAIN_BENCHMARK="$EVAL_DIR/benchmark_train.json"
TEST_EXTRACTIONS="$EVAL_DIR/test_extractions.jsonl"
SPLIT_SUMMARY="$EVAL_DIR/split_summary.json"

VALIDITY_RESULT="$EVAL_DIR/benchmark_validity_test.json"
VALIDITY_ANALYSIS="$EVAL_DIR/benchmark_validity_analysis_test.json"
QUERY_EVAL="$EVAL_DIR/query_eval_test.json"
QUERY_MODEL_DIR="$EVAL_DIR/query_model_results"
QUERY_SCORE_DIR="$EVAL_DIR/query_eval_scores"
RADAR_DIR="$EVAL_DIR/radar_charts"

TIMING_DIR="$EVAL_DIR/timing"
TIMING_JSONL="$TIMING_DIR/command_timings.jsonl"
TIMING_TSV="$TIMING_DIR/command_timings.tsv"
USAGE_DIR="$EVAL_DIR/usage"
USAGE_JSONL="$USAGE_DIR/llm_usage.jsonl"

mkdir -p "$EVAL_DIR" "$QUERY_MODEL_DIR" "$QUERY_SCORE_DIR" "$RADAR_DIR" "$TIMING_DIR" "$USAGE_DIR"

if [ "$1" = "--background" ] || [ "$1" = "-bg" ]; then
    LOG_FILE="$EVAL_DIR/pipeline.log"
    echo "启动后台运行，日志输出到: $LOG_FILE"
    echo "查看进度: tail -f $LOG_FILE"
    nohup bash "$0" --foreground > "$LOG_FILE" 2>&1 &
    BG_PID=$!
    echo $BG_PID > "$EVAL_DIR/pipeline.pid"
    echo "后台 PID: $BG_PID"
    exit 0
fi

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

log_step() {
    echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}[$(date '+%H:%M:%S')] [STEP] $1${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"
}

log_info() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] [INFO] $1${NC}"
}

if [ ! -f "$TIMING_TSV" ]; then
    printf 'stage\tcommand\tstart_epoch\tend_epoch\telapsed_sec\treal_sec\tuser_sec\tsys_sec\tmax_rss_kb\texit_code\n' > "$TIMING_TSV"
fi

append_timing_jsonl() {
    local stage="$1"
    local command_name="$2"
    local start_epoch="$3"
    local end_epoch="$4"
    local elapsed_sec="$5"
    local real_sec="$6"
    local user_sec="$7"
    local sys_sec="$8"
    local max_rss_kb="$9"
    local exit_code="${10}"
    python - <<PY
import json
record = {
    "stage": ${stage@Q},
    "command": ${command_name@Q},
    "start_epoch": int(${start_epoch}),
    "end_epoch": int(${end_epoch}),
    "elapsed_sec": float(${elapsed_sec}),
    "real_sec": float(${real_sec:-0}),
    "user_sec": float(${user_sec:-0}),
    "sys_sec": float(${sys_sec:-0}),
    "max_rss_kb": int(${max_rss_kb:-0}),
    "exit_code": int(${exit_code}),
}
with open(${TIMING_JSONL@Q}, "a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\\n")
PY
}

run_timed() {
    local stage="$1"
    local command_name="$2"
    shift 2

    local stats_file start_epoch end_epoch elapsed_sec exit_code
    local real_sec=0 user_sec=0 sys_sec=0 max_rss_kb=0
    stats_file="$(mktemp)"
    start_epoch="$(date +%s)"
    log_info "TIMING START [$stage] $command_name"

    set +e
    env \
        CROSSDISC_STAGE="$stage" \
        CROSSDISC_COMMAND="$command_name" \
        CROSSDISC_LLM_USAGE_LOG="$USAGE_JSONL" \
        /usr/bin/time -f "__TIME__ real=%e user=%U sys=%S maxrss=%M" -o "$stats_file" "$@"
    exit_code=$?
    set -e

    end_epoch="$(date +%s)"
    elapsed_sec=$((end_epoch - start_epoch))

    if grep -q "^__TIME__" "$stats_file" 2>/dev/null; then
        real_sec="$(sed -n 's/^__TIME__ real=\([^ ]*\) user=.*/\1/p' "$stats_file")"
        user_sec="$(sed -n 's/^__TIME__ real=[^ ]* user=\([^ ]*\) sys=.*/\1/p' "$stats_file")"
        sys_sec="$(sed -n 's/^__TIME__ real=[^ ]* user=[^ ]* sys=\([^ ]*\) maxrss=.*/\1/p' "$stats_file")"
        max_rss_kb="$(sed -n 's/^__TIME__ .* maxrss=\([^ ]*\)$/\1/p' "$stats_file")"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$stage" "$command_name" "$start_epoch" "$end_epoch" "$elapsed_sec" \
        "$real_sec" "$user_sec" "$sys_sec" "$max_rss_kb" "$exit_code" >> "$TIMING_TSV"
    append_timing_jsonl "$stage" "$command_name" "$start_epoch" "$end_epoch" "$elapsed_sec" "$real_sec" "$user_sec" "$sys_sec" "$max_rss_kb" "$exit_code"

    rm -f "$stats_file"
    log_info "TIMING END [$stage] $command_name exit=$exit_code elapsed=${elapsed_sec}s real=${real_sec}s rss=${max_rss_kb}KB"
    return "$exit_code"
}

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY 未设置"
    echo "请先执行：export OPENAI_API_KEY='你的key'"
    exit 1
fi

if [ ! -f "$SOURCE_BENCHMARK" ] || [ ! -f "$SOURCE_EXTRACTIONS" ]; then
    echo "ERROR: 找不到源数据："
    echo "  $SOURCE_BENCHMARK"
    echo "  $SOURCE_EXTRACTIONS"
    exit 1
fi

log_info "SOURCE_DIR=$SOURCE_DIR"
log_info "EVAL_DIR=$EVAL_DIR"
log_info "TEST_COUNT=$TEST_COUNT"
log_info "QUERY_MODELS=$QUERY_MODELS"
log_info "PROMPT_LEVEL=$PROMPT_LEVEL"

log_step "Stage 0: train/test 切分，避免 benchmark 自评估泄漏"
run_timed "stage0" "split_benchmark_and_test_extractions" \
python - <<PY
import json
import random
from pathlib import Path

source_benchmark = Path(${SOURCE_BENCHMARK@Q})
source_extractions = Path(${SOURCE_EXTRACTIONS@Q})
train_benchmark = Path(${TRAIN_BENCHMARK@Q})
test_extractions = Path(${TEST_EXTRACTIONS@Q})
split_summary = Path(${SPLIT_SUMMARY@Q})
test_count = int(${TEST_COUNT})
seed = int(${SPLIT_SEED})

rows = []
with source_extractions.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if item.get("ok") and item.get("parsed"):
            rows.append(item)

with source_benchmark.open(encoding="utf-8") as f:
    benchmark = json.load(f)

valid_titles = {r.get("title", "") for r in rows if r.get("title")}
rng = random.Random(seed)
titles = sorted(valid_titles)
rng.shuffle(titles)
test_titles = set(titles[: min(test_count, len(titles))])

train_entries = [
    e for e in benchmark
    if (e.get("input", {}).get("title") or "") not in test_titles
]
test_rows = [r for r in rows if r.get("title", "") in test_titles]

train_benchmark.parent.mkdir(parents=True, exist_ok=True)
with train_benchmark.open("w", encoding="utf-8") as f:
    json.dump(train_entries, f, ensure_ascii=False, indent=2)
with test_extractions.open("w", encoding="utf-8") as f:
    for row in test_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\\n")

summary = {
    "source_extraction_ok": len(rows),
    "source_benchmark_entries": len(benchmark),
    "test_count_requested": test_count,
    "test_count_actual": len(test_rows),
    "train_benchmark_entries": len(train_entries),
    "split_seed": seed,
    "test_titles": sorted(test_titles),
}
with split_summary.open("w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

log_step "Stage 1: 用 train benchmark 评估真实论文 hypothesis 有效性"
run_timed "stage1" "evaluate_benchmark_validity_on_test" \
python -m crossdisc_extractor.benchmark.evaluate_benchmark_validity \
    --benchmark "$TRAIN_BENCHMARK" \
    --extractions "$TEST_EXTRACTIONS" \
    --output "$VALIDITY_RESULT" \
    --taxonomy data/msc_converted.json

run_timed "stage1" "analyze_benchmark_validity_on_test" \
python scripts/analyze_benchmark_validity.py \
    --input "$VALIDITY_RESULT" \
    --output "$VALIDITY_ANALYSIS" \
    --min-journal-count 1

log_step "Stage 2: 构建 query-driven 测试集"
run_timed "stage2" "build_query_eval_set_from_test" \
python scripts/build_query_eval_set.py \
    --input "$TEST_EXTRACTIONS" \
    --output "$QUERY_EVAL"

log_step "Stage 3: query 驱动多模型生成自由文本 hypothesis"
run_timed "stage3" "run_query_benchmark_models" \
python run_query_benchmark.py \
    --input "$QUERY_EVAL" \
    --output-dir "$QUERY_MODEL_DIR" \
    --models "$QUERY_MODELS" \
    --prompt-level "$PROMPT_LEVEL"

log_step "Stage 4: 自由文本 hypothesis 解析回结构化路径并统一打分"
run_timed "stage4" "run_multimodel_eval_16metrics" \
python run_multimodel_eval_16metrics.py \
    --model-results-dir "$QUERY_MODEL_DIR" \
    --benchmark "$TRAIN_BENCHMARK" \
    --test-data "$QUERY_EVAL" \
    --input-mode query_eval \
    --output-dir "$QUERY_SCORE_DIR" \
    --taxonomy data/msc_converted.json

log_step "Stage 5: 生成多模型横向对比雷达图"
run_timed "stage5" "generate_multimodel_radar" \
python generate_multimodel_radar.py \
    --input "$QUERY_SCORE_DIR/multimodel_16metrics_summary.json" \
    --output-dir "$RADAR_DIR"

log_step "Stage 6: 汇总耗时和 token 消耗"
python scripts/summarize_stage_timings.py \
    --input "$TIMING_JSONL" \
    --output-json "$EVAL_DIR/timing_summary.json" \
    --output-md "$EVAL_DIR/timing_report.md"

python scripts/summarize_llm_usage.py \
    --input "$USAGE_JSONL" \
    --output-json "$EVAL_DIR/usage_summary.json" \
    --output-md "$EVAL_DIR/usage_report.md"

python - <<PY
import json
from pathlib import Path
summary = {
    "source_dir": ${SOURCE_DIR@Q},
    "eval_dir": ${EVAL_DIR@Q},
    "train_benchmark": ${TRAIN_BENCHMARK@Q},
    "test_extractions": ${TEST_EXTRACTIONS@Q},
    "benchmark_validity": ${VALIDITY_RESULT@Q},
    "benchmark_validity_analysis": ${VALIDITY_ANALYSIS@Q},
    "query_eval": ${QUERY_EVAL@Q},
    "query_model_results": ${QUERY_MODEL_DIR@Q},
    "query_eval_scores": ${QUERY_SCORE_DIR@Q},
    "radar_charts": ${RADAR_DIR@Q},
    "timing_summary": ${EVAL_DIR@Q} + "/timing_summary.json",
    "usage_summary": ${EVAL_DIR@Q} + "/usage_summary.json",
    "query_models": ${QUERY_MODELS@Q},
    "prompt_level": ${PROMPT_LEVEL@Q},
}
out = Path(${EVAL_DIR@Q}) / "pipeline_summary.json"
with out.open("w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

rm -f "$EVAL_DIR/pipeline.pid"

echo
echo "后续评测流程完成，主要产物："
echo "  - $VALIDITY_RESULT"
echo "  - $VALIDITY_ANALYSIS"
echo "  - $QUERY_EVAL"
echo "  - $QUERY_MODEL_DIR"
echo "  - $QUERY_SCORE_DIR/multimodel_16metrics_results.json"
echo "  - $QUERY_SCORE_DIR/multimodel_16metrics_summary.json"
echo "  - $RADAR_DIR"
echo "  - $EVAL_DIR/timing_summary.json"
echo "  - $EVAL_DIR/usage_summary.json"

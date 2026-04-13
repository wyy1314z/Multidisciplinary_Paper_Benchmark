#!/bin/bash
# ============================================================================
# 使用 2024 Nature/Nature Communications GT Benchmark 评估 2025 真实论文。
#
# 流程：
#   0) 从 nature_springer_2025.csv 按期刊均衡抽取候选池
#   1) 对候选池做跨学科分类
#   2) 从跨学科结果中按期刊均衡抽取 100 篇，每个入选期刊尽量 >=5 篇
#   3) 对 100 篇 2025 论文做三阶段知识抽取
#   4) 用 2024 GT benchmark 评估 2025 真实论文 hypothesis 有效性
#   5) 构建 query-driven 测试集
#   6) 多模型生成自由文本 hypothesis
#   7) 将自由文本解析回结构化路径并统一 16 指标打分
#   8) 生成多模型横向对比雷达图
#
# 可配置环境变量：
#   SOURCE_DIR=outputs/nature_nc_2024_gt_1000
#   EVAL_DIR=outputs/nature_nc_2024_gt_1000/eval_2025_validity
#   VALIDITY_CSV=/ssd/wangyuyang/git/data/raw_data/nature_springer_2025.csv
#   CANDIDATE_COUNT=1000
#   CANDIDATE_MIN_PER_JOURNAL=20
#   TARGET_COUNT=100
#   TARGET_MIN_PER_JOURNAL=5
#   NUM_WORKERS=8
#   CROSSDISC_THRESHOLD=0.5
#   QUERY_MODELS="deepseek-v3,qwen3-235b-a22b"
#   PROMPT_LEVEL=all
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

SOURCE_DIR="${SOURCE_DIR:-outputs/nature_nc_2024_gt_1000}"
EVAL_DIR="${EVAL_DIR:-$SOURCE_DIR/eval_2025_validity}"
VALIDITY_CSV="${VALIDITY_CSV:-/ssd/wangyuyang/git/data/raw_data/nature_springer_2025.csv}"
CANDIDATE_COUNT="${CANDIDATE_COUNT:-1000}"
CANDIDATE_MIN_PER_JOURNAL="${CANDIDATE_MIN_PER_JOURNAL:-20}"
TARGET_COUNT="${TARGET_COUNT:-100}"
TARGET_MIN_PER_JOURNAL="${TARGET_MIN_PER_JOURNAL:-5}"
SPLIT_SEED="${SPLIT_SEED:-42}"
NUM_WORKERS="${NUM_WORKERS:-8}"
CROSSDISC_THRESHOLD="${CROSSDISC_THRESHOLD:-0.5}"
LANGUAGE_MODE="${LANGUAGE_MODE:-chinese}"
QUERY_MODELS="${QUERY_MODELS:-${OPENAI_MODEL:-deepseek-v3}}"
PROMPT_LEVEL="${PROMPT_LEVEL:-all}"

SOURCE_BENCHMARK="$SOURCE_DIR/benchmark_dataset_2024_nature_nc_1000.json"

VALIDITY_RAW_CANDIDATES="$EVAL_DIR/validity_raw_2025_balanced_candidates.jsonl"
VALIDITY_RAW_BALANCE="$EVAL_DIR/validity_raw_2025_balanced_candidates_summary.json"
VALIDITY_CLASSIFIED_ALL="$EVAL_DIR/validity_classified_2025_candidates_all.jsonl"
VALIDITY_CLASSIFIED="$EVAL_DIR/validity_classified_2025_balanced_100.jsonl"
VALIDITY_CLASSIFIED_BALANCE="$EVAL_DIR/validity_classified_2025_balanced_100_summary.json"
VALIDITY_EXTRACTIONS="$EVAL_DIR/validity_extractions_2025_balanced_100.jsonl"
VALIDITY_RESULT="$EVAL_DIR/benchmark_validity_2025_balanced_100.json"
VALIDITY_ANALYSIS="$EVAL_DIR/benchmark_validity_analysis_2025_balanced_100.json"

QUERY_EVAL="$EVAL_DIR/query_eval_2025_balanced_100.json"
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

if [ ! -f "$SOURCE_BENCHMARK" ] || [ ! -f "$VALIDITY_CSV" ]; then
    echo "ERROR: 找不到源数据："
    echo "  $SOURCE_BENCHMARK"
    echo "  $VALIDITY_CSV"
    exit 1
fi

log_info "SOURCE_BENCHMARK=$SOURCE_BENCHMARK"
log_info "VALIDITY_CSV=$VALIDITY_CSV"
log_info "EVAL_DIR=$EVAL_DIR"
log_info "CANDIDATE_COUNT=$CANDIDATE_COUNT"
log_info "TARGET_COUNT=$TARGET_COUNT"
log_info "QUERY_MODELS=$QUERY_MODELS"

log_step "Stage 0: 从 2025 CSV 按期刊均衡抽取候选池"
run_timed "stage0" "prepare_2025_balanced_candidate_pool" \
python scripts/prepare_temporal_papers.py \
    --inputs "$VALIDITY_CSV" \
    --output "$VALIDITY_RAW_CANDIDATES" \
    --year-eq 2025 \
    --balanced-total "$CANDIDATE_COUNT" \
    --balanced-min-per-journal "$CANDIDATE_MIN_PER_JOURNAL" \
    --random-seed "$SPLIT_SEED" \
    --balanced-summary "$VALIDITY_RAW_BALANCE"

log_step "Stage 1: 对 2025 候选池做跨学科分类"
run_timed "stage1" "classify_2025_candidate_pool" \
python -m crossdisc_extractor.pipeline classify \
    --input "$VALIDITY_RAW_CANDIDATES" \
    --output "$VALIDITY_CLASSIFIED_ALL" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"

log_step "Stage 2: 从跨学科论文中按期刊均衡抽取 100 篇"
run_timed "stage2" "sample_2025_crossdisc_balanced_100" \
python scripts/sample_balanced_journals.py \
    --input "$VALIDITY_CLASSIFIED_ALL" \
    --output "$VALIDITY_CLASSIFIED" \
    --total "$TARGET_COUNT" \
    --min-per-journal "$TARGET_MIN_PER_JOURNAL" \
    --seed "$SPLIT_SEED" \
    --summary "$VALIDITY_CLASSIFIED_BALANCE" \
    --strict

log_step "Stage 3: 对 2025 均衡跨学科 100 篇做三阶段抽取"
run_timed "stage3" "extract_2025_balanced_100" \
python run.py batch \
    --input "$VALIDITY_CLASSIFIED" \
    --output "$VALIDITY_EXTRACTIONS" \
    --num-workers "$NUM_WORKERS" \
    --max-tokens-hyp 8192 \
    --language-mode "$LANGUAGE_MODE" \
    --resume

log_step "Stage 4: 用 2024 GT benchmark 评估 2025 真实论文 hypothesis 有效性"
run_timed "stage4" "evaluate_2025_real_hypothesis_validity" \
python -m crossdisc_extractor.benchmark.evaluate_benchmark_validity \
    --benchmark "$SOURCE_BENCHMARK" \
    --extractions "$VALIDITY_EXTRACTIONS" \
    --output "$VALIDITY_RESULT" \
    --taxonomy data/msc_converted.json

run_timed "stage4" "analyze_2025_validity_journal_correlation" \
python scripts/analyze_benchmark_validity.py \
    --input "$VALIDITY_RESULT" \
    --output "$VALIDITY_ANALYSIS" \
    --min-journal-count "$TARGET_MIN_PER_JOURNAL"

log_step "Stage 5: 构建 query-driven 测试集"
run_timed "stage5" "build_2025_query_eval_set" \
python scripts/build_query_eval_set.py \
    --input "$VALIDITY_EXTRACTIONS" \
    --output "$QUERY_EVAL"

log_step "Stage 6: query 驱动多模型生成自由文本 hypothesis"
run_timed "stage6" "run_2025_query_benchmark_models" \
python run_query_benchmark.py \
    --input "$QUERY_EVAL" \
    --output-dir "$QUERY_MODEL_DIR" \
    --models "$QUERY_MODELS" \
    --prompt-level "$PROMPT_LEVEL"

log_step "Stage 7: 自由文本 hypothesis 解析回结构化路径并统一打分"
run_timed "stage7" "run_2025_multimodel_eval_16metrics" \
python run_multimodel_eval_16metrics.py \
    --model-results-dir "$QUERY_MODEL_DIR" \
    --benchmark "$SOURCE_BENCHMARK" \
    --test-data "$QUERY_EVAL" \
    --input-mode query_eval \
    --output-dir "$QUERY_SCORE_DIR" \
    --taxonomy data/msc_converted.json

log_step "Stage 8: 生成多模型横向对比雷达图"
run_timed "stage8" "generate_2025_multimodel_radar" \
python generate_multimodel_radar.py \
    --input "$QUERY_SCORE_DIR/multimodel_16metrics_summary.json" \
    --output-dir "$RADAR_DIR"

log_step "Stage 9: 汇总耗时和 token 消耗"
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
    "source_benchmark": ${SOURCE_BENCHMARK@Q},
    "validity_csv": ${VALIDITY_CSV@Q},
    "eval_dir": ${EVAL_DIR@Q},
    "validity_raw_candidates": ${VALIDITY_RAW_CANDIDATES@Q},
    "validity_raw_balance": ${VALIDITY_RAW_BALANCE@Q},
    "validity_classified_all": ${VALIDITY_CLASSIFIED_ALL@Q},
    "validity_classified_balanced": ${VALIDITY_CLASSIFIED@Q},
    "validity_classified_balance": ${VALIDITY_CLASSIFIED_BALANCE@Q},
    "validity_extractions": ${VALIDITY_EXTRACTIONS@Q},
    "benchmark_validity": ${VALIDITY_RESULT@Q},
    "benchmark_validity_analysis": ${VALIDITY_ANALYSIS@Q},
    "query_eval": ${QUERY_EVAL@Q},
    "query_model_results": ${QUERY_MODEL_DIR@Q},
    "query_eval_scores": ${QUERY_SCORE_DIR@Q},
    "radar_charts": ${RADAR_DIR@Q},
    "timing_summary": ${EVAL_DIR@Q} + "/timing_summary.json",
    "usage_summary": ${EVAL_DIR@Q} + "/usage_summary.json",
    "candidate_count": int(${CANDIDATE_COUNT}),
    "candidate_min_per_journal": int(${CANDIDATE_MIN_PER_JOURNAL}),
    "target_count": int(${TARGET_COUNT}),
    "target_min_per_journal": int(${TARGET_MIN_PER_JOURNAL}),
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
echo "2025 validity / query benchmark 流程完成，主要产物："
echo "  - $VALIDITY_CLASSIFIED"
echo "  - $VALIDITY_EXTRACTIONS"
echo "  - $VALIDITY_RESULT"
echo "  - $VALIDITY_ANALYSIS"
echo "  - $QUERY_EVAL"
echo "  - $QUERY_SCORE_DIR/multimodel_16metrics_results.json"
echo "  - $QUERY_SCORE_DIR/multimodel_16metrics_summary.json"
echo "  - $RADAR_DIR"
echo "  - $EVAL_DIR/timing_summary.json"
echo "  - $EVAL_DIR/usage_summary.json"

#!/bin/bash
# ============================================================================
# 三阶段时序 Benchmark 小批量全流程测试 v1
# 目标：用约 100 篇文章快速验证三阶段流程是否可跑通
#   - 阶段一：2023/2024 构建 benchmark（默认 80 篇）
#   - 阶段二：2025 真实 hypothesis 验证 benchmark 有效性（默认 20 篇）
#   - 阶段三：2025 query 驱动模型生成，并用 benchmark 统一评测（默认 20 篇）
#
# 默认总规模：80 + 20 ≈ 100 篇
# 可通过环境变量覆盖：
#   BENCHMARK_COUNT=80
#   VALIDITY_COUNT=20
#   QUERY_COUNT=20
#   CROSSDISC_THRESHOLD=0.5
#   NUM_WORKERS=4
#   QUERY_MODELS="qwen3-235b-a22b"
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/temporal_100_v1}"
LOG_FILE="$OUTPUT_DIR/pipeline.log"
TIMING_DIR="$OUTPUT_DIR/timing"
TIMING_JSONL="$TIMING_DIR/command_timings.jsonl"
TIMING_TSV="$TIMING_DIR/command_timings.tsv"
USAGE_DIR="$OUTPUT_DIR/usage"
USAGE_JSONL="$USAGE_DIR/llm_usage.jsonl"
mkdir -p "$OUTPUT_DIR/stage_outputs" "$TIMING_DIR" "$USAGE_DIR"

if [ "$1" = "--background" ] || [ "$1" = "-bg" ]; then
    echo "启动后台运行，日志输出到: $LOG_FILE"
    echo "查看进度: tail -f $LOG_FILE"
    echo "停止运行: kill \$(cat $OUTPUT_DIR/pipeline.pid)"
    nohup bash "$0" --foreground > "$LOG_FILE" 2>&1 &
    BG_PID=$!
    echo $BG_PID > "$OUTPUT_DIR/pipeline.pid"
    echo "后台 PID: $BG_PID"
    exit 0
fi

if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

log_step() {
    echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}[$(date '+%H:%M:%S')] [STEP] $1${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"
}
log_info() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] [INFO] $1${NC}"; }

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
        real_sec="$(sed -n 's/^__TIME__ real=\\([^ ]*\\) user=.*/\\1/p' "$stats_file")"
        user_sec="$(sed -n 's/^__TIME__ real=[^ ]* user=\\([^ ]*\\) sys=.*/\\1/p' "$stats_file")"
        sys_sec="$(sed -n 's/^__TIME__ real=[^ ]* user=[^ ]* sys=\\([^ ]*\\) maxrss=.*/\\1/p' "$stats_file")"
        max_rss_kb="$(sed -n 's/^__TIME__ .* maxrss=\\([^ ]*\\)$/\\1/p' "$stats_file")"
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

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
log_info "HF_ENDPOINT=$HF_ENDPOINT"

BENCHMARK_COUNT="${BENCHMARK_COUNT:-80}"
VALIDITY_COUNT="${VALIDITY_COUNT:-20}"
QUERY_COUNT="${QUERY_COUNT:-20}"
NUM_WORKERS="${NUM_WORKERS:-4}"
CROSSDISC_THRESHOLD="${CROSSDISC_THRESHOLD:-0.5}"
LANGUAGE_MODE="${LANGUAGE_MODE:-chinese}"
QUERY_MODELS="${QUERY_MODELS:-${OPENAI_MODEL:-qwen3-235b-a22b}}"

BENCHMARK_RAW="$OUTPUT_DIR/benchmark_raw_2023_2024.jsonl"
BENCHMARK_CLASSIFIED="$OUTPUT_DIR/benchmark_classified_2023_2024.jsonl"
BENCHMARK_EXTRACTIONS="$OUTPUT_DIR/benchmark_extractions_2023_2024.jsonl"
BENCHMARK_DATASET="$OUTPUT_DIR/benchmark_dataset_2023_2024.json"

VALIDITY_RAW="$OUTPUT_DIR/validity_raw_2025.jsonl"
VALIDITY_CLASSIFIED="$OUTPUT_DIR/validity_classified_2025.jsonl"
VALIDITY_EXTRACTIONS="$OUTPUT_DIR/validity_extractions_2025.jsonl"
VALIDITY_RESULT="$OUTPUT_DIR/benchmark_validity_2025.json"
VALIDITY_ANALYSIS="$OUTPUT_DIR/benchmark_validity_analysis_2025.json"

QUERY_EVAL="$OUTPUT_DIR/query_eval_2025.json"
QUERY_MODEL_DIR="$OUTPUT_DIR/query_model_results"
QUERY_SCORE_DIR="$OUTPUT_DIR/query_eval_scores"

CSV_2023="/ssd/wangyuyang/git/data/raw_data/nature_springer_2023.csv"
CSV_2024="/ssd/wangyuyang/git/data/raw_data/nature_springer_2024.csv"
CSV_2025="/ssd/wangyuyang/git/data/raw_data/nature_springer_2025.csv"


# ============================================================================
# Stage 0: 2023/2024 预处理（benchmark 候选）
# ============================================================================
log_step "Stage 0: 预处理 2023/2024 原始数据 (benchmark 候选, limit=$BENCHMARK_COUNT)"

run_timed "stage0" "prepare_temporal_papers_benchmark" \
python scripts/prepare_temporal_papers.py \
    --inputs "$CSV_2023" "$CSV_2024" \
    --output "$BENCHMARK_RAW" \
    --year-lte 2024 \
    --limit "$BENCHMARK_COUNT"

BENCHMARK_RAW_COUNT=$(wc -l < "$BENCHMARK_RAW")
log_info "benchmark 原始记录: $BENCHMARK_RAW_COUNT"


# ============================================================================
# Stage 1: 2023/2024 分类筛选
# ============================================================================
log_step "Stage 1: benchmark 候选跨学科分类筛选"

run_timed "stage1" "classify_benchmark_candidates" \
python -m crossdisc_extractor.pipeline classify \
    --input "$BENCHMARK_RAW" \
    --output "$BENCHMARK_CLASSIFIED" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"

BENCHMARK_CLASSIFIED_COUNT=$(wc -l < "$BENCHMARK_CLASSIFIED")
log_info "benchmark 跨学科记录: $BENCHMARK_CLASSIFIED_COUNT"


# ============================================================================
# Stage 2: 2023/2024 三阶段抽取
# ============================================================================
log_step "Stage 2: benchmark 候选三阶段知识抽取"

run_timed "stage2" "extract_benchmark_candidates" \
python run.py batch \
    --input "$BENCHMARK_CLASSIFIED" \
    --output "$BENCHMARK_EXTRACTIONS" \
    --num-workers "$NUM_WORKERS" \
    --max-tokens-hyp 8192 \
    --language-mode "$LANGUAGE_MODE" \
    --resume

python - <<PY
import json, os
path = "$BENCHMARK_EXTRACTIONS"
ok = 0
total = 0
samples = []
with open(path, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        total += 1
        rec = json.loads(line)
        if rec.get("ok"):
            ok += 1
            if len(samples) < 3:
                samples.append(rec)
out = os.path.join("$OUTPUT_DIR", "stage_outputs", "benchmark_extraction_samples.json")
with open(out, "w", encoding="utf-8") as wf:
    json.dump(samples, wf, ensure_ascii=False, indent=2)
print(f"benchmark 抽取完成: {ok}/{total}")
PY


# ============================================================================
# Stage 3: 构建 benchmark 数据集
# ============================================================================
log_step "Stage 3: 构建 2023/2024 benchmark 数据集"

run_timed "stage3" "build_benchmark_dataset" \
python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$BENCHMARK_EXTRACTIONS" \
    --output "$BENCHMARK_DATASET" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

python - <<PY
import json, os
with open("$BENCHMARK_DATASET", encoding="utf-8") as f:
    data = json.load(f)
samples = data[:3]
out = os.path.join("$OUTPUT_DIR", "stage_outputs", "benchmark_dataset_samples.json")
with open(out, "w", encoding="utf-8") as wf:
    json.dump(samples, wf, ensure_ascii=False, indent=2)
print(f"benchmark 数据集条目: {len(data)}")
PY


# ============================================================================
# Stage 4: 2025 预处理（validity/query 集）
# ============================================================================
log_step "Stage 4: 预处理 2025 原始数据 (validity/query, limit=$VALIDITY_COUNT)"

run_timed "stage4" "prepare_temporal_papers_validity" \
python scripts/prepare_temporal_papers.py \
    --inputs "$CSV_2025" \
    --output "$VALIDITY_RAW" \
    --year-eq 2025 \
    --limit "$VALIDITY_COUNT"

VALIDITY_RAW_COUNT=$(wc -l < "$VALIDITY_RAW")
log_info "2025 原始记录: $VALIDITY_RAW_COUNT"


# ============================================================================
# Stage 5: 2025 分类筛选
# ============================================================================
log_step "Stage 5: 2025 跨学科分类筛选"

run_timed "stage5" "classify_validity_candidates" \
python -m crossdisc_extractor.pipeline classify \
    --input "$VALIDITY_RAW" \
    --output "$VALIDITY_CLASSIFIED" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"

VALIDITY_CLASSIFIED_COUNT=$(wc -l < "$VALIDITY_CLASSIFIED")
log_info "2025 跨学科记录: $VALIDITY_CLASSIFIED_COUNT"


# ============================================================================
# Stage 6: 2025 三阶段抽取
# ============================================================================
log_step "Stage 6: 2025 三阶段知识抽取"

run_timed "stage6" "extract_validity_candidates" \
python run.py batch \
    --input "$VALIDITY_CLASSIFIED" \
    --output "$VALIDITY_EXTRACTIONS" \
    --num-workers "$NUM_WORKERS" \
    --max-tokens-hyp 8192 \
    --language-mode "$LANGUAGE_MODE" \
    --resume

python - <<PY
import json, os
path = "$VALIDITY_EXTRACTIONS"
ok = 0
total = 0
samples = []
with open(path, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        total += 1
        rec = json.loads(line)
        if rec.get("ok"):
            ok += 1
            if len(samples) < 3:
                samples.append(rec)
out = os.path.join("$OUTPUT_DIR", "stage_outputs", "validity_extraction_samples.json")
with open(out, "w", encoding="utf-8") as wf:
    json.dump(samples, wf, ensure_ascii=False, indent=2)
print(f"2025 抽取完成: {ok}/{total}")
PY


# ============================================================================
# Stage 7: benchmark 有效性评估
# ============================================================================
log_step "Stage 7: 使用 2025 真实 hypothesis 验证 benchmark 有效性"

run_timed "stage7" "evaluate_benchmark_validity" \
python -m crossdisc_extractor.benchmark.evaluate_benchmark_validity \
    --benchmark "$BENCHMARK_DATASET" \
    --extractions "$VALIDITY_EXTRACTIONS" \
    --output "$VALIDITY_RESULT" \
    --taxonomy data/msc_converted.json \
    --max-items "$QUERY_COUNT"

run_timed "stage7" "analyze_benchmark_validity" \
python scripts/analyze_benchmark_validity.py \
    --input "$VALIDITY_RESULT" \
    --output "$VALIDITY_ANALYSIS" \
    --min-journal-count 1


# ============================================================================
# Stage 8: 构建 query 测试集
# ============================================================================
log_step "Stage 8: 从 2025 抽取结果构建 query-centric 测试集"

run_timed "stage8" "build_query_eval_set" \
python scripts/build_query_eval_set.py \
    --input "$VALIDITY_EXTRACTIONS" \
    --output "$QUERY_EVAL" \
    --max-items "$QUERY_COUNT"


# ============================================================================
# Stage 9: query 驱动模型生成
# ============================================================================
log_step "Stage 9: 基于 2025 query 驱动模型生成 hypothesis"

run_timed "stage9" "run_query_benchmark" \
python run_query_benchmark.py \
    --input "$QUERY_EVAL" \
    --output-dir "$QUERY_MODEL_DIR" \
    --models "$QUERY_MODELS" \
    --prompt-level L1 \
    --max-items "$QUERY_COUNT"


# ============================================================================
# Stage 10: 16 指标统一评测
# ============================================================================
log_step "Stage 10: 使用 benchmark 对模型结果做 16 指标统一评测"

run_timed "stage10" "run_multimodel_eval_16metrics" \
python run_multimodel_eval_16metrics.py \
    --model-results-dir "$QUERY_MODEL_DIR" \
    --benchmark "$BENCHMARK_DATASET" \
    --test-data "$QUERY_EVAL" \
    --input-mode query_eval \
    --output-dir "$QUERY_SCORE_DIR" \
    --taxonomy data/msc_converted.json \
    --max-items "$QUERY_COUNT"


# ============================================================================
# Stage 11: 汇总输出
# ============================================================================
log_step "Stage 11: 汇总输出"

python - <<PY
import json, os
summary = {
    "benchmark_raw": "$BENCHMARK_RAW",
    "benchmark_classified": "$BENCHMARK_CLASSIFIED",
    "benchmark_extractions": "$BENCHMARK_EXTRACTIONS",
    "benchmark_dataset": "$BENCHMARK_DATASET",
    "validity_raw": "$VALIDITY_RAW",
    "validity_classified": "$VALIDITY_CLASSIFIED",
    "validity_extractions": "$VALIDITY_EXTRACTIONS",
    "benchmark_validity": "$VALIDITY_RESULT",
    "benchmark_validity_analysis": "$VALIDITY_ANALYSIS",
    "query_eval": "$QUERY_EVAL",
    "query_model_results": "$QUERY_MODEL_DIR",
    "query_eval_scores": "$QUERY_SCORE_DIR",
    "llm_usage_log": "$USAGE_JSONL",
    "timing_log": "$TIMING_JSONL",
}
out = os.path.join("$OUTPUT_DIR", "pipeline_summary.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

log_info "小批量三阶段全流程完成"
echo -e "  输出目录: ${GREEN}$OUTPUT_DIR${NC}"
echo -e "  benchmark 数据集: ${GREEN}$BENCHMARK_DATASET${NC}"
echo -e "  有效性分析: ${GREEN}$VALIDITY_ANALYSIS${NC}"
echo -e "  模型评测结果: ${GREEN}$QUERY_SCORE_DIR${NC}"

rm -f "$OUTPUT_DIR/pipeline.pid"

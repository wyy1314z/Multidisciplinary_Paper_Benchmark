#!/bin/bash
# ============================================================================
# 从 nature_springer_YYYY.csv 中筛选 Nature / Nature Communications 共 N 篇，
# 识别跨学科论文，完成三阶段抽取并构建 evidence-grounded Benchmark GT 数据集。
#
# 产物：
#   - 原始筛选数据
#   - 跨学科分类结果
#   - 三阶段抽取结果
#   - GT benchmark 数据集
#   - 各阶段耗时统计
#   - LLM token / usage 汇总
#
# 环境变量：
#   INPUT_CSV=/ssd/wangyuyang/git/data/raw_data/nature_springer_2024.csv
#   DATA_YEAR=2024
#   RAW_LIMIT=1000
#   RUN_TAG=2024_nature_nc_1000
#   EXCLUDE_TITLES_FROM=outputs/nature_nc_2024_gt_1000/benchmark_raw_2024_nature_nc_1000.jsonl
#   NUM_WORKERS=8
#   CROSSDISC_THRESHOLD=0.5
#   LANGUAGE_MODE=chinese
#   OUTPUT_DIR=outputs/nature_nc_2024_gt_1000
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

INPUT_CSV="${INPUT_CSV:-/ssd/wangyuyang/git/data/raw_data/nature_springer_2024.csv}"
DATA_YEAR="${DATA_YEAR:-2024}"
RAW_LIMIT="${RAW_LIMIT:-1000}"
RUN_TAG="${RUN_TAG:-${DATA_YEAR}_nature_nc_${RAW_LIMIT}}"
EXCLUDE_TITLES_FROM="${EXCLUDE_TITLES_FROM:-}"
NUM_WORKERS="${NUM_WORKERS:-8}"
CROSSDISC_THRESHOLD="${CROSSDISC_THRESHOLD:-0.5}"
LANGUAGE_MODE="${LANGUAGE_MODE:-chinese}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/nature_nc_2024_gt_1000}"

LOG_FILE="$OUTPUT_DIR/pipeline.log"
TIMING_DIR="$OUTPUT_DIR/timing"
TIMING_JSONL="$TIMING_DIR/command_timings.jsonl"
TIMING_TSV="$TIMING_DIR/command_timings.tsv"
USAGE_DIR="$OUTPUT_DIR/usage"
USAGE_JSONL="$USAGE_DIR/llm_usage.jsonl"

RAW_JSONL="$OUTPUT_DIR/benchmark_raw_${RUN_TAG}.jsonl"
RAW_PREP_JSONL="$OUTPUT_DIR/benchmark_raw_${RUN_TAG}_pre_exclude.jsonl"
CLASSIFIED_JSONL="$OUTPUT_DIR/benchmark_classified_${RUN_TAG}.jsonl"
EXTRACTIONS_JSONL="$OUTPUT_DIR/benchmark_extractions_${RUN_TAG}.jsonl"
BENCHMARK_JSON="$OUTPUT_DIR/benchmark_dataset_${RUN_TAG}.json"
PIPELINE_SUMMARY_JSON="$OUTPUT_DIR/pipeline_summary.json"

mkdir -p "$OUTPUT_DIR" "$TIMING_DIR" "$USAGE_DIR"

if [ "$1" = "--background" ] || [ "$1" = "-bg" ]; then
    echo "启动后台运行，日志输出到: $LOG_FILE"
    echo "查看进度: tail -f $LOG_FILE"
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

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
log_info "INPUT_CSV=$INPUT_CSV"
log_info "DATA_YEAR=$DATA_YEAR"
log_info "RAW_LIMIT=$RAW_LIMIT"
log_info "RUN_TAG=$RUN_TAG"
log_info "EXCLUDE_TITLES_FROM=$EXCLUDE_TITLES_FROM"
log_info "NUM_WORKERS=$NUM_WORKERS"
log_info "CROSSDISC_THRESHOLD=$CROSSDISC_THRESHOLD"
log_info "OUTPUT_DIR=$OUTPUT_DIR"

log_step "Stage 0: 筛选 ${DATA_YEAR} 年 Nature / Nature Communications 论文"
if [ -n "$EXCLUDE_TITLES_FROM" ]; then
    if [ ! -f "$EXCLUDE_TITLES_FROM" ]; then
        echo "ERROR: EXCLUDE_TITLES_FROM 不存在: $EXCLUDE_TITLES_FROM"
        exit 1
    fi

    run_timed "stage0" "prepare_nature_nc_${DATA_YEAR}_candidates_before_exclusion" \
    python scripts/prepare_temporal_papers.py \
        --inputs "$INPUT_CSV" \
        --output "$RAW_PREP_JSONL" \
        --year-eq "$DATA_YEAR" \
        --include-journals "Nature" "Nature Communications"

    run_timed "stage0" "exclude_previous_and_limit_nature_nc_${DATA_YEAR}" \
    python - <<PY
import json
from pathlib import Path

source = Path(${RAW_PREP_JSONL@Q})
exclude_path = Path(${EXCLUDE_TITLES_FROM@Q})
output = Path(${RAW_JSONL@Q})
limit = int(${RAW_LIMIT})

def iter_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

exclude_titles = set()
exclude_dois = set()
for item in iter_jsonl(exclude_path):
    title = (item.get("title") or "").strip()
    doi = (item.get("doi") or "").strip()
    if title:
        exclude_titles.add(title)
    if doi:
        exclude_dois.add(doi)

selected = []
skipped = 0
seen = set()
for item in iter_jsonl(source):
    title = (item.get("title") or "").strip()
    doi = (item.get("doi") or "").strip()
    key = (title, doi)
    if title in exclude_titles or (doi and doi in exclude_dois):
        skipped += 1
        continue
    if key in seen:
        continue
    seen.add(key)
    selected.append(item)
    if len(selected) >= limit:
        break

output.parent.mkdir(parents=True, exist_ok=True)
with output.open("w", encoding="utf-8") as f:
    for item in selected:
        f.write(json.dumps(item, ensure_ascii=False) + "\\n")

summary = {
    "source": str(source),
    "exclude_path": str(exclude_path),
    "output": str(output),
    "limit": limit,
    "excluded_titles": len(exclude_titles),
    "excluded_dois": len(exclude_dois),
    "skipped_records": skipped,
    "selected_records": len(selected),
}
summary_path = output.with_suffix(".exclude_summary.json")
with summary_path.open("w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
if len(selected) < limit:
    raise SystemExit(f"只选到 {len(selected)} 篇，少于 RAW_LIMIT={limit}")
PY
else
    run_timed "stage0" "prepare_nature_nc_${DATA_YEAR}_candidates" \
    python scripts/prepare_temporal_papers.py \
        --inputs "$INPUT_CSV" \
        --output "$RAW_JSONL" \
        --year-eq "$DATA_YEAR" \
        --include-journals "Nature" "Nature Communications" \
        --limit "$RAW_LIMIT"
fi

RAW_COUNT=$(wc -l < "$RAW_JSONL")
log_info "原始候选论文数: $RAW_COUNT"

log_step "Stage 1: 跨学科分类筛选"
run_timed "stage1" "classify_nature_nc_${DATA_YEAR}_candidates" \
python -m crossdisc_extractor.pipeline classify \
    --input "$RAW_JSONL" \
    --output "$CLASSIFIED_JSONL" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"

CLASSIFIED_COUNT=$(wc -l < "$CLASSIFIED_JSONL")
log_info "跨学科论文数: $CLASSIFIED_COUNT"

if [ "$CLASSIFIED_COUNT" -eq 0 ]; then
    echo "未筛选出跨学科论文，流程终止。"
    exit 1
fi

log_step "Stage 2: 三阶段知识抽取"
run_timed "stage2" "extract_nature_nc_${DATA_YEAR}_crossdisc" \
python run.py batch \
    --input "$CLASSIFIED_JSONL" \
    --output "$EXTRACTIONS_JSONL" \
    --num-workers "$NUM_WORKERS" \
    --max-tokens-hyp 8192 \
    --language-mode "$LANGUAGE_MODE" \
    --resume

EXTRACTION_OK_COUNT=$(python - <<PY
import json
ok = 0
total = 0
with open(${EXTRACTIONS_JSONL@Q}, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        total += 1
        rec = json.loads(line)
        if rec.get("ok"):
            ok += 1
print(ok)
PY
)
log_info "抽取成功论文数: $EXTRACTION_OK_COUNT"

log_step "Stage 3: 构造 evidence-grounded Benchmark GT 数据集"
run_timed "stage3" "build_nature_nc_${DATA_YEAR}_gt_dataset" \
python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$EXTRACTIONS_JSONL" \
    --output "$BENCHMARK_JSON" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

BENCHMARK_COUNT=$(python - <<PY
import json
with open(${BENCHMARK_JSON@Q}, encoding="utf-8") as f:
    data = json.load(f)
print(len(data))
PY
)
log_info "GT 数据集条目数: $BENCHMARK_COUNT"

log_step "Stage 4: 汇总耗时与 token 消耗"
python scripts/summarize_stage_timings.py \
    --input "$TIMING_JSONL" \
    --output-json "$OUTPUT_DIR/timing_summary.json" \
    --output-md "$OUTPUT_DIR/timing_report.md"

python scripts/summarize_llm_usage.py \
    --input "$USAGE_JSONL" \
    --output-json "$OUTPUT_DIR/usage_summary.json" \
    --output-md "$OUTPUT_DIR/usage_report.md"

python - <<PY
import json
summary = {
    "input_csv": ${INPUT_CSV@Q},
    "data_year": int(${DATA_YEAR}),
    "raw_limit": int(${RAW_LIMIT}),
    "run_tag": ${RUN_TAG@Q},
    "exclude_titles_from": ${EXCLUDE_TITLES_FROM@Q},
    "journals": ["Nature", "Nature Communications"],
    "crossdisc_threshold": float(${CROSSDISC_THRESHOLD}),
    "num_workers": int(${NUM_WORKERS}),
    "language_mode": ${LANGUAGE_MODE@Q},
    "paths": {
        "benchmark_raw": ${RAW_JSONL@Q},
        "benchmark_classified": ${CLASSIFIED_JSONL@Q},
        "benchmark_extractions": ${EXTRACTIONS_JSONL@Q},
        "benchmark_dataset": ${BENCHMARK_JSON@Q},
        "timing_summary": ${OUTPUT_DIR@Q} + "/timing_summary.json",
        "usage_summary": ${OUTPUT_DIR@Q} + "/usage_summary.json",
    },
    "counts": {
        "raw_candidates": int(${RAW_COUNT}),
        "crossdisciplinary_candidates": int(${CLASSIFIED_COUNT}),
        "successful_extractions": int(${EXTRACTION_OK_COUNT}),
        "gt_entries": int(${BENCHMARK_COUNT}),
    },
}
with open(${PIPELINE_SUMMARY_JSON@Q}, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
PY

echo
echo "流程完成，主要产物："
echo "  - $RAW_JSONL"
echo "  - $CLASSIFIED_JSONL"
echo "  - $EXTRACTIONS_JSONL"
echo "  - $BENCHMARK_JSON"
echo "  - $OUTPUT_DIR/timing_summary.json"
echo "  - $OUTPUT_DIR/usage_summary.json"
echo "  - $PIPELINE_SUMMARY_JSON"

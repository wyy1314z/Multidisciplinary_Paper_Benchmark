#!/usr/bin/env bash
set -euo pipefail

PROJ_DIR="${PROJ_DIR:-/ssd/wangyuyang/git/benchmark}"
cd "$PROJ_DIR"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/querycentric_2025_300_v1}"
INPUT_CSV="${INPUT_CSV:-/ssd/wangyuyang/git/data/raw_data/nature_springer_2025.csv}"
RAW_LIMIT="${RAW_LIMIT:-300}"
CANDIDATE_LIMIT="${CANDIDATE_LIMIT:-$RAW_LIMIT}"
QUERY_LIMIT="${QUERY_LIMIT:-$RAW_LIMIT}"
INCLUDE_JOURNALS="${INCLUDE_JOURNALS:-}"
RESET_LOGS="${RESET_LOGS:-1}"
NUM_WORKERS="${NUM_WORKERS:-8}"
CROSSDISC_THRESHOLD="${CROSSDISC_THRESHOLD:-0.5}"
LANGUAGE_MODE="${LANGUAGE_MODE:-chinese}"
MODELS="${MODELS:-gpt-3.5-turbo-0125,gpt-4-turbo-2024-04-09,gpt-4o-mini-2024-07-18,gpt-4o-2024-11-20,o1-2024-12-17,claude-3-5-haiku-20241022,claude-3-5-sonnet-20241022,deepseek-v3,doubao-pro-32k-241215}"
EVAL_MODEL="${EVAL_MODEL:-gpt-4o-mini-2024-07-18}"
BENCHMARK="${BENCHMARK:-outputs/temporal_3000_diag_v1/benchmark_dataset_2023_2024.json}"

RAW_JSONL="$OUTPUT_DIR/raw_2025_candidates.jsonl"
CLASSIFIED_ALL_JSONL="$OUTPUT_DIR/classified_2025_candidates_crossdisc.jsonl"
CLASSIFIED_JSONL="$OUTPUT_DIR/classified_2025_query_crossdisc.jsonl"
EXTRACTIONS_JSONL="$OUTPUT_DIR/extractions_2025_query_crossdisc.jsonl"
QUERY_EVAL_JSON="$OUTPUT_DIR/query_eval_2025_query.json"
QUERY_MODEL_DIR="$OUTPUT_DIR/query_model_results"
QUERY_SCORE_DIR="$OUTPUT_DIR/query_eval_scores"
RADAR_DIR="$OUTPUT_DIR/radar_charts"
USAGE_DIR="$OUTPUT_DIR/usage"
USAGE_JSONL="$USAGE_DIR/llm_usage.jsonl"
TIMING_DIR="$OUTPUT_DIR/timing"
TIMING_JSONL="$TIMING_DIR/command_timings.jsonl"

mkdir -p "$OUTPUT_DIR" "$QUERY_MODEL_DIR" "$QUERY_SCORE_DIR" "$RADAR_DIR" "$USAGE_DIR" "$TIMING_DIR"

if [ "${1:-}" = "--background" ] || [ "${1:-}" = "-bg" ]; then
  echo "Starting background run. Log: $OUTPUT_DIR/pipeline.log"
  echo "Watch progress: tail -f $OUTPUT_DIR/pipeline.log"
  nohup bash "$0" --foreground > "$OUTPUT_DIR/pipeline.log" 2>&1 &
  BG_PID=$!
  echo "$BG_PID" > "$OUTPUT_DIR/pipeline.pid"
  echo "Background PID: $BG_PID"
  exit 0
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY is not set. Export your OpenAI-compatible gateway key first." >&2
  exit 1
fi

if [ ! -f "$BENCHMARK" ]; then
  echo "ERROR: benchmark dataset not found: $BENCHMARK" >&2
  exit 1
fi

export CROSSDISC_LLM_USAGE_LOG="$USAGE_JSONL"

run_stage() {
  local stage="$1"
  local command_name="$2"
  shift 2
  echo "[$stage] $command_name"

  local start end exit_code
  start="$(python - <<'PY'
import time
print(time.time())
PY
)"

  set +e
  CROSSDISC_STAGE="$stage" CROSSDISC_COMMAND="$command_name" "$@"
  exit_code=$?
  set -e

  end="$(python - <<'PY'
import time
print(time.time())
PY
)"

  python - "$TIMING_JSONL" "$stage" "$command_name" "$start" "$end" "$exit_code" "$*" <<'PY'
import json, sys
path, stage, command, start, end, exit_code, argv = sys.argv[1:]
row = {
    "stage": stage,
    "command": command,
    "argv": argv,
    "elapsed_sec": round(float(end) - float(start), 4),
    "real_sec": round(float(end) - float(start), 4),
    "max_rss_kb": 0,
    "exit_code": int(exit_code),
}
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
PY

  return "$exit_code"
}

if [ "$RESET_LOGS" = "1" ]; then
  : > "$TIMING_JSONL"
  : > "$USAGE_JSONL"
else
  touch "$TIMING_JSONL" "$USAGE_JSONL"
fi

echo "[1/7] Prepare 2025 raw papers: $RAW_JSONL"
if [ ! -s "$RAW_JSONL" ]; then
  PREPARE_ARGS=(
    python scripts/prepare_temporal_papers.py \
    --inputs "$INPUT_CSV" \
    --output "$RAW_JSONL" \
    --year-eq 2025 \
    --limit "$CANDIDATE_LIMIT"
  )
  if [ -n "$INCLUDE_JOURNALS" ]; then
    PREPARE_ARGS+=(--include-journals "$INCLUDE_JOURNALS")
  fi
  run_stage prepare prepare_2025_raw "${PREPARE_ARGS[@]}"
else
  echo "  Reusing existing $RAW_JSONL"
fi

echo "[2/7] Classify and filter cross-disciplinary papers: $CLASSIFIED_ALL_JSONL"
if [ ! -s "$CLASSIFIED_ALL_JSONL" ]; then
  run_stage classify classify_crossdisc \
    python -m crossdisc_extractor.pipeline classify \
    --input "$RAW_JSONL" \
    --output "$CLASSIFIED_ALL_JSONL" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"
else
  echo "  Reusing existing $CLASSIFIED_ALL_JSONL"
fi

CLASSIFIED_COUNT="$(wc -l < "$CLASSIFIED_ALL_JSONL" | tr -d ' ')"
if [ "$CLASSIFIED_COUNT" -eq 0 ]; then
  echo "ERROR: no cross-disciplinary papers after classification." >&2
  exit 1
fi
if [ "$CLASSIFIED_COUNT" -lt "$QUERY_LIMIT" ]; then
  echo "ERROR: only $CLASSIFIED_COUNT cross-disciplinary papers found; need $QUERY_LIMIT. Increase CANDIDATE_LIMIT." >&2
  exit 1
fi

echo "[3/7] Select $QUERY_LIMIT cross-disciplinary papers: $CLASSIFIED_JSONL"
run_stage select select_query_papers \
  python - "$CLASSIFIED_ALL_JSONL" "$CLASSIFIED_JSONL" "$QUERY_LIMIT" <<'PY'
import sys
src, dst, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as out:
    for i, line in enumerate(f):
        if i >= n:
            break
        out.write(line)
PY

echo "[4/7] Extract CrossDisc queries and hypotheses: $EXTRACTIONS_JSONL"
run_stage extract extract_crossdisc_queries \
  python run.py batch \
  --input "$CLASSIFIED_JSONL" \
  --output "$EXTRACTIONS_JSONL" \
  --num-workers "$NUM_WORKERS" \
  --max-tokens-hyp 8192 \
  --language-mode "$LANGUAGE_MODE" \
  --resume

echo "[5/7] Build query-centric evaluation set: $QUERY_EVAL_JSON"
run_stage build_query_eval build_query_eval_set \
  python scripts/build_query_eval_set.py \
  --input "$EXTRACTIONS_JSONL" \
  --output "$QUERY_EVAL_JSON" \
  --max-items "$QUERY_LIMIT"

QUERY_COUNT="$(python - <<PY
import json
with open(${QUERY_EVAL_JSON@Q}, encoding="utf-8") as f:
    print(len(json.load(f)))
PY
)"
if [ "$QUERY_COUNT" -eq 0 ]; then
  echo "ERROR: query evaluation set is empty." >&2
  exit 1
fi

echo "[6/7] Generate hypotheses for models: $MODELS"
run_stage query_generation generate_multimodel_hypotheses \
  python run_query_benchmark.py \
  --input "$QUERY_EVAL_JSON" \
  --output-dir "$QUERY_MODEL_DIR" \
  --models "$MODELS" \
  --prompt-level L1 \
  --max-consecutive-errors 1 \
  --max-items "$QUERY_COUNT"

echo "[7/7] Evaluate model outputs with judge model: $EVAL_MODEL"
IFS=',' read -r -a MODEL_ARRAY <<< "$MODELS"
run_stage eval evaluate_16_metrics \
  env OPENAI_MODEL="$EVAL_MODEL" python run_multimodel_eval_16metrics.py \
  --model-results-dir "$QUERY_MODEL_DIR" \
  --benchmark "$BENCHMARK" \
  --test-data "$QUERY_EVAL_JSON" \
  --input-mode query_eval \
  --output-dir "$QUERY_SCORE_DIR" \
  --taxonomy data/msc_converted.json \
  --include-models "${MODEL_ARRAY[@]}" \
  --max-items "$QUERY_COUNT"

run_stage radar generate_x5_radar \
  python generate_x5_radar.py \
  --input "$QUERY_SCORE_DIR/multimodel_16metrics_summary.json" \
  --output-dir "$RADAR_DIR" \
  --level L1

run_stage summarize summarize_timing \
  python scripts/summarize_stage_timings.py \
  --input "$TIMING_JSONL" \
  --output-json "$TIMING_DIR/timing_summary.json" \
  --output-md "$TIMING_DIR/timing_summary.md"

run_stage summarize summarize_llm_usage \
  python scripts/summarize_llm_usage.py \
  --input "$USAGE_JSONL" \
  --output-json "$USAGE_DIR/usage_summary.json" \
  --output-md "$USAGE_DIR/usage_summary.md"

python - <<PY
import json
from pathlib import Path

out = Path(${OUTPUT_DIR@Q})
summary = {
    "input_csv": ${INPUT_CSV@Q},
    "candidate_limit": int(${CANDIDATE_LIMIT@Q}),
    "query_limit": int(${QUERY_LIMIT@Q}),
    "include_journals": ${INCLUDE_JOURNALS@Q},
    "models": ${MODELS@Q}.split(","),
    "eval_model": ${EVAL_MODEL@Q},
    "benchmark": ${BENCHMARK@Q},
    "paths": {
        "raw": ${RAW_JSONL@Q},
        "classified": ${CLASSIFIED_JSONL@Q},
        "extractions": ${EXTRACTIONS_JSONL@Q},
        "query_eval": ${QUERY_EVAL_JSON@Q},
        "query_model_results": ${QUERY_MODEL_DIR@Q},
        "query_eval_scores": ${QUERY_SCORE_DIR@Q},
        "radar_charts": ${RADAR_DIR@Q},
        "x5_radar": ${RADAR_DIR@Q} + "/x5_radar_all_models.png",
        "x5_scores": ${RADAR_DIR@Q} + "/x5_scores.json",
        "usage_log": ${USAGE_JSONL@Q},
        "usage_summary": ${USAGE_DIR@Q} + "/usage_summary.md",
        "timing_log": ${TIMING_JSONL@Q},
        "timing_summary": ${TIMING_DIR@Q} + "/timing_summary.md",
    },
    "counts": {
        "raw": sum(1 for line in open(${RAW_JSONL@Q}, encoding="utf-8") if line.strip()),
        "classified_crossdisc_candidates": sum(1 for line in open(${CLASSIFIED_ALL_JSONL@Q}, encoding="utf-8") if line.strip()),
        "classified_crossdisc": sum(1 for line in open(${CLASSIFIED_JSONL@Q}, encoding="utf-8") if line.strip()),
        "extractions_total": sum(1 for line in open(${EXTRACTIONS_JSONL@Q}, encoding="utf-8") if line.strip()),
        "query_eval": len(json.load(open(${QUERY_EVAL_JSON@Q}, encoding="utf-8"))),
    },
}
(out / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

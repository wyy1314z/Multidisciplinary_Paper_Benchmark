#!/bin/bash
# ============================================================================
# 三阶段时序 Benchmark 小批量诊断版复跑脚本 v1
# 目标：复用 run_temporal_100_v1.sh 跑完整流程，并自动产出诊断摘要
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/temporal_100_diag_v1}"
LOG_FILE="$OUTPUT_DIR/pipeline.log"
mkdir -p "$OUTPUT_DIR/stage_outputs"

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

echo "运行目录: $OUTPUT_DIR"
echo "第一阶段到第三阶段将复用 run_temporal_100_v1.sh"

set +e
OUTPUT_DIR="$OUTPUT_DIR" bash run_temporal_100_v1.sh --foreground
PIPE_RC=$?
set -e

echo
echo "开始生成诊断报告..."
python scripts/diagnose_temporal_run.py --output-dir "$OUTPUT_DIR"
DIAG_RC=$?

if [ -f "$OUTPUT_DIR/timing/command_timings.jsonl" ]; then
    echo
    echo "开始生成耗时汇总..."
    python scripts/summarize_stage_timings.py \
        --input "$OUTPUT_DIR/timing/command_timings.jsonl" \
        --output-json "$OUTPUT_DIR/timing_summary.json" \
        --output-md "$OUTPUT_DIR/timing_report.md"
    TIMING_RC=$?
else
    TIMING_RC=0
fi

if [ -f "$OUTPUT_DIR/usage/llm_usage.jsonl" ]; then
    echo
    echo "开始生成 token / usage 汇总..."
    python scripts/summarize_llm_usage.py \
        --input "$OUTPUT_DIR/usage/llm_usage.jsonl" \
        --output-json "$OUTPUT_DIR/usage_summary.json" \
        --output-md "$OUTPUT_DIR/usage_report.md"
    USAGE_RC=$?
else
    USAGE_RC=0
fi

if [ $PIPE_RC -ne 0 ]; then
    echo "主流程退出码: $PIPE_RC"
fi
if [ $DIAG_RC -ne 0 ]; then
    echo "诊断脚本退出码: $DIAG_RC"
fi
if [ $TIMING_RC -ne 0 ]; then
    echo "耗时汇总退出码: $TIMING_RC"
fi
if [ $USAGE_RC -ne 0 ]; then
    echo "usage 汇总退出码: $USAGE_RC"
fi

echo
echo "诊断产物:"
echo "  - $OUTPUT_DIR/diagnosis_summary.json"
echo "  - $OUTPUT_DIR/diagnosis_report.md"
if [ -f "$OUTPUT_DIR/timing_summary.json" ]; then
    echo "  - $OUTPUT_DIR/timing_summary.json"
    echo "  - $OUTPUT_DIR/timing_report.md"
fi
if [ -f "$OUTPUT_DIR/usage_summary.json" ]; then
    echo "  - $OUTPUT_DIR/usage_summary.json"
    echo "  - $OUTPUT_DIR/usage_report.md"
fi

if [ $PIPE_RC -ne 0 ]; then
    exit $PIPE_RC
fi
if [ $DIAG_RC -ne 0 ]; then
    exit $DIAG_RC
fi
if [ $TIMING_RC -ne 0 ]; then
    exit $TIMING_RC
fi
exit $USAGE_RC

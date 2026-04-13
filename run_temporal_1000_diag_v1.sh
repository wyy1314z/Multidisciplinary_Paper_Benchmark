#!/bin/bash
# ============================================================================
# 三阶段时序 Benchmark 诊断版中规模测试 v1
# 默认规模：800 + 200 ≈ 1000 篇
#   - benchmark: 2023/2024 共 800 篇
#   - validity/query: 2025 共 200 篇
# 说明：
#   - 复用 run_temporal_100_diag_v1.sh
#   - 跑完自动生成 diagnosis_summary.json / diagnosis_report.md
# 可通过环境变量覆盖：
#   BENCHMARK_COUNT=800
#   VALIDITY_COUNT=200
#   QUERY_COUNT=200
#   NUM_WORKERS=8
#   CROSSDISC_THRESHOLD=0.5
#   OUTPUT_DIR=outputs/temporal_1000_diag_v1
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

export BENCHMARK_COUNT="${BENCHMARK_COUNT:-800}"
export VALIDITY_COUNT="${VALIDITY_COUNT:-200}"
export QUERY_COUNT="${QUERY_COUNT:-200}"
export NUM_WORKERS="${NUM_WORKERS:-8}"
export OUTPUT_DIR="${OUTPUT_DIR:-outputs/temporal_1000_diag_v1}"

echo "启动 1000 篇级别诊断版测试"
echo "  BENCHMARK_COUNT=$BENCHMARK_COUNT"
echo "  VALIDITY_COUNT=$VALIDITY_COUNT"
echo "  QUERY_COUNT=$QUERY_COUNT"
echo "  NUM_WORKERS=$NUM_WORKERS"
echo "  OUTPUT_DIR=$OUTPUT_DIR"

bash "$PROJ_DIR/run_temporal_100_diag_v1.sh" "$@"

#!/bin/bash
# ============================================================================
# 三阶段时序 Benchmark 诊断版大规模测试 v1
# 默认规模：2400 + 600 ≈ 3000 篇
#   - benchmark: 2023/2024 共 2400 篇
#   - validity/query: 2025 共 600 篇
# 说明：
#   - 复用 run_temporal_100_diag_v1.sh
#   - 跑完自动生成 diagnosis_summary.json / diagnosis_report.md
# 可通过环境变量覆盖：
#   BENCHMARK_COUNT=2400
#   VALIDITY_COUNT=600
#   QUERY_COUNT=600
#   NUM_WORKERS=12
#   CROSSDISC_THRESHOLD=0.5
#   OUTPUT_DIR=outputs/temporal_3000_diag_v1
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

export BENCHMARK_COUNT="${BENCHMARK_COUNT:-2400}"
export VALIDITY_COUNT="${VALIDITY_COUNT:-600}"
export QUERY_COUNT="${QUERY_COUNT:-600}"
export NUM_WORKERS="${NUM_WORKERS:-12}"
export OUTPUT_DIR="${OUTPUT_DIR:-outputs/temporal_3000_diag_v1}"

echo "启动 3000 篇级别诊断版测试"
echo "  BENCHMARK_COUNT=$BENCHMARK_COUNT"
echo "  VALIDITY_COUNT=$VALIDITY_COUNT"
echo "  QUERY_COUNT=$QUERY_COUNT"
echo "  NUM_WORKERS=$NUM_WORKERS"
echo "  OUTPUT_DIR=$OUTPUT_DIR"

bash "$PROJ_DIR/run_temporal_100_diag_v1.sh" "$@"

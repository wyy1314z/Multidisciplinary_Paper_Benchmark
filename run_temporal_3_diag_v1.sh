#!/bin/bash
# ============================================================================
# 三阶段时序 Benchmark 超小规模 smoke test v1
# 目标：使用极小样本检查各环节的耗时和 LLM token 使用
# 默认配置偏向“可观察所有阶段”而不是正式实验：
#   - benchmark: 3 篇
#   - validity/query: 3 篇
#   - 单 worker
#   - 禁用 SBERT GPU
#   - 禁用 LLM stream，优先拿真实 usage
# 可通过环境变量覆盖：
#   BENCHMARK_COUNT=3
#   VALIDITY_COUNT=3
#   QUERY_COUNT=3
#   NUM_WORKERS=1
#   CROSSDISC_THRESHOLD=0.0
#   CROSSDISC_LLM_STREAM=0
#   OUTPUT_DIR=outputs/temporal_3_diag_v1
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

export BENCHMARK_COUNT="${BENCHMARK_COUNT:-3}"
export VALIDITY_COUNT="${VALIDITY_COUNT:-3}"
export QUERY_COUNT="${QUERY_COUNT:-3}"
export NUM_WORKERS="${NUM_WORKERS:-1}"
export CROSSDISC_THRESHOLD="${CROSSDISC_THRESHOLD:-0.0}"
export CROSSDISC_SBERT_DEVICE="${CROSSDISC_SBERT_DEVICE:-no-gpu}"
export CROSSDISC_LLM_STREAM="${CROSSDISC_LLM_STREAM:-0}"
export OUTPUT_DIR="${OUTPUT_DIR:-outputs/temporal_3_diag_v1}"

echo "启动 3 篇级别 smoke test"
echo "  BENCHMARK_COUNT=$BENCHMARK_COUNT"
echo "  VALIDITY_COUNT=$VALIDITY_COUNT"
echo "  QUERY_COUNT=$QUERY_COUNT"
echo "  NUM_WORKERS=$NUM_WORKERS"
echo "  CROSSDISC_THRESHOLD=$CROSSDISC_THRESHOLD"
echo "  CROSSDISC_SBERT_DEVICE=$CROSSDISC_SBERT_DEVICE"
echo "  CROSSDISC_LLM_STREAM=$CROSSDISC_LLM_STREAM"
echo "  OUTPUT_DIR=$OUTPUT_DIR"

bash "$PROJ_DIR/run_temporal_100_diag_v1.sh" "$@"

#!/bin/bash
# ===========================================================================
#  run_comparison_experiment.sh
#  跨学科假设生成 Benchmark 实际对比实验
#
#  所有命令默认后台运行 (nohup)，日志写入 OUTPUT_DIR。
#  加 --fg 参数可前台运行。
#
#  用法:
#    # 第 0 步：准备数据（不需要 API key，前台即可）
#    bash run_comparison_experiment.sh prepare
#
#    # 第 1 步：小规模测试（后台运行，2篇 × 11种方法）
#    bash run_comparison_experiment.sh phase1
#
#    # 第 2 步：完整实验（后台运行，6篇 × 11种方法）
#    bash run_comparison_experiment.sh phase2
#
#    # 第 3 步：评估（后台运行）
#    bash run_comparison_experiment.sh eval1
#    bash run_comparison_experiment.sh eval2
#
#    # 第 4 步：生成对比报告（前台即可）
#    bash run_comparison_experiment.sh report
#
#    # 一键全部后台运行（prepare + phase2 + eval2 + report 串行）
#    bash run_comparison_experiment.sh all
#
#    # 查看进度
#    bash run_comparison_experiment.sh status
#
#    # 查看实时日志
#    bash run_comparison_experiment.sh logs [phase1|phase2|eval1|eval2]
#
#    # 前台运行（调试用）
#    bash run_comparison_experiment.sh phase1 --fg
# ===========================================================================
set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────────────
# ⚠️  请在运行前设置以下环境变量:
#   export OPENAI_API_KEY="your-api-key-here"
#   export OPENAI_BASE_URL="https://uni-api.cstcloud.cn/v1"   # 或其他兼容端点
#   export OPENAI_MODEL="deepseek-v3"                          # 可选，默认用 config

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

OUTPUT_DIR="baseline/outputs/comparison_2025"
DATA_DIR="baseline/data"
PAPERS_FILE="$DATA_DIR/papers_6_2025.json"
PID_FILE="$OUTPUT_DIR/.running.pid"
MASTER_LOG="$OUTPUT_DIR/master.log"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$DATA_DIR"

# ── 工具函数 ──────────────────────────────────────────────────────────
ts() { date '+%Y-%m-%d %H:%M:%S'; }

log_msg() {
    local msg="[$(ts)] $1"
    echo "$msg"
    echo "$msg" >> "$MASTER_LOG"
}

check_api() {
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo "================================================================"
        echo "  ERROR: OPENAI_API_KEY 未设置!"
        echo ""
        echo "  请先运行:"
        echo "    export OPENAI_API_KEY='your-key'"
        echo "    export OPENAI_BASE_URL='https://uni-api.cstcloud.cn/v1'"
        echo "================================================================"
        exit 1
    fi
    log_msg "API 配置: BASE_URL=${OPENAI_BASE_URL:-default}"
    log_msg "API 配置: MODEL=${OPENAI_MODEL:-default from config}"
}

save_pid() {
    echo "$1" > "$PID_FILE"
    log_msg "后台进程 PID: $1"
    log_msg "PID 已保存到: $PID_FILE"
}

check_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "[WARN] 已有后台任务运行中 (PID=$pid)。"
            echo "       如需强制重新运行，请先: kill $pid"
            exit 1
        else
            rm -f "$PID_FILE"
        fi
    fi
}

# ── 核心函数 ──────────────────────────────────────────────────────────

prepare_data() {
    log_msg "══════════════════════════════════════════════════════════"
    log_msg "Step 0: 准备论文数据"
    log_msg "══════════════════════════════════════════════════════════"

    python -m baseline.prepare_6papers \
        --input outputs/nature_comm_100_v6/classified.jsonl \
        --output "$PAPERS_FILE" \
        2>&1 | tee -a "$MASTER_LOG"

    log_msg "数据准备完成: $PAPERS_FILE"
}

do_phase1() {
    log_msg "══════════════════════════════════════════════════════════"
    log_msg "Phase 1: 小规模测试 (前2篇论文 × 11种方法)"
    log_msg "══════════════════════════════════════════════════════════"

    [ ! -f "$PAPERS_FILE" ] && prepare_data

    python -m baseline.run_6paper_experiment \
        --input "$PAPERS_FILE" \
        --max-papers 2 \
        --output "$OUTPUT_DIR/phase1_results.json" \
        >> "$OUTPUT_DIR/phase1_run.log" 2>&1

    log_msg "Phase 1 生成完成: $OUTPUT_DIR/phase1_results.json"
}

do_phase2() {
    log_msg "══════════════════════════════════════════════════════════"
    log_msg "Phase 2: 完整实验 (6篇论文 × 11种方法)"
    log_msg "══════════════════════════════════════════════════════════"

    [ ! -f "$PAPERS_FILE" ] && prepare_data

    python -m baseline.run_6paper_experiment \
        --input "$PAPERS_FILE" \
        --output "$OUTPUT_DIR/phase2_results.json" \
        >> "$OUTPUT_DIR/phase2_run.log" 2>&1

    log_msg "Phase 2 生成完成: $OUTPUT_DIR/phase2_results.json"
}

do_eval() {
    local PHASE="$1"
    local RESULTS_FILE="$OUTPUT_DIR/${PHASE}_results.json"

    if [ ! -f "$RESULTS_FILE" ]; then
        log_msg "ERROR: $RESULTS_FILE not found. Run $PHASE first."
        exit 1
    fi

    log_msg "══════════════════════════════════════════════════════════"
    log_msg "评估 $PHASE 结果 (ROUGE + LLM-as-Judge)"
    log_msg "══════════════════════════════════════════════════════════"

    python -m baseline.evaluate_batch \
        --input "$RESULTS_FILE" \
        --output "$OUTPUT_DIR/${PHASE}_eval.json" \
        >> "$OUTPUT_DIR/${PHASE}_eval.log" 2>&1

    log_msg "评估完成: $OUTPUT_DIR/${PHASE}_eval.json"
}

do_report() {
    log_msg "══════════════════════════════════════════════════════════"
    log_msg "生成对比报告"
    log_msg "══════════════════════════════════════════════════════════"

    local EVAL_FILE=""
    if [ -f "$OUTPUT_DIR/phase2_eval.json" ]; then
        EVAL_FILE="$OUTPUT_DIR/phase2_eval.json"
    elif [ -f "$OUTPUT_DIR/phase1_eval.json" ]; then
        EVAL_FILE="$OUTPUT_DIR/phase1_eval.json"
    else
        log_msg "ERROR: No evaluation results found. Run eval first."
        exit 1
    fi

    python -m baseline.generate_comparison_report \
        --eval-results "$EVAL_FILE" \
        --output "$OUTPUT_DIR/comparison_report.md" \
        --kg-results "outputs/nature_comm_100_v6/p5_kg_eval_results.json" \
        2>&1 | tee -a "$MASTER_LOG"

    log_msg "报告已生成: $OUTPUT_DIR/comparison_report.md"
}

do_all() {
    log_msg "══════════════════════════════════════════════════════════"
    log_msg "一键运行: prepare → phase2 → eval2 → report"
    log_msg "══════════════════════════════════════════════════════════"

    prepare_data
    do_phase2
    do_eval "phase2"
    do_report

    log_msg "══════════════════════════════════════════════════════════"
    log_msg "全部完成!"
    log_msg "══════════════════════════════════════════════════════════"
}

# ── 后台启动封装 ──────────────────────────────────────────────────────

run_in_background() {
    local CMD="$1"
    local LOG_NAME="$2"
    local LOG_FILE="$OUTPUT_DIR/${LOG_NAME}.log"

    check_api
    check_running

    # 清空本次日志
    : > "$LOG_FILE"

    log_msg "启动后台任务: $CMD"
    log_msg "日志文件: $LOG_FILE"

    # 使用 nohup 后台运行，将环境变量传递给子进程
    # 注意：只在变量非空时才 export，避免空字符串覆盖代码中的默认值
    nohup bash -c "
        export OPENAI_API_KEY='${OPENAI_API_KEY}'
        ${OPENAI_BASE_URL:+export OPENAI_BASE_URL='${OPENAI_BASE_URL}'}
        ${OPENAI_MODEL:+export OPENAI_MODEL='${OPENAI_MODEL}'}
        cd '$PROJECT_DIR'
        source '$0' _internal_$CMD 2>&1
    " >> "$LOG_FILE" 2>&1 &

    local BG_PID=$!
    save_pid "$BG_PID"

    echo ""
    echo "════════════════════════════════════════════════════"
    echo "  后台任务已启动"
    echo "  PID:  $BG_PID"
    echo "  日志: $LOG_FILE"
    echo ""
    echo "  查看实时日志:  tail -f $LOG_FILE"
    echo "  查看总进度:    bash $0 status"
    echo "  终止任务:      kill $BG_PID"
    echo "════════════════════════════════════════════════════"
}

show_status() {
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "  对比实验状态"
    echo "════════════════════════════════════════════════════"
    echo ""

    # 后台进程
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  [运行中] 后台进程 PID=$pid"
        else
            echo "  [已结束] 上次后台进程 PID=$pid (已退出)"
        fi
    else
        echo "  [空闲] 无后台任务"
    fi
    echo ""

    # 各阶段状态
    local stages=("papers_6_2025.json:prepare:数据准备"
                   "phase1_results.json:phase1:Phase1生成"
                   "phase1_eval.json:eval1:Phase1评估"
                   "phase2_results.json:phase2:Phase2生成"
                   "phase2_eval.json:eval2:Phase2评估"
                   "comparison_report.md:report:对比报告")

    for entry in "${stages[@]}"; do
        IFS=':' read -r file stage label <<< "$entry"
        if [ "$stage" = "prepare" ]; then
            filepath="$DATA_DIR/$file"
        else
            filepath="$OUTPUT_DIR/$file"
        fi

        if [ -f "$filepath" ]; then
            local size
            size=$(du -h "$filepath" | cut -f1)
            local mtime
            mtime=$(stat -c '%y' "$filepath" 2>/dev/null | cut -d'.' -f1)
            echo "  ✓ $label  →  $filepath ($size, $mtime)"
        else
            echo "  · $label  →  未完成"
        fi
    done
    echo ""

    # 日志文件
    echo "  日志文件:"
    for logf in "$MASTER_LOG" "$OUTPUT_DIR"/*_run.log "$OUTPUT_DIR"/*_eval.log; do
        if [ -f "$logf" ]; then
            local size
            size=$(du -h "$logf" | cut -f1)
            local last_line
            last_line=$(tail -1 "$logf" 2>/dev/null | head -c 80)
            echo "    $(basename "$logf") ($size)  最后: $last_line"
        fi
    done
    echo ""
}

show_logs() {
    local STAGE="${1:-}"

    if [ -z "$STAGE" ]; then
        # 默认显示最新的日志
        local latest=""
        local latest_time=0
        for logf in "$OUTPUT_DIR"/*_run.log "$OUTPUT_DIR"/*_eval.log "$MASTER_LOG"; do
            if [ -f "$logf" ]; then
                local mtime
                mtime=$(stat -c '%Y' "$logf" 2>/dev/null || echo 0)
                if [ "$mtime" -gt "$latest_time" ]; then
                    latest_time="$mtime"
                    latest="$logf"
                fi
            fi
        done
        if [ -n "$latest" ]; then
            echo "实时跟踪最新日志: $latest"
            echo "(Ctrl+C 退出)"
            echo ""
            tail -f "$latest"
        else
            echo "没有找到日志文件"
        fi
    else
        local logf="$OUTPUT_DIR/${STAGE}_run.log"
        [ ! -f "$logf" ] && logf="$OUTPUT_DIR/${STAGE}_eval.log"
        [ ! -f "$logf" ] && logf="$OUTPUT_DIR/${STAGE}.log"
        if [ -f "$logf" ]; then
            echo "实时跟踪: $logf"
            echo "(Ctrl+C 退出)"
            echo ""
            tail -f "$logf"
        else
            echo "日志文件不存在: $logf"
            echo "可用的日志: $(ls "$OUTPUT_DIR"/*.log 2>/dev/null | xargs -I{} basename {} || echo '无')"
        fi
    fi
}

# ── 主入口 ─────────────────────────────────────────────────────────────

COMMAND="${1:-help}"
FOREGROUND="${2:-}"

case "$COMMAND" in
    prepare)
        prepare_data
        ;;
    phase1)
        if [ "$FOREGROUND" = "--fg" ]; then
            check_api
            do_phase1 2>&1 | tee "$OUTPUT_DIR/phase1_run.log"
        else
            run_in_background "phase1" "phase1_run"
        fi
        ;;
    phase2)
        if [ "$FOREGROUND" = "--fg" ]; then
            check_api
            do_phase2 2>&1 | tee "$OUTPUT_DIR/phase2_run.log"
        else
            run_in_background "phase2" "phase2_run"
        fi
        ;;
    eval1)
        if [ "$FOREGROUND" = "--fg" ]; then
            check_api
            do_eval "phase1" 2>&1 | tee "$OUTPUT_DIR/phase1_eval.log"
        else
            run_in_background "eval1" "phase1_eval"
        fi
        ;;
    eval2)
        if [ "$FOREGROUND" = "--fg" ]; then
            check_api
            do_eval "phase2" 2>&1 | tee "$OUTPUT_DIR/phase2_eval.log"
        else
            run_in_background "eval2" "phase2_eval"
        fi
        ;;
    report)
        do_report
        ;;
    all)
        if [ "$FOREGROUND" = "--fg" ]; then
            check_api
            do_all 2>&1 | tee "$OUTPUT_DIR/all_run.log"
        else
            run_in_background "all" "all_run"
        fi
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "${2:-}"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            local_pid=$(cat "$PID_FILE")
            if kill -0 "$local_pid" 2>/dev/null; then
                kill "$local_pid"
                echo "已终止后台任务 PID=$local_pid"
            else
                echo "进程 $local_pid 已不存在"
            fi
            rm -f "$PID_FILE"
        else
            echo "没有正在运行的后台任务"
        fi
        ;;

    # 内部调用入口（由 nohup 子进程使用，不要直接调用）
    _internal_phase1) check_api; do_phase1 ;;
    _internal_phase2) check_api; do_phase2 ;;
    _internal_eval1)  check_api; do_eval "phase1" ;;
    _internal_eval2)  check_api; do_eval "phase2" ;;
    _internal_all)    check_api; do_all ;;

    help|*)
        cat << 'HELPEOF'
用法: bash run_comparison_experiment.sh <command> [--fg]

Commands:
  prepare  — 准备论文数据（前台，不需要 API key）
  phase1   — 小规模测试（后台，2篇 × 11方法，约20min）
  phase2   — 完整实验（后台，6篇 × 11方法，约60-90min）
  eval1    — 评估 phase1 结果（后台，ROUGE + LLM-as-Judge）
  eval2    — 评估 phase2 结果（后台，ROUGE + LLM-as-Judge）
  report   — 生成 Markdown 对比报告（前台）
  all      — 一键全部后台运行（prepare → phase2 → eval2 → report）

监控:
  status   — 查看各阶段完成状态和后台进程
  logs     — 查看最新日志（tail -f）
  logs X   — 查看指定阶段日志（X = phase1|phase2|eval1|eval2）
  stop     — 终止后台任务

选项:
  --fg     — 前台运行（调试用），如: bash run_comparison_experiment.sh phase1 --fg

环境变量（运行 phase/eval 前必须设置）:
  export OPENAI_API_KEY='your-key'
  export OPENAI_BASE_URL='https://uni-api.cstcloud.cn/v1'

示例完整流程:
  export OPENAI_API_KEY='sk-xxx'
  export OPENAI_BASE_URL='https://uni-api.cstcloud.cn/v1'

  bash run_comparison_experiment.sh prepare        # 准备数据
  bash run_comparison_experiment.sh phase1          # 后台：小规模测试
  bash run_comparison_experiment.sh status          # 查看进度
  bash run_comparison_experiment.sh logs phase1     # 实时日志
  # phase1 完成后:
  bash run_comparison_experiment.sh eval1           # 后台：评估
  bash run_comparison_experiment.sh report          # 生成报告
  # 确认无误后完整运行:
  bash run_comparison_experiment.sh all             # 后台：一键全部
HELPEOF
        ;;
esac

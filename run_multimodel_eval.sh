#!/bin/bash
# ============================================================================
# 多模型评测实验 v7
# 在筛选出多学科论文后，选取5篇作为测试集，其余构建GT，
# 然后用13个大模型分别生成假设进行评测，结果以雷达图展示。
#
# 用法:
#   # 设置 API Key
#   export OPENAI_API_KEY="your-key-here"
#
#   # 全流程运行
#   bash run_multimodel_eval.sh
#
#   # 后台运行
#   bash run_multimodel_eval.sh -bg
#
#   # 仅运行某个阶段
#   bash run_multimodel_eval.sh --stage eval    # 仅评测
#   bash run_multimodel_eval.sh --stage radar   # 仅画雷达图
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

OUTPUT_DIR="outputs/multimodel_eval_v7"
LOG_FILE="$OUTPUT_DIR/pipeline.log"
mkdir -p "$OUTPUT_DIR/stage_outputs" "$OUTPUT_DIR/radar_charts"

# ── 后台运行支持 ──
if [ "$1" = "-bg" ] || [ "$1" = "--background" ]; then
    echo "启动后台运行，日志: $LOG_FILE"
    echo "查看进度: tail -f $LOG_FILE"
    nohup bash "$0" --foreground > "$LOG_FILE" 2>&1 &
    echo $! > "$OUTPUT_DIR/pipeline.pid"
    echo "PID: $!"
    exit 0
fi

# ── 颜色输出 ──
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi
log_step() { echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"; echo -e "${GREEN}[$(date '+%H:%M:%S')] [STEP] $1${NC}"; echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}\n"; }
log_info() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] [INFO] $1${NC}"; }

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY 未设置"; exit 1
fi
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# ── 实验配置 ──
NUM_WORKERS=4
LANGUAGE_MODE="chinese"
TEST_COUNT=5
PAPER_COUNT=100
CROSSDISC_THRESHOLD=0.5

# 13个测试模型
MODELS=(
    "gpt-4o-mini"
    "gpt-4.1-mini"
    "gemini-2.0-flash"
    "claude-sonnet-4-20250514"
    "doubao-1-5-pro-32k-250115"
    "glm-4.5"
    "qwen2.5-72b-instruct"
    "qwen2.5-7b-instruct"
    "deepseek-v3"
    "o1"
    "o3-mini"
    "deepseek-r1"
    "qwen3-235b-a22b"
)

STAGE_FLAG="${1:-all}"

# ============================================================================
# Stage 0: 复用已有原始数据
# ============================================================================
JSONL_RAW="$OUTPUT_DIR/nature_comm_100_raw.jsonl"
JSONL_CLASSIFIED="$OUTPUT_DIR/classified.jsonl"

if [ "$STAGE_FLAG" = "all" ] || [ "$STAGE_FLAG" = "--foreground" ]; then

if [ ! -f "$JSONL_RAW" ]; then
    log_step "Stage 0: 复用 v5 原始数据"
    cp "outputs/nature_comm_100_v5/nature_comm_100_raw.jsonl" "$JSONL_RAW"
fi
TOTAL_RAW=$(wc -l < "$JSONL_RAW")
log_info "原始论文数: $TOTAL_RAW 篇"


# ============================================================================
# Stage 1: 学科分类 + 跨学科筛选
# ============================================================================
if [ ! -f "$JSONL_CLASSIFIED" ]; then
    log_step "Stage 1: 学科分类 + 跨学科筛选 (threshold=$CROSSDISC_THRESHOLD)"
    python -m crossdisc_extractor.pipeline classify \
        --input "$JSONL_RAW" \
        --output "$JSONL_CLASSIFIED" \
        --config configs/default.yaml \
        --crossdisc-threshold "$CROSSDISC_THRESHOLD"
else
    log_info "Stage 1: 已有分类结果，跳过"
fi
TOTAL_CROSS=$(wc -l < "$JSONL_CLASSIFIED")
log_info "跨学科论文: $TOTAL_CROSS / $TOTAL_RAW 篇"


# ============================================================================
# Stage 2: 知识抽取 (概念→关系→查询→假设)
# ============================================================================
EXTRACTION_JSONL="$OUTPUT_DIR/extraction_results.jsonl"
if [ ! -f "$EXTRACTION_JSONL" ]; then
    log_step "Stage 2: 三阶段知识抽取 (workers=$NUM_WORKERS)"
    python run.py batch \
        --input "$JSONL_CLASSIFIED" \
        --output "$EXTRACTION_JSONL" \
        --num-workers "$NUM_WORKERS" \
        --max-tokens-hyp 8192 \
        --resume \
        --language-mode "$LANGUAGE_MODE"
else
    log_info "Stage 2: 已有抽取结果，跳过"
fi

# 划分GT和测试集
log_step "Stage 2b: 划分数据集 (GT + 测试集)"
OUTPUT_DIR="$OUTPUT_DIR" TEST_COUNT=$TEST_COUNT python3 << 'SPLIT_EOF'
import json, os

output_dir = os.environ.get("OUTPUT_DIR")
test_count = int(os.environ.get("TEST_COUNT", "5"))

results = []
with open(os.path.join(output_dir, "extraction_results.jsonl"), encoding="utf-8") as f:
    for line in f:
        if line.strip():
            results.append(json.loads(line))

ok_results = [r for r in results if r.get("ok")]
print(f"抽取成功: {len(ok_results)}/{len(results)}")

with open(os.path.join(output_dir, "extraction_results.json"), "w", encoding="utf-8") as f:
    json.dump(ok_results, f, ensure_ascii=False, indent=2)

gt_items = ok_results[:-test_count]
test_items = ok_results[-test_count:]

for name, items in [("gt_extraction.json", gt_items), ("test_extraction.json", test_items)]:
    with open(os.path.join(output_dir, name), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

print(f"GT 集: {len(gt_items)} 篇, 测试集: {len(test_items)} 篇")
for t in test_items:
    print(f"  测试: {t.get('title', '')[:60]}")
SPLIT_EOF


# ============================================================================
# Stage 3: 构建 Benchmark GT 数据集
# ============================================================================
if [ ! -f "$OUTPUT_DIR/benchmark_dataset.json" ]; then
    log_step "Stage 3: 构建 Benchmark GT 数据集"
    python -m crossdisc_extractor.benchmark.build_dataset \
        --input "$OUTPUT_DIR/gt_extraction.json" \
        --output "$OUTPUT_DIR/benchmark_dataset.json" \
        --gt-mode evidence \
        --taxonomy data/msc_converted.json
else
    log_info "Stage 3: 已有GT数据集，跳过"
fi

fi  # end of STAGE_FLAG = all


# ============================================================================
# Stage 4: 多模型假设生成
# ============================================================================
if [ "$STAGE_FLAG" = "all" ] || [ "$STAGE_FLAG" = "--foreground" ] || [ "$STAGE_FLAG" = "--stage" -a "$2" = "gen" ]; then

log_step "Stage 4: 多模型假设生成 (${#MODELS[@]} 个模型 × $TEST_COUNT 篇)"

for MODEL in "${MODELS[@]}"; do
    MODEL_RESULT="$OUTPUT_DIR/model_results/${MODEL}.json"
    mkdir -p "$OUTPUT_DIR/model_results"

    if [ -f "$MODEL_RESULT" ]; then
        log_info "  $MODEL: 已有结果，跳过"
        continue
    fi

    log_info "  正在测试模型: $MODEL"

    OUTPUT_DIR="$OUTPUT_DIR" MODEL_NAME="$MODEL" python3 << 'MODEL_GEN_EOF'
import json, hashlib, os, time, traceback
from datetime import datetime

output_dir = os.environ["OUTPUT_DIR"]
model_name = os.environ["MODEL_NAME"]

with open(os.path.join(output_dir, "test_extraction.json"), encoding="utf-8") as f:
    test_items = json.load(f)

from crossdisc_extractor.prompts.hypothesis_prompt_levels import PromptLevel, build_messages
from crossdisc_extractor.utils.llm import MODEL_NAME as DEFAULT_MODEL

# Temporarily override model
import crossdisc_extractor.utils.llm as llm_module
original_model = llm_module.MODEL_NAME
llm_module.MODEL_NAME = model_name
from crossdisc_extractor.utils.llm import chat_completion_with_retry

all_results = []

for paper_idx, item in enumerate(test_items):
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    abstract = item.get("abstract", "")
    primary = meta.get("primary", item.get("primary", ""))
    secondary_list = meta.get("secondary_list", item.get("secondary_list", []))
    paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]

    queries = parsed.get("查询", {})
    l1_query = queries.get("一级", "")
    l2_queries = queries.get("二级", [])
    l3_queries = queries.get("三级", [])
    concepts = parsed.get("概念", {})
    relations = parsed.get("跨学科关系", [])

    print(f"  [{paper_idx+1}/{len(test_items)}] {model_name} | {title[:50]}...")

    # Use P4 level (most information without requiring structured paths)
    # This tests the model's ability to generate hypotheses given full context
    for level_name in ["P1", "P2", "P3", "P4"]:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"    [{ts}] {level_name}...", end="", flush=True)
        t0 = time.time()
        try:
            level = PromptLevel(level_name)
            messages = build_messages(
                level, l1_query=l1_query,
                l2_queries=l2_queries if level.value >= "P2" else None,
                l3_queries=l3_queries if level.value >= "P3" else None,
                abstract=abstract if level.value >= "P2" else "",
                primary=primary, secondary_list=secondary_list,
                concepts=concepts if level.value >= "P3" else None,
                relations=relations if level.value >= "P4" else None,
            )
            resp = chat_completion_with_retry(messages, temperature=0.7)
            hyp_text = resp.strip()
            elapsed = time.time() - t0

            all_results.append({
                "paper_id": paper_id,
                "title": title,
                "model": model_name,
                "method_name": level_name,
                "free_text_hypotheses": [hyp_text],
                "structured_paths": {},
                "elapsed_seconds": round(elapsed, 2),
                "error": None,
            })
            print(f" ok ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - t0
            print(f" FAIL ({elapsed:.1f}s): {e}")
            all_results.append({
                "paper_id": paper_id,
                "title": title,
                "model": model_name,
                "method_name": level_name,
                "free_text_hypotheses": [f"[ERROR] {e}"],
                "structured_paths": {},
                "elapsed_seconds": round(elapsed, 2),
                "error": str(e),
            })

# Restore model
llm_module.MODEL_NAME = original_model

out_path = os.path.join(output_dir, "model_results", f"{model_name}.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f"  {model_name}: {len(all_results)} 条结果已保存")
MODEL_GEN_EOF

done

fi


# ============================================================================
# Stage 5: 多模型 16 指标评测
# ============================================================================
if [ "$STAGE_FLAG" = "all" ] || [ "$STAGE_FLAG" = "--foreground" ] || [ "$STAGE_FLAG" = "--stage" -a "$2" = "eval" ]; then

log_step "Stage 5: 多模型 16 指标评测 (KG-based + LLM-as-Judge)"

python "$PROJ_DIR/run_multimodel_eval_16metrics.py" \
    --model-results-dir "$OUTPUT_DIR/model_results" \
    --benchmark "$OUTPUT_DIR/benchmark_dataset.json" \
    --test-data "$OUTPUT_DIR/test_extraction.json" \
    --output-dir "$OUTPUT_DIR" \
    --taxonomy data/msc_converted.json

fi


# ============================================================================
# Stage 6: 生成多模型雷达图
# ============================================================================
if [ "$STAGE_FLAG" = "all" ] || [ "$STAGE_FLAG" = "--foreground" ] || [ "$STAGE_FLAG" = "--stage" -a "$2" = "radar" ]; then

log_step "Stage 6: 生成多模型雷达图"

python "$PROJ_DIR/generate_multimodel_radar.py" \
    --input "$OUTPUT_DIR/multimodel_16metrics_summary.json" \
    --output-dir "$OUTPUT_DIR/radar_charts"

fi


log_info "全流程完成！"
echo -e "  输出目录: ${GREEN}$OUTPUT_DIR/${NC}"
echo -e "  雷达图:   ${GREEN}$OUTPUT_DIR/radar_charts/${NC}"
rm -f "$OUTPUT_DIR/pipeline.pid"

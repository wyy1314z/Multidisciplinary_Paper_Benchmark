#!/bin/bash
# ============================================================================
# Nature Communications 100篇 全流程测试 v6
# 基于 v5(100篇) 数据源，使用优化后的分类器：
#   - 去除 prompt 强制多选引导
#   - 新增跨学科置信度评分 + 阈值过滤
# ============================================================================
set -e

PROJ_DIR="/ssd/wangyuyang/git/benchmark"
cd "$PROJ_DIR"

# ── 输出目录 ──────────────────────────────────────────────────────────
OUTPUT_DIR="outputs/nature_comm_100_v6"
LOG_FILE="$OUTPUT_DIR/pipeline.log"
mkdir -p "$OUTPUT_DIR/stage_outputs"

# ── 后台运行支持 ──────────────────────────────────────────────────────
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

# ── 颜色输出 ──────────────────────────────────────────────────────────
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

# HuggingFace 镜像（国内服务器无法直连 huggingface.co）
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
log_info "HF_ENDPOINT=$HF_ENDPOINT"

NUM_WORKERS=4
LANGUAGE_MODE="chinese"
TEST_COUNT=5         # 100篇规模下，留5篇做测试集
PAPER_COUNT=100      # 目标论文数
CROSSDISC_THRESHOLD=0.5  # 跨学科置信度阈值

JSONL_RAW="$OUTPUT_DIR/nature_comm_100_raw.jsonl"
JSONL_CLASSIFIED="$OUTPUT_DIR/classified.jsonl"


# ============================================================================
# Stage 0: 复用 v5 的原始数据
# ============================================================================
if [ ! -f "$JSONL_RAW" ]; then
    log_step "Stage 0: 复用 v5 原始数据 (100 篇)"
    cp "outputs/nature_comm_100_v5/nature_comm_100_raw.jsonl" "$JSONL_RAW"
fi

TOTAL_RAW=$(wc -l < "$JSONL_RAW")
log_info "原始论文数: $TOTAL_RAW 篇"


# ============================================================================
# Stage 1: 学科分类 + 跨学科置信度筛选 (新版分类器)
# ============================================================================
log_step "Stage 1: 学科分类 + 跨学科置信度筛选 ($TOTAL_RAW 篇, threshold=$CROSSDISC_THRESHOLD)"

python -m crossdisc_extractor.pipeline classify \
    --input "$JSONL_RAW" \
    --output "$JSONL_CLASSIFIED" \
    --config configs/default.yaml \
    --crossdisc-threshold "$CROSSDISC_THRESHOLD"

TOTAL_CROSS=$(wc -l < "$JSONL_CLASSIFIED")
log_info "跨学科论文: $TOTAL_CROSS / $TOTAL_RAW 篇 (置信度阈值=$CROSSDISC_THRESHOLD)"

# 保存 Stage 1 样例
python3 -c "
import json
with open('$JSONL_CLASSIFIED') as f:
    lines = [json.loads(l) for l in f if l.strip()]
samples = lines[:3]
with open('$OUTPUT_DIR/stage_outputs/stage1_classification_samples.json', 'w', encoding='utf-8') as f:
    json.dump(samples, f, ensure_ascii=False, indent=2)
print(f'Stage 1 样例已保存 ({len(lines)} 篇跨学科论文)')
"


# ============================================================================
# Stage 2: 三阶段知识抽取
# ============================================================================
log_step "Stage 2: 三阶段知识抽取 (概念→关系→查询→假设, workers=$NUM_WORKERS)"

python run.py batch \
    --input "$JSONL_CLASSIFIED" \
    --output "$OUTPUT_DIR/extraction_results.jsonl" \
    --num-workers "$NUM_WORKERS" \
    --max-tokens-hyp 8192 \
    --resume \
    --language-mode "$LANGUAGE_MODE"

# 保存 Stage 2 样例 + 划分数据集
TEST_COUNT=$TEST_COUNT python3 << 'STAGE2_EOF'
import json, os

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_comm_100_v6")
extraction_file = os.path.join(output_dir, "extraction_results.jsonl")
test_count = int(os.environ.get("TEST_COUNT", "5"))

results = []
with open(extraction_file, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            results.append(json.loads(line))

ok_results = [r for r in results if r.get("ok")]
print(f"抽取完成: {len(ok_results)}/{len(results)} 成功")

# 保存完整 JSON
with open(os.path.join(output_dir, "extraction_results.json"), "w", encoding="utf-8") as f:
    json.dump(ok_results, f, ensure_ascii=False, indent=2)

# 保存 Stage 2 各子阶段样例
stage_dir = os.path.join(output_dir, "stage_outputs")
samples = ok_results[:3]

# Stage 2a: 概念抽取样例
concepts_samples = []
for s in samples:
    parsed = s.get("parsed", {})
    concepts_samples.append({
        "title": parsed.get("meta", {}).get("title", s.get("title", "")),
        "primary": parsed.get("meta", {}).get("primary", ""),
        "secondary_list": parsed.get("meta", {}).get("secondary_list", []),
        "概念_主学科": parsed.get("概念", {}).get("主学科", []),
        "概念_辅学科": parsed.get("概念", {}).get("辅学科", {}),
    })
with open(os.path.join(stage_dir, "stage2a_concepts_samples.json"), "w", encoding="utf-8") as f:
    json.dump(concepts_samples, f, ensure_ascii=False, indent=2)

# Stage 2b: 跨学科关系样例
relations_samples = []
for s in samples:
    parsed = s.get("parsed", {})
    relations_samples.append({
        "title": parsed.get("meta", {}).get("title", s.get("title", "")),
        "跨学科关系": parsed.get("跨学科关系", []),
        "按辅助学科分类": parsed.get("按辅助学科分类", {}),
    })
with open(os.path.join(stage_dir, "stage2b_relations_samples.json"), "w", encoding="utf-8") as f:
    json.dump(relations_samples, f, ensure_ascii=False, indent=2)

# Stage 2c: 查询生成样例
query_samples = []
for s in samples:
    parsed = s.get("parsed", {})
    query_samples.append({
        "title": parsed.get("meta", {}).get("title", s.get("title", "")),
        "查询": parsed.get("查询", {}),
    })
with open(os.path.join(stage_dir, "stage2c_query_samples.json"), "w", encoding="utf-8") as f:
    json.dump(query_samples, f, ensure_ascii=False, indent=2)

# Stage 2d: 假设生成样例
hyp_samples = []
for s in samples:
    parsed = s.get("parsed", {})
    hyp_data = parsed.get("假设", {})
    hyp_samples.append({
        "title": parsed.get("meta", {}).get("title", s.get("title", "")),
        "假设_一级": hyp_data.get("一级", []),
        "假设_一级总结": hyp_data.get("一级总结", []),
        "假设_二级": hyp_data.get("二级", []),
        "假设_二级总结": hyp_data.get("二级总结", []),
        "假设_三级": hyp_data.get("三级", []),
        "假设_三级总结": hyp_data.get("三级总结", []),
    })
with open(os.path.join(stage_dir, "stage2d_hypothesis_samples.json"), "w", encoding="utf-8") as f:
    json.dump(hyp_samples, f, ensure_ascii=False, indent=2)

# Stage 2e: 图指标样例
graph_samples = []
for s in samples:
    parsed = s.get("parsed", {})
    graph_samples.append({
        "title": parsed.get("meta", {}).get("title", s.get("title", "")),
        "graph": parsed.get("graph", {}),
        "metrics": parsed.get("metrics", {}),
    })
with open(os.path.join(stage_dir, "stage2e_graph_metrics_samples.json"), "w", encoding="utf-8") as f:
    json.dump(graph_samples, f, ensure_ascii=False, indent=2)

print("Stage 2 各子阶段样例已保存")

# 划分数据集
gt_items = ok_results[:-test_count]
test_items = ok_results[-test_count:]

for name, items in [("gt_extraction.json", gt_items),
                     ("test_extraction.json", test_items)]:
    with open(os.path.join(output_dir, name), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

print(f"GT 集: {len(gt_items)} 篇, 测试集: {len(test_items)} 篇")
for t in test_items:
    print(f"  测试: {t.get('title', '')[:60]}")
STAGE2_EOF


# ============================================================================
# Stage 3: 构建 Benchmark GT 数据集
# ============================================================================
log_step "Stage 3: 构建 Benchmark GT 数据集 (evidence-grounded)"

python -m crossdisc_extractor.benchmark.build_dataset \
    --input "$OUTPUT_DIR/gt_extraction.json" \
    --output "$OUTPUT_DIR/benchmark_dataset.json" \
    --gt-mode evidence \
    --taxonomy data/msc_converted.json

# 保存 Stage 3 样例
python3 -c "
import json
with open('$OUTPUT_DIR/benchmark_dataset.json') as f:
    data = json.load(f)
samples = data[:3]
with open('$OUTPUT_DIR/stage_outputs/stage3_gt_benchmark_samples.json', 'w', encoding='utf-8') as f:
    json.dump(samples, f, ensure_ascii=False, indent=2)
print(f'Stage 3 样例已保存 (共 {len(data)} 条 GT)')
"


# ============================================================================
# Stage 4: P1-P5 五级 Prompt 假设生成
# ============================================================================
log_step "Stage 4: P1-P5 五级 Prompt 假设生成 (测试集 $TEST_COUNT 篇 × 5 级)"

OUTPUT_DIR="$OUTPUT_DIR" TEST_COUNT=$TEST_COUNT python3 << 'P1P5_EOF'
import json, hashlib, os, time, traceback
from datetime import datetime

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_comm_100_v6")
stage_dir = os.path.join(output_dir, "stage_outputs")

with open(os.path.join(output_dir, "test_extraction.json"), encoding="utf-8") as f:
    test_items = json.load(f)

from crossdisc_extractor.prompts.hypothesis_prompt_levels import PromptLevel, build_messages
from crossdisc_extractor.utils.llm import chat_completion_with_retry

all_batch_results = []
all_eval_inputs = []
p1p5_stage_samples = {}

for paper_idx, item in enumerate(test_items):
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    abstract = item.get("abstract", "")
    primary = meta.get("primary", item.get("primary", ""))
    secondary_list = meta.get("secondary_list", item.get("secondary_list", []))
    paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]

    print(f"\n{'='*70}")
    print(f"[{paper_idx+1}/{len(test_items)}] {title[:60]}...")

    queries = parsed.get("查询", {})
    l1_query = queries.get("一级", "")
    l2_queries = queries.get("二级", [])
    l3_queries = queries.get("三级", [])
    concepts = parsed.get("概念", {})
    relations = parsed.get("跨学科关系", [])

    paper_results = []

    for level_name in ["P1", "P2", "P3", "P4", "P5"]:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {level_name}...", end="", flush=True)
        t0 = time.time()

        try:
            if level_name == "P5":
                hyp_data = parsed.get("假设", {})
                hyp_lines = []
                structured_paths = {}
                for lk, ck, sk in [("L1","一级","一级总结"),("L2","二级","二级总结"),("L3","三级","三级总结")]:
                    paths = hyp_data.get(ck, [])
                    sums = hyp_data.get(sk, [])
                    lp = []
                    for i, path in enumerate(paths):
                        if isinstance(path, list):
                            steps = [s if isinstance(s, dict) else {} for s in path]
                            lp.append({"steps": steps, "summary": sums[i] if i < len(sums) else ""})
                            for step in steps:
                                h = step.get("head", ""); r = step.get("relation", ""); tail = step.get("tail", "")
                                hyp_lines.append(f"[{lk}] {h} --[{r}]--> {tail}")
                    if lp: structured_paths[lk] = lp
                hyp_text = "\n".join(hyp_lines) if hyp_lines else "(empty)"
                elapsed = time.time() - t0
                all_sums = []
                for sk2 in ["一级总结","二级总结","三级总结"]:
                    all_sums.extend(hyp_data.get(sk2, []))
                eval_entry = {"paper_id": paper_id, "method_name": "P5",
                              "free_text_hypotheses": [s for s in all_sums if s],
                              "structured_paths": structured_paths, "raw_responses": [], "elapsed_seconds": elapsed}
            else:
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
                eval_entry = {"paper_id": paper_id, "method_name": level_name,
                              "free_text_hypotheses": [hyp_text], "structured_paths": {},
                              "raw_responses": [resp], "elapsed_seconds": elapsed}

            result = {"method": level_name, "hypotheses_text": hyp_text, "elapsed": round(elapsed, 1)}
            paper_results.append(result)
            all_eval_inputs.append(eval_entry)

            if level_name not in p1p5_stage_samples:
                p1p5_stage_samples[level_name] = []
            p1p5_stage_samples[level_name].append({
                "title": title, "primary": primary,
                "hypothesis_text": hyp_text[:2000],
                "elapsed": round(elapsed, 1),
            })
            print(f" done ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - t0
            print(f" FAIL ({elapsed:.1f}s): {e}")
            traceback.print_exc()
            paper_results.append({"method": level_name, "hypotheses_text": f"[ERROR] {e}", "elapsed": round(elapsed, 1)})
            all_eval_inputs.append({"paper_id": paper_id, "method_name": level_name,
                                    "free_text_hypotheses": [f"[ERROR] {e}"], "structured_paths": {},
                                    "raw_responses": [], "elapsed_seconds": elapsed})

    all_batch_results.append({
        "tag": f"test_{paper_idx}", "paper": {"paper_id": paper_id, "title": title,
        "abstract": abstract[:200]+"...", "primary_discipline": primary, "secondary_disciplines": secondary_list},
        "results": paper_results,
    })

for name, data in [("p1p5_batch_results.json", all_batch_results), ("p1p5_eval_input.json", all_eval_inputs)]:
    with open(os.path.join(output_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

with open(os.path.join(stage_dir, "stage4_p1p5_samples.json"), "w", encoding="utf-8") as f:
    json.dump(p1p5_stage_samples, f, ensure_ascii=False, indent=2)

papers_dict = {}
for item in test_items:
    parsed = item.get("parsed", {})
    meta = parsed.get("meta", {})
    title = meta.get("title", item.get("title", ""))
    pid = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
    papers_dict[pid] = {"paper_id": pid, "title": title, "abstract": item.get("abstract", ""),
                        "primary_discipline": meta.get("primary", ""), "secondary_disciplines": meta.get("secondary_list", [])}
with open(os.path.join(output_dir, "test_papers_map.json"), "w", encoding="utf-8") as f:
    json.dump(papers_dict, f, ensure_ascii=False, indent=2)

print("\nP1-P5 生成完成, 样例已保存")
P1P5_EOF


# ============================================================================
# Stage 5: 多维度评测
# ============================================================================
log_step "Stage 5: 多维度评测 (LLM-as-Judge + 文本相似度 + 结构化指标)"

OUTPUT_DIR="$OUTPUT_DIR" python3 << 'EVAL_EOF'
import json, os

output_dir = os.environ.get("OUTPUT_DIR", "outputs/nature_comm_100_v6")
stage_dir = os.path.join(output_dir, "stage_outputs")

with open(os.path.join(output_dir, "p1p5_eval_input.json"), encoding="utf-8") as f:
    eval_inputs = json.load(f)
with open(os.path.join(output_dir, "test_papers_map.json"), encoding="utf-8") as f:
    papers_map = json.load(f)

from baseline.evaluate_all import evaluate_single_output, aggregate_by_method, print_comparison_table

all_eval_results = []
for i, output in enumerate(eval_inputs):
    pid = output.get("paper_id", "")
    method = output.get("method_name", "")
    paper = papers_map.get(pid, {})
    if not paper: continue
    print(f"  [{i+1}/{len(eval_inputs)}] {method} - {paper['title'][:50]}...", flush=True)
    result = evaluate_single_output(output, paper, use_llm_judge=True)
    all_eval_results.append(result)

with open(os.path.join(output_dir, "p1p5_eval_results.json"), "w", encoding="utf-8") as f:
    json.dump(all_eval_results, f, ensure_ascii=False, indent=2)

aggregated = aggregate_by_method(all_eval_results)
print_comparison_table(aggregated)

with open(os.path.join(output_dir, "p1p5_comparison_summary.json"), "w", encoding="utf-8") as f:
    json.dump(aggregated, f, ensure_ascii=False, indent=2)

with open(os.path.join(stage_dir, "stage5_eval_samples.json"), "w", encoding="utf-8") as f:
    json.dump({"detailed_results": all_eval_results[:5], "aggregated_summary": aggregated}, f, ensure_ascii=False, indent=2)

print("评测完成, 样例已保存")
EVAL_EOF


# ============================================================================
# Stage 6: P5 KG-based 深度评测
# ============================================================================
log_step "Stage 6: KG-based 结构化评测"

python -m crossdisc_extractor.benchmark.evaluate_benchmark \
    --benchmark "$OUTPUT_DIR/benchmark_dataset.json" \
    --predictions "$OUTPUT_DIR/test_extraction.json" \
    --output "$OUTPUT_DIR/p5_kg_eval_results.json" \
    --taxonomy data/msc_converted.json

python3 -c "
import json
with open('$OUTPUT_DIR/p5_kg_eval_results.json') as f:
    data = json.load(f)
with open('$OUTPUT_DIR/stage_outputs/stage6_kg_eval_samples.json', 'w', encoding='utf-8') as f:
    json.dump(data[:3] if data else [], f, ensure_ascii=False, indent=2)
print(f'Stage 6 样例已保存 ({len(data)} 条)')
"


# ============================================================================
# Stage 7: 生成汇报文档
# ============================================================================
log_step "Stage 7: 生成汇报文档 (Word)"

REPORT_OUTPUT_DIR="$OUTPUT_DIR" python3 /ssd/wangyuyang/git/benchmark/generate_nature_comm_report.py

log_info "全套流程完成！"
echo -e "  输出目录: ${GREEN}$OUTPUT_DIR/${NC}"
echo -e "  汇报文档: ${GREEN}$OUTPUT_DIR/全流程汇报文档.docx${NC}"

rm -f "$OUTPUT_DIR/pipeline.pid"

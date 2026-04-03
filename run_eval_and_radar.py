"""
独立评测 + 雷达图脚本
直接从 model_results/ 读取13个模型的生成结果，进行评测并画雷达图。

用法:
    cd /ssd/wangyuyang/git/benchmark
    python3 run_eval_and_radar.py
"""
import json, os, glob, hashlib, sys, traceback
import numpy as np
from collections import defaultdict
from pathlib import Path

PROJ_DIR = "/ssd/wangyuyang/git/benchmark"
OUTPUT_DIR = os.path.join(PROJ_DIR, "outputs/multimodel_eval_v7")
MODEL_DIR = os.path.join(OUTPUT_DIR, "model_results")
RADAR_DIR = os.path.join(OUTPUT_DIR, "radar_charts")
os.makedirs(RADAR_DIR, exist_ok=True)

# ============================================================================
# Step 1: Build test_papers_map.json
# ============================================================================
def build_papers_map():
    """Build papers map from test_extraction.json."""
    test_path = os.path.join(OUTPUT_DIR, "test_extraction.json")
    with open(test_path, encoding="utf-8") as f:
        test_items = json.load(f)

    papers_map = {}
    for item in test_items:
        parsed = item.get("parsed", {})
        meta = parsed.get("meta", {})
        title = meta.get("title", item.get("title", ""))
        pid = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        papers_map[pid] = {
            "paper_id": pid,
            "title": title,
            "abstract": item.get("abstract", ""),
            "primary_discipline": meta.get("primary", item.get("primary", "")),
            "secondary_disciplines": meta.get("secondary_list", item.get("secondary_list", [])),
        }

    out = os.path.join(OUTPUT_DIR, "test_papers_map.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(papers_map, f, ensure_ascii=False, indent=2)
    print(f"[Step 1] test_papers_map.json 已生成 ({len(papers_map)} 篇)")
    return papers_map


# ============================================================================
# Step 2: Evaluate all model results
# ============================================================================
def evaluate_all_models(papers_map):
    """Evaluate all model results using baseline.evaluate_all."""
    sys.path.insert(0, PROJ_DIR)
    from baseline.evaluate_all import evaluate_single_output

    all_results = []
    model_files = sorted(glob.glob(os.path.join(MODEL_DIR, "*.json")))

    for mf in model_files:
        model_name = Path(mf).stem
        with open(mf, encoding="utf-8") as f:
            outputs = json.load(f)

        print(f"\n[Step 2] 评测: {model_name} ({len(outputs)} 条)")

        for i, output in enumerate(outputs):
            pid = output.get("paper_id", "")
            method = output.get("method_name", "")
            paper = papers_map.get(pid)

            if not paper:
                continue
            if output.get("error"):
                continue
            # Skip entries with error text
            hyps = output.get("free_text_hypotheses", [])
            if hyps and isinstance(hyps[0], str) and hyps[0].startswith("[ERROR]"):
                continue

            print(f"  [{i+1}/{len(outputs)}] {model_name}/{method} ...", end="", flush=True)
            try:
                result = evaluate_single_output(output, paper, use_llm_judge=True)
                result["model"] = model_name
                result["method"] = method
                result["paper_id"] = pid
                all_results.append(result)
                print(" ok")
            except Exception as e:
                print(f" FAIL: {e}")
                traceback.print_exc()

    out = os.path.join(OUTPUT_DIR, "multimodel_eval_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n[Step 2] 评测完成: {len(all_results)} 条结果")
    return all_results


# ============================================================================
# Step 3: Aggregate results
# ============================================================================
def aggregate_results(all_results):
    """Aggregate evaluation results by model and by model+method."""
    # By model (overall)
    model_agg = defaultdict(lambda: defaultdict(list))
    # By model + method
    model_method_agg = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for r in all_results:
        model = r.get("model", "")
        method = r.get("method", "")
        for k, v in r.items():
            if isinstance(v, (int, float)) and v is not None:
                model_agg[model][k].append(v)
                model_method_agg[model][method][k].append(v)

    # Compute means
    summary = {}
    for model, metrics in model_agg.items():
        summary[model] = {k: round(float(np.mean(v)), 4) for k, v in metrics.items()}

    summary_by_method = {}
    for model, methods in model_method_agg.items():
        summary_by_method[model] = {}
        for method, metrics in methods.items():
            summary_by_method[model][method] = {
                k: round(float(np.mean(v)), 4) for k, v in metrics.items()
            }

    # Save
    with open(os.path.join(OUTPUT_DIR, "multimodel_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUTPUT_DIR, "multimodel_summary_by_method.json"), "w", encoding="utf-8") as f:
        json.dump(summary_by_method, f, ensure_ascii=False, indent=2)

    # Print table
    print("\n" + "=" * 100)
    print(f"  {'Model':<30s} {'BERTScore':>10s} {'Novelty':>10s} {'Specif.':>10s} "
          f"{'Feasib.':>10s} {'Relev.':>10s} {'CrossDisc':>10s}")
    print("  " + "-" * 90)
    for model in sorted(summary.keys()):
        m = summary[model]
        print(f"  {model:<30s} "
              f"{m.get('text_bertscore_f1', 0):>10.4f} "
              f"{m.get('judge_novelty', 0):>10.2f} "
              f"{m.get('judge_specificity', 0):>10.2f} "
              f"{m.get('judge_feasibility', 0):>10.2f} "
              f"{m.get('judge_relevance', 0):>10.2f} "
              f"{m.get('judge_cross_disciplinary', 0):>10.2f}")
    print("=" * 100)

    return summary, summary_by_method


# ============================================================================
# Step 4: Generate radar charts
# ============================================================================
def generate_radar_charts(summary, summary_by_method):
    """Generate all radar charts."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    for fname in ["SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC"]:
        if any(fname.lower() in f.name.lower() for f in fm.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [fname]
            break
    plt.rcParams["axes.unicode_minus"] = False

    # ── Model display config ──
    MODEL_GROUPS = {
        "Group A: \u95ed\u6e90\u901a\u7528": {
            "models": ["gpt-4o-mini", "gpt-4.1-mini", "gemini-2.0-flash",
                        "claude-sonnet-4-20250514", "doubao-1-5-pro-32k-250115", "glm-4.5"],
            "colors": ["#E74C3C", "#C0392B", "#E67E22", "#F39C12", "#D35400", "#8E44AD"],
            "linestyles": ["-", "-", "-", "-", "-", "-"],
        },
        "Group B: \u5f00\u6e90\u901a\u7528": {
            "models": ["qwen2.5-72b-instruct", "qwen2.5-7b-instruct", "deepseek-v3"],
            "colors": ["#2ECC71", "#27AE60", "#1ABC9C"],
            "linestyles": ["--", "--", "--"],
        },
        "Group C: \u63a8\u7406\u589e\u5f3a": {
            "models": ["o1", "o3-mini", "deepseek-r1", "qwen3-235b-a22b"],
            "colors": ["#3498DB", "#2980B9", "#1F618D", "#5DADE2"],
            "linestyles": ["-.", "-.", "-.", "-."],
        },
    }

    SHORT = {
        "gpt-4o-mini": "GPT-4o-mini", "gpt-4.1-mini": "GPT-4.1-mini",
        "gemini-2.0-flash": "Gemini-2.0", "claude-sonnet-4-20250514": "Claude-S4",
        "doubao-1-5-pro-32k-250115": "Doubao-1.5", "glm-4.5": "GLM-4.5",
        "qwen2.5-72b-instruct": "Qwen2.5-72B", "qwen2.5-7b-instruct": "Qwen2.5-7B",
        "deepseek-v3": "DS-V3", "o1": "O1", "o3-mini": "O3-mini",
        "deepseek-r1": "DS-R1", "qwen3-235b-a22b": "Qwen3-235B",
    }

    # Build style map
    style_map = {}
    for gname, g in MODEL_GROUPS.items():
        for i, m in enumerate(g["models"]):
            style_map[m] = {
                "color": g["colors"][i], "ls": g["linestyles"][i],
                "short": SHORT.get(m, m), "group": gname,
            }

    # ── Metrics definitions ──
    # Chart 1: LLM Judge metrics (available for P1-P4)
    JUDGE_METRICS = ["judge_novelty", "judge_specificity", "judge_feasibility",
                     "judge_relevance", "judge_cross_disciplinary"]
    JUDGE_LABELS = ["Novelty", "Specificity", "Feasibility", "Relevance", "Cross-Disc"]

    # Chart 2: Full metrics including BERTScore
    FULL_METRICS = ["text_bertscore_f1", "judge_novelty", "judge_specificity",
                    "judge_feasibility", "judge_relevance", "judge_cross_disciplinary"]
    FULL_LABELS = ["BERTScore", "Novelty", "Specificity", "Feasibility", "Relevance", "Cross-Disc"]

    def normalize(val, key):
        if key.startswith("judge_"):
            return min(float(val), 10.0)
        if key in ("text_bertscore_f1",):
            return min(float(val) * 10, 10.0)
        return min(float(val), 10.0)

    def draw_radar(ax, labels, model_vals, title_text):
        N = len(labels)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=10, fontweight="bold")
        ax.set_ylim(0, 10)
        ax.set_yticks([2, 4, 6, 8, 10])
        ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=7, alpha=0.5)
        ax.spines["polar"].set_alpha(0.2)
        ax.grid(alpha=0.3)

        for model_id, vals in model_vals.items():
            if model_id not in style_map:
                continue
            s = style_map[model_id]
            v = vals + vals[:1]
            ax.plot(angles, v, color=s["color"], linestyle=s["ls"],
                    linewidth=2.0, label=s["short"], alpha=0.85)
            ax.fill(angles, v, color=s["color"], alpha=0.05)
        ax.set_title(title_text, fontsize=14, fontweight="bold", pad=20)

    # ── Chart A: Overall (all P levels averaged) ──
    print("\n[Step 4] Generating radar charts...")

    fig, ax = plt.subplots(figsize=(13, 11), subplot_kw=dict(projection="polar"))
    model_vals = {}
    for model, metrics in summary.items():
        vals = [normalize(metrics.get(mk, 0), mk) for mk in FULL_METRICS]
        model_vals[model] = vals
    draw_radar(ax, FULL_LABELS, model_vals,
               "13 Models \u00d7 6 Metrics \u2014 Overall (P1-P4 Avg)")
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, fontsize=10,
               bbox_to_anchor=(0.5, -0.01), frameon=True, fancybox=True)
    plt.tight_layout(rect=[0, 0.07, 1, 0.95])
    out = os.path.join(RADAR_DIR, "radar_overall.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  \u2192 {out}")

    # ── Chart B: Per prompt level (P1/P2/P3/P4) ──
    fig, axes = plt.subplots(2, 2, figsize=(22, 20), subplot_kw=dict(projection="polar"))
    fig.suptitle("13 Models \u00d7 6 Metrics \u2014 P1 / P2 / P3 / P4",
                 fontsize=20, fontweight="bold", y=0.98)

    for pi, plevel in enumerate(["P1", "P2", "P3", "P4"]):
        ax = axes[pi // 2][pi % 2]
        model_vals = {}
        for model, methods in summary_by_method.items():
            if plevel in methods:
                m = methods[plevel]
                vals = [normalize(m.get(mk, 0), mk) for mk in FULL_METRICS]
                model_vals[model] = vals
        level_desc = {"P1": "Title Only", "P2": "Title+Abstract",
                      "P3": "+Discipline+Concepts", "P4": "+Relations (Full Context)"}
        draw_radar(ax, FULL_LABELS, model_vals, f"{plevel}: {level_desc[plevel]}")

    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, fontsize=11,
               bbox_to_anchor=(0.5, 0.01), frameon=True, fancybox=True)
    plt.tight_layout(rect=[0, 0.06, 1, 0.95])
    out = os.path.join(RADAR_DIR, "radar_P1P2P3P4.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  \u2192 {out}")

    # ── Chart C: Group comparison (3 groups side by side) ──
    fig, axes = plt.subplots(1, 3, figsize=(26, 9), subplot_kw=dict(projection="polar"))
    fig.suptitle("\u5206\u7ec4\u5bf9\u6bd4\u96f7\u8fbe\u56fe \u2014 \u95ed\u6e90 / \u5f00\u6e90 / \u63a8\u7406",
                 fontsize=20, fontweight="bold", y=1.04)

    for gi, (gname, g) in enumerate(MODEL_GROUPS.items()):
        ax = axes[gi]
        model_vals = {}
        for m in g["models"]:
            if m in summary:
                vals = [normalize(summary[m].get(mk, 0), mk) for mk in FULL_METRICS]
                model_vals[m] = vals
        draw_radar(ax, FULL_LABELS, model_vals, gname)
        ax.legend(loc="upper right", fontsize=9, bbox_to_anchor=(1.35, 1.15))

    plt.tight_layout()
    out = os.path.join(RADAR_DIR, "radar_group_comparison.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  \u2192 {out}")

    # ── Chart D: Per-level single model comparison (P1 only, P4 only) ──
    for plevel in ["P1", "P4"]:
        fig, ax = plt.subplots(figsize=(13, 11), subplot_kw=dict(projection="polar"))
        model_vals = {}
        for model, methods in summary_by_method.items():
            if plevel in methods:
                m = methods[plevel]
                vals = [normalize(m.get(mk, 0), mk) for mk in FULL_METRICS]
                model_vals[model] = vals
        desc = {"P1": "Title Only (Minimal Info)", "P4": "Full Context (Maximum Info)"}
        draw_radar(ax, FULL_LABELS, model_vals, f"{plevel}: {desc[plevel]}")
        h, l = ax.get_legend_handles_labels()
        fig.legend(h, l, loc="lower center", ncol=5, fontsize=10,
                   bbox_to_anchor=(0.5, -0.01), frameon=True, fancybox=True)
        plt.tight_layout(rect=[0, 0.07, 1, 0.95])
        out = os.path.join(RADAR_DIR, f"radar_{plevel}_single.png")
        fig.savefig(out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  \u2192 {out}")

    # ── Chart E: Heatmap summary table ──
    fig, ax = plt.subplots(figsize=(16, 8))
    models_sorted = sorted(summary.keys())
    metric_keys = FULL_METRICS
    metric_labels = FULL_LABELS

    data_matrix = []
    for m in models_sorted:
        row = [normalize(summary[m].get(mk, 0), mk) for mk in metric_keys]
        data_matrix.append(row)
    data_matrix = np.array(data_matrix)

    im = ax.imshow(data_matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=10)
    ax.set_xticks(range(len(metric_labels)))
    ax.set_xticklabels(metric_labels, fontsize=12, fontweight="bold", rotation=30, ha="right")
    ax.set_yticks(range(len(models_sorted)))
    ax.set_yticklabels([SHORT.get(m, m) for m in models_sorted], fontsize=11)

    for i in range(len(models_sorted)):
        for j in range(len(metric_keys)):
            val = data_matrix[i, j]
            color = "white" if val < 4 or val > 8 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                    fontsize=10, fontweight="bold", color=color)

    plt.colorbar(im, ax=ax, shrink=0.8, label="Score (0-10)")
    ax.set_title("13 Models \u00d7 6 Metrics \u2014 Heatmap", fontsize=16, fontweight="bold")
    plt.tight_layout()
    out = os.path.join(RADAR_DIR, "heatmap_summary.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  \u2192 {out}")

    print(f"\n[Step 4] \u6240\u6709\u56fe\u8868\u5df2\u4fdd\u5b58\u81f3: {RADAR_DIR}/")


# ============================================================================
# Main
# ============================================================================
def main():
    print("=" * 60)
    print("  CrossDisc-Bench \u591a\u6a21\u578b\u8bc4\u6d4b + \u96f7\u8fbe\u56fe")
    print("=" * 60)

    # Step 1
    papers_map = build_papers_map()

    # Step 2
    all_results = evaluate_all_models(papers_map)

    # Step 3
    summary, summary_by_method = aggregate_results(all_results)

    # Step 4
    generate_radar_charts(summary, summary_by_method)

    print("\n\u5168\u90e8\u5b8c\u6210!")


if __name__ == "__main__":
    main()

"""
生成多模型评测雷达图。
针对 L1/L2/L3 各层级的 6 个核心指标，以雷达图展示 13 个大模型的能力对比。

用法:
    OUTPUT_DIR=outputs/multimodel_eval_v7 python3 generate_radar_charts.py
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.font_manager as fm

# ── 中文字体 ──
for fname in ["SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Microsoft YaHei"]:
    if any(fname.lower() in f.name.lower() for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [fname]
        break
plt.rcParams["axes.unicode_minus"] = False

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "outputs/multimodel_eval_v7")
RADAR_DIR = os.path.join(OUTPUT_DIR, "radar_charts")
os.makedirs(RADAR_DIR, exist_ok=True)

# ── 6 core metrics per level ──
# These are the metrics from evaluate_benchmark.py (KG-based evaluation)
CORE_METRICS = {
    "Innovation":       "innovation",
    "Feasibility":      "feasibility",
    "Scientificity":    "scientificity",
    "Testability":      "testability",
    "Chain Coherence":  "chain_coherence",
    "Entity Coverage":  "entity_coverage",
}

# Text-based metrics for P1-P4 (non-KG evaluation)
TEXT_METRICS = {
    "BERTScore":        "text_bertscore_f1",
    "Novelty":          "judge_novelty",
    "Specificity":      "judge_specificity",
    "Feasibility":      "judge_feasibility",
    "Relevance":        "judge_relevance",
    "Cross-Disc":       "judge_cross_disciplinary",
}

# ── Model display config ──
MODEL_GROUPS = {
    "Group A: Closed-Source": {
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gemini-2.0-flash",
                    "claude-sonnet-4-20250514", "doubao-1-5-pro-32k-250115", "glm-4.5"],
        "colors": ["#E74C3C", "#C0392B", "#E67E22", "#F39C12", "#D35400", "#8E44AD"],
        "linestyles": ["-", "-", "-", "-", "-", "-"],
    },
    "Group B: Open-Source": {
        "models": ["qwen2.5-72b-instruct", "qwen2.5-7b-instruct", "deepseek-v3"],
        "colors": ["#2ECC71", "#27AE60", "#1ABC9C"],
        "linestyles": ["--", "--", "--"],
    },
    "Group C: Reasoning": {
        "models": ["o1", "o3-mini", "deepseek-r1", "qwen3-235b-a22b"],
        "colors": ["#3498DB", "#2980B9", "#1F618D", "#5DADE2"],
        "linestyles": ["-.", "-.", "-.", "-."],
    },
}

# Short names for display
MODEL_SHORT = {
    "gpt-4o-mini": "GPT-4o-mini",
    "gpt-4.1-mini": "GPT-4.1-mini",
    "gemini-2.0-flash": "Gemini-2.0",
    "claude-sonnet-4-20250514": "Claude-S4",
    "doubao-1-5-pro-32k-250115": "Doubao-1.5",
    "glm-4.5": "GLM-4.5",
    "qwen2.5-72b-instruct": "Qwen2.5-72B",
    "qwen2.5-7b-instruct": "Qwen2.5-7B",
    "deepseek-v3": "DS-V3",
    "o1": "O1",
    "o3-mini": "O3-mini",
    "deepseek-r1": "DS-R1",
    "qwen3-235b-a22b": "Qwen3-235B",
}


def build_model_style_map():
    """Build a mapping from model_id to (color, linestyle, short_name)."""
    style_map = {}
    for group_name, group in MODEL_GROUPS.items():
        for i, model in enumerate(group["models"]):
            style_map[model] = {
                "color": group["colors"][i],
                "linestyle": group["linestyles"][i],
                "short_name": MODEL_SHORT.get(model, model),
                "group": group_name,
            }
    return style_map


def draw_radar(ax, labels, model_data, title, style_map):
    """Draw a single radar chart on the given axis."""
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close polygon

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(0)

    # Grid
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9, fontweight="bold")
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=7, alpha=0.6)
    ax.spines["polar"].set_alpha(0.2)
    ax.grid(alpha=0.3)

    # Plot each model
    for model_id, values in model_data.items():
        if model_id not in style_map:
            continue
        s = style_map[model_id]
        vals = values + values[:1]  # close
        ax.plot(angles, vals, color=s["color"], linestyle=s["linestyle"],
                linewidth=1.8, label=s["short_name"], alpha=0.85)
        ax.fill(angles, vals, color=s["color"], alpha=0.05)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)


def normalize_to_10(value, metric_key):
    """Normalize metric values to 0-10 scale for radar chart."""
    # LLM judge metrics are already 0-10
    if metric_key in ("innovation", "feasibility", "scientificity", "testability",
                       "judge_novelty", "judge_specificity", "judge_feasibility",
                       "judge_relevance", "judge_cross_disciplinary"):
        return min(float(value), 10.0)
    # 0-1 metrics → scale to 10
    if metric_key in ("chain_coherence", "entity_coverage", "embedding_bridging",
                       "rao_stirling", "info_novelty", "text_bertscore_f1",
                       "bridging", "atypical_combination"):
        return min(float(value) * 10, 10.0)
    # ROUGE/BLEU are small, scale ×20
    if "rouge" in metric_key or "bleu" in metric_key:
        return min(float(value) * 20, 10.0)
    return min(float(value), 10.0)


def load_kg_eval_data():
    """Load KG-based evaluation data (for P5/structured paths)."""
    path = os.path.join(OUTPUT_DIR, "p5_kg_eval_results.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_multimodel_data():
    """Load multi-model evaluation summary."""
    path = os.path.join(OUTPUT_DIR, "multimodel_summary.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_multimodel_eval_detail():
    """Load detailed per-result evaluation data."""
    path = os.path.join(OUTPUT_DIR, "multimodel_eval_results.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_text_metric_radar(summary_data, style_map):
    """Generate radar chart for text-based metrics (P1-P4)."""
    labels = list(TEXT_METRICS.keys())
    metric_keys = list(TEXT_METRICS.values())

    fig, axes = plt.subplots(2, 2, figsize=(20, 18),
                              subplot_kw=dict(projection="polar"))
    fig.suptitle("多模型评测雷达图 — 文本指标 (P1-P4)",
                 fontsize=18, fontweight="bold", y=0.98)

    for pi, prompt_level in enumerate(["P1", "P2", "P3", "P4"]):
        ax = axes[pi // 2][pi % 2]

        # Filter data for this prompt level - aggregate from detailed results
        model_data = {}
        detail = load_multimodel_eval_detail()
        if detail:
            from collections import defaultdict
            model_metrics = defaultdict(lambda: defaultdict(list))
            for r in detail:
                if r.get("method") != prompt_level:
                    continue
                model = r.get("model", "")
                for mk in metric_keys:
                    if mk in r and r[mk] is not None:
                        model_metrics[model][mk].append(r[mk])

            for model, metrics in model_metrics.items():
                vals = []
                for mk in metric_keys:
                    raw = np.mean(metrics.get(mk, [0])) if metrics.get(mk) else 0
                    vals.append(normalize_to_10(raw, mk))
                model_data[model] = vals
        elif summary_data:
            for model, metrics in summary_data.items():
                vals = [normalize_to_10(metrics.get(mk, 0), mk) for mk in metric_keys]
                model_data[model] = vals

        draw_radar(ax, labels, model_data, f"{prompt_level} Level", style_map)

    # Legend
    handles, labels_leg = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="lower center", ncol=5,
               fontsize=10, bbox_to_anchor=(0.5, 0.01), frameon=True,
               fancybox=True, shadow=True)

    plt.tight_layout(rect=[0, 0.06, 1, 0.95])
    out_path = os.path.join(RADAR_DIR, "radar_text_metrics_P1P4.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存: {out_path}")
    return out_path


def generate_kg_level_radar(kg_data, style_map):
    """Generate radar charts for KG-based L1/L2/L3 metrics."""
    if not kg_data:
        print("  警告: 无 KG 评测数据，跳过 L1/L2/L3 雷达图")
        return None

    labels = list(CORE_METRICS.keys())
    metric_keys = list(CORE_METRICS.values())

    fig, axes = plt.subplots(1, 3, figsize=(24, 9),
                              subplot_kw=dict(projection="polar"))
    fig.suptitle("多模型评测雷达图 — KG 结构指标 (L1 / L2 / L3)",
                 fontsize=18, fontweight="bold", y=1.02)

    for li, level in enumerate(["L1", "L2", "L3"]):
        ax = axes[li]

        # Aggregate per-model
        model_data = {}
        from collections import defaultdict
        model_scores = defaultdict(lambda: defaultdict(list))

        for item in kg_data:
            model = item.get("model", "default")
            scores = item.get("scores", {})
            for mk in metric_keys:
                key = f"{level}_{mk}"
                if key in scores and scores[key] is not None:
                    model_scores[model][mk].append(scores[key])

        for model, metrics in model_scores.items():
            vals = []
            for mk in metric_keys:
                raw = np.mean(metrics.get(mk, [0])) if metrics.get(mk) else 0
                vals.append(normalize_to_10(raw, mk))
            model_data[model] = vals

        level_names = {"L1": "L1 (宏观)", "L2": "L2 (中观)", "L3": "L3 (微观)"}
        draw_radar(ax, labels, model_data, level_names[level], style_map)

    handles, labels_leg = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="lower center", ncol=5,
               fontsize=10, bbox_to_anchor=(0.5, -0.02), frameon=True,
               fancybox=True, shadow=True)

    plt.tight_layout(rect=[0, 0.06, 1, 0.96])
    out_path = os.path.join(RADAR_DIR, "radar_kg_metrics_L1L2L3.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存: {out_path}")
    return out_path


def generate_single_level_radar(summary_data, style_map, level="L1"):
    """Generate a single large radar for one level with all 13 models."""
    labels = list(CORE_METRICS.keys())
    metric_keys = list(CORE_METRICS.values())

    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(projection="polar"))

    model_data = {}
    if summary_data:
        for model, metrics in summary_data.items():
            vals = []
            for mk in metric_keys:
                key = f"{level}_{mk}" if f"{level}_{mk}" in metrics else mk
                raw = metrics.get(key, metrics.get(mk, 0))
                vals.append(normalize_to_10(raw, mk))
            model_data[model] = vals

    draw_radar(ax, labels, model_data,
               f"13 Models × 6 Metrics — {level} Level", style_map)

    handles, labels_leg = ax.get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="lower center", ncol=5,
               fontsize=10, bbox_to_anchor=(0.5, 0.0), frameon=True,
               fancybox=True, shadow=True)

    plt.tight_layout(rect=[0, 0.08, 1, 0.95])
    out_path = os.path.join(RADAR_DIR, f"radar_{level}_single.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存: {out_path}")
    return out_path


def generate_group_comparison(summary_data, style_map):
    """Generate grouped radar charts: one chart per group."""
    labels = list(TEXT_METRICS.keys())
    metric_keys = list(TEXT_METRICS.values())

    fig, axes = plt.subplots(1, 3, figsize=(24, 9),
                              subplot_kw=dict(projection="polar"))
    fig.suptitle("多模型评测雷达图 — 按分组对比",
                 fontsize=18, fontweight="bold", y=1.02)

    for gi, (group_name, group) in enumerate(MODEL_GROUPS.items()):
        ax = axes[gi]
        model_data = {}
        if summary_data:
            for model in group["models"]:
                if model in summary_data:
                    vals = [normalize_to_10(summary_data[model].get(mk, 0), mk)
                            for mk in metric_keys]
                    model_data[model] = vals

        draw_radar(ax, labels, model_data, group_name, style_map)
        ax.legend(loc="upper right", fontsize=8, bbox_to_anchor=(1.3, 1.1))

    plt.tight_layout()
    out_path = os.path.join(RADAR_DIR, "radar_group_comparison.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存: {out_path}")
    return out_path


def generate_demo_radar(style_map):
    """Generate demo radar charts with simulated data for preview."""
    print("\n  === 生成模拟数据预览雷达图 ===")

    np.random.seed(42)
    labels = list(CORE_METRICS.keys())

    # Simulate scores: each model group has characteristic strengths
    sim_data = {}
    # Group A: Closed-source - generally high, balanced
    for m in MODEL_GROUPS["Group A: Closed-Source"]["models"]:
        sim_data[m] = (np.random.uniform(5.5, 8.5, 6) + np.array([0.5, 0.3, 0.2, 0.1, 0.4, 0.3])).tolist()
    # Group B: Open-source - slightly lower
    for m in MODEL_GROUPS["Group B: Open-Source"]["models"]:
        sim_data[m] = (np.random.uniform(5.0, 8.0, 6) + np.array([0.0, 0.2, 0.3, 0.0, 0.5, 0.4])).tolist()
    # Group C: Reasoning - higher on innovation/scientificity
    for m in MODEL_GROUPS["Group C: Reasoning"]["models"]:
        sim_data[m] = (np.random.uniform(5.5, 8.0, 6) + np.array([1.5, 0.8, 1.0, 0.5, 0.2, 0.1])).tolist()

    # Clamp to 10
    for m in sim_data:
        sim_data[m] = [min(v, 10.0) for v in sim_data[m]]

    # Single L1 chart
    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(projection="polar"))
    draw_radar(ax, labels, sim_data,
               "L1 Core Metrics — 13 Models (Demo Data)", style_map)
    handles, labels_leg = ax.get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="lower center", ncol=5,
               fontsize=10, bbox_to_anchor=(0.5, 0.0), frameon=True,
               fancybox=True, shadow=True)
    plt.tight_layout(rect=[0, 0.08, 1, 0.95])
    out = os.path.join(RADAR_DIR, "radar_L1_demo.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存 (demo): {out}")

    # L1/L2/L3 triptych
    fig, axes = plt.subplots(1, 3, figsize=(24, 9),
                              subplot_kw=dict(projection="polar"))
    fig.suptitle("KG 结构指标雷达图 — L1 / L2 / L3 (Demo Data)",
                 fontsize=18, fontweight="bold", y=1.02)
    for li, level in enumerate(["L1 (宏观)", "L2 (中观)", "L3 (微观)"]):
        # Slightly vary data per level
        level_data = {}
        for m, vals in sim_data.items():
            noise = np.random.uniform(-0.5, 0.5, 6)
            level_data[m] = [min(max(v + n, 0), 10) for v, n in zip(vals, noise)]
        draw_radar(axes[li], labels, level_data, level, style_map)

    handles, labels_leg = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="lower center", ncol=5,
               fontsize=10, bbox_to_anchor=(0.5, -0.02), frameon=True)
    plt.tight_layout(rect=[0, 0.06, 1, 0.96])
    out = os.path.join(RADAR_DIR, "radar_L1L2L3_demo.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存 (demo): {out}")

    # Group comparison
    fig, axes = plt.subplots(1, 3, figsize=(24, 9),
                              subplot_kw=dict(projection="polar"))
    fig.suptitle("分组对比雷达图 (Demo Data)",
                 fontsize=18, fontweight="bold", y=1.02)
    for gi, (gname, group) in enumerate(MODEL_GROUPS.items()):
        group_data = {m: sim_data[m] for m in group["models"] if m in sim_data}
        draw_radar(axes[gi], labels, group_data, gname, style_map)
        axes[gi].legend(loc="upper right", fontsize=8, bbox_to_anchor=(1.3, 1.1))
    plt.tight_layout()
    out = os.path.join(RADAR_DIR, "radar_group_demo.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  保存 (demo): {out}")


def main():
    print("=" * 60)
    print("  CrossDisc-Bench 多模型评测雷达图生成")
    print("=" * 60)

    style_map = build_model_style_map()

    # Try to load real data
    summary = load_multimodel_data()
    kg_data = load_kg_eval_data()

    if summary:
        print(f"\n  已加载评测数据: {len(summary)} 个模型")
        generate_text_metric_radar(summary, style_map)
        generate_group_comparison(summary, style_map)

        for level in ["L1", "L2", "L3"]:
            generate_single_level_radar(summary, style_map, level)
    else:
        print("\n  未找到评测数据，生成模拟预览图...")

    if kg_data:
        generate_kg_level_radar(kg_data, style_map)

    # Always generate demo for preview
    generate_demo_radar(style_map)

    print(f"\n  所有雷达图已保存至: {RADAR_DIR}/")


if __name__ == "__main__":
    main()

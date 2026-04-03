"""
generate_multimodel_radar.py — 多模型评测雷达图生成

从 multimodel_16metrics_summary.json 生成:
  Figure 1: 全模型总览雷达图 (6 核心指标)
  Figure 2: 按组对比 (Group A/B/C)
  Figure 3: P1-P4 Prompt 级别效果对比 (选 top 模型)

Usage:
    python generate_multimodel_radar.py \
        --input outputs/multimodel_eval_v7/multimodel_16metrics_summary.json \
        --output-dir outputs/multimodel_eval_v7/radar_charts
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Chinese font support
plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------------------
# Model groups
# ---------------------------------------------------------------------------
GROUP_A = ["gpt-4o-mini", "gpt-4.1-mini", "gemini-2.0-flash",
           "claude-sonnet-4-20250514", "doubao-1-5-pro-32k-250115", "glm-4.5"]
GROUP_B = ["qwen2.5-72b-instruct", "qwen2.5-7b-instruct", "deepseek-v3"]
GROUP_C = ["o1", "o3-mini", "deepseek-r1", "qwen3-235b-a22b"]

GROUP_LABELS = {
    "A": "Group A: Commercial Closed-Source",
    "B": "Group B: Open-Source",
    "C": "Group C: Reasoning-Enhanced",
}

# Color palettes per group
COLORS_ALL = [
    "#2563EB", "#DC2626", "#16A34A", "#9333EA", "#EA580C",
    "#0891B2", "#CA8A04", "#DB2777", "#4F46E5", "#059669",
    "#D97706", "#7C3AED", "#E11D48",
]
COLORS_A = ["#2563EB", "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE", "#1E40AF"]
COLORS_B = ["#DC2626", "#EF4444", "#F87171"]
COLORS_C = ["#16A34A", "#22C55E", "#4ADE80", "#86EFAC"]


# ---------------------------------------------------------------------------
# Core metrics definition
# ---------------------------------------------------------------------------
CORE_METRICS = [
    ("Innovation", "L1_innovation"),
    ("Testability", "L1_testability"),
    ("Consistency F1", "L1_consistency_f1"),
    ("Rao-Stirling", "L1_rao_stirling"),
    ("Factual Precision", "L1_factual_precision"),
    ("Atypical Comb.", "L1_atypical_combination"),
    ("Chain Coherence", "L1_chain_coherence"),
    ("Concept F1", "L1_concept_f1"),
]

# Metrics that are on 0-10 scale (LLM scores)
SCALE_10_METRICS = {"L1_innovation", "L1_feasibility", "L1_scientificity", "L1_testability",
                    "L2_innovation", "L2_feasibility", "L2_scientificity", "L2_testability",
                    "L3_innovation", "L3_feasibility", "L3_scientificity", "L3_testability"}


def normalize_val(key: str, val: float) -> float:
    """Normalize metric to 0-1 range."""
    if key in SCALE_10_METRICS:
        return val / 10.0
    return val


# ---------------------------------------------------------------------------
# Radar plot helper
# ---------------------------------------------------------------------------

def radar_plot(
    ax,
    categories: List[str],
    values_dict: Dict[str, List[float]],
    title: str = "",
    colors: List[str] | None = None,
    fill_alpha: float = 0.10,
    ylim: tuple = (0, 1),
):
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(*ylim)
    ax.set_rlabel_position(30)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8)

    default_colors = COLORS_ALL
    if colors is None:
        colors = default_colors

    for idx, (label, vals) in enumerate(values_dict.items()):
        data = vals + vals[:1]
        color = colors[idx % len(colors)]
        ax.plot(angles, data, "o-", linewidth=1.5, markersize=3, label=label, color=color)
        ax.fill(angles, data, alpha=fill_alpha, color=color)

    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", pad=18)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="multimodel_16metrics_summary.json")
    parser.add_argument("--output-dir", default="outputs/multimodel_eval_v7/radar_charts")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    model_overall = data.get("by_model_overall", {})
    by_model_method = data.get("by_model_method", {})

    if not model_overall:
        print("No model data found!")
        return

    labels = [m[0] for m in CORE_METRICS]
    metric_keys = [m[1] for m in CORE_METRICS]

    def get_model_values(model: str) -> List[float]:
        scores = model_overall.get(model, {})
        return [normalize_val(k, scores.get(k, 0.0)) for k in metric_keys]

    # ── Figure 1: All models overview ─────────────────────────────────

    available_models = [m for m in sorted(model_overall.keys())]
    print(f"Available models: {available_models}")

    fig1, ax1 = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    model_data = {m: get_model_values(m) for m in available_models}
    radar_plot(ax1, labels, model_data, title="Multi-Model Evaluation — Core Metrics")
    ax1.legend(loc="upper right", bbox_to_anchor=(1.45, 1.15), fontsize=8)
    fig1.tight_layout()

    p1 = os.path.join(args.output_dir, "radar_all_models.png")
    fig1.savefig(p1, dpi=200, bbox_inches="tight")
    fig1.savefig(p1.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p1}")
    plt.close(fig1)

    # ── Figure 2: Group comparison (3 subplots) ──────────────────────

    fig2, axes = plt.subplots(1, 3, figsize=(24, 8), subplot_kw=dict(polar=True))

    for ax, (group_key, group_models, group_colors) in zip(
        axes,
        [("A", GROUP_A, COLORS_A), ("B", GROUP_B, COLORS_B), ("C", GROUP_C, COLORS_C)],
    ):
        present = [m for m in group_models if m in model_overall]
        if not present:
            ax.set_title(f"{GROUP_LABELS[group_key]} (no data)", fontsize=10)
            continue
        gdata = {m: get_model_values(m) for m in present}
        radar_plot(ax, labels, gdata, title=GROUP_LABELS[group_key], colors=group_colors)
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=7)

    fig2.suptitle("Model Group Comparison", fontsize=14, fontweight="bold", y=1.02)
    fig2.tight_layout()

    p2 = os.path.join(args.output_dir, "radar_groups.png")
    fig2.savefig(p2, dpi=200, bbox_inches="tight")
    fig2.savefig(p2.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p2}")
    plt.close(fig2)

    # ── Figure 3: P1-P4 prompt level comparison ──────────────────────

    # Pick top 3 models by average innovation score
    model_scores = {m: model_overall[m].get("L1_innovation", 0) for m in available_models}
    top_models = sorted(model_scores, key=model_scores.get, reverse=True)[:3]

    fig3, axes3 = plt.subplots(1, len(top_models), figsize=(8 * len(top_models), 8),
                                subplot_kw=dict(polar=True))
    if len(top_models) == 1:
        axes3 = [axes3]

    prompt_colors = ["#2563EB", "#DC2626", "#16A34A", "#9333EA"]

    for ax, model in zip(axes3, top_models):
        methods = by_model_method.get(model, {})
        method_data = {}
        for method_name in ["P1", "P2", "P3", "P4"]:
            if method_name in methods:
                scores = methods[method_name]
                vals = [normalize_val(k, scores.get(k, 0.0)) for k in metric_keys]
                method_data[method_name] = vals

        if method_data:
            radar_plot(ax, labels, method_data, title=f"{model}", colors=prompt_colors)
            ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)

    fig3.suptitle("Prompt Level Comparison (Top Models)", fontsize=14, fontweight="bold", y=1.02)
    fig3.tight_layout()

    p3 = os.path.join(args.output_dir, "radar_prompt_levels.png")
    fig3.savefig(p3, dpi=200, bbox_inches="tight")
    fig3.savefig(p3.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p3}")
    plt.close(fig3)

    # ── Figure 4: Heatmap (models × metrics) ─────────────────────────

    fig4, ax4 = plt.subplots(figsize=(14, max(6, len(available_models) * 0.5 + 2)))

    matrix = []
    for m in available_models:
        row = [normalize_val(k, model_overall[m].get(k, 0.0)) for k in metric_keys]
        matrix.append(row)

    matrix = np.array(matrix)
    im = ax4.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)

    ax4.set_xticks(range(len(labels)))
    ax4.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax4.set_yticks(range(len(available_models)))
    ax4.set_yticklabels(available_models, fontsize=9)

    # Add value annotations
    for i in range(len(available_models)):
        for j in range(len(labels)):
            val = matrix[i, j]
            ax4.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                     color="white" if val > 0.5 else "black")

    fig4.colorbar(im, ax=ax4, shrink=0.8)
    ax4.set_title("Multi-Model Evaluation Heatmap", fontsize=13, fontweight="bold")
    fig4.tight_layout()

    p4 = os.path.join(args.output_dir, "heatmap_models.png")
    fig4.savefig(p4, dpi=200, bbox_inches="tight")
    fig4.savefig(p4.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p4}")
    plt.close(fig4)

    print(f"\nAll charts saved to {args.output_dir}/")


if __name__ == "__main__":
    main()

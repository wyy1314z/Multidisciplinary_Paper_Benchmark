"""
plot_radar.py — Generate radar charts for CrossDisc evaluation results.

Produces two figures:
  1. A single radar chart with L1/L2/L3 overlaid (core metrics)
  2. A 2x2 panel: Innovation, Reliability, Structure, Diversity

Usage:
    python plot_radar.py [--input eval_results.json] [--output-dir figures/]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --------------------------------------------------------------------------
# Chinese font support
# --------------------------------------------------------------------------
plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def load_results(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def aggregate_scores(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """Average scores across all items."""
    accum: Dict[str, List[float]] = defaultdict(list)
    for item in results:
        for k, v in item["scores"].items():
            accum[k].append(v)
    return {k: float(np.mean(v)) for k, v in accum.items()}


# --------------------------------------------------------------------------
# Radar plot helper
# --------------------------------------------------------------------------

def radar_plot(
    ax,
    categories: List[str],
    values_dict: Dict[str, List[float]],
    title: str = "",
    colors: List[str] | None = None,
    fill_alpha: float = 0.12,
    ylim: tuple = (0, 1),
):
    """Draw a radar chart on the given axes."""
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close the loop

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    # Draw gridlines
    ax.set_ylim(*ylim)
    ax.set_rlabel_position(30)

    # Category labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=8)

    default_colors = ["#2563EB", "#DC2626", "#16A34A", "#9333EA", "#EA580C"]
    if colors is None:
        colors = default_colors

    for idx, (label, vals) in enumerate(values_dict.items()):
        data = vals + vals[:1]
        color = colors[idx % len(colors)]
        ax.plot(angles, data, "o-", linewidth=1.8, markersize=4, label=label, color=color)
        ax.fill(angles, data, alpha=fill_alpha, color=color)

    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", pad=18)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="eval_results.json")
    parser.add_argument("--output-dir", default="figures")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    results = load_results(args.input)
    avg = aggregate_scores(results)

    # ── Define metric groups ──────────────────────────────────────────

    # LLM scores are on 0-10 scale, normalize to 0-1
    def g(level, metric):
        """Get metric value, normalizing 0-10 LLM scores to 0-1."""
        v = avg.get(f"{level}_{metric}", 0.0)
        if metric in ("innovation", "feasibility", "scientificity", "testability"):
            v = v / 10.0
        return round(v, 4)

    # Group 1: Core capability metrics (for the main radar)
    core_metrics = [
        ("Innovation", "innovation"),
        ("Feasibility", "feasibility"),
        ("Scientificity", "scientificity"),
        ("Testability", "testability"),
        ("Chain Coherence", "chain_coherence"),
        ("Factual Precision", "factual_precision"),
        ("1-Hallucination", "hallucination_rate"),  # invert
        ("Concept F1", "concept_f1"),
        ("Embedding Bridge", "embedding_bridging"),
        ("Remote Assoc.", "remote_association_index"),
    ]

    core_labels = [m[0] for m in core_metrics]

    def get_core_values(level):
        vals = []
        for label, metric in core_metrics:
            v = g(level, metric)
            if metric == "hallucination_rate":
                v = round(1.0 - v, 4)  # invert: lower hallucination = better
            vals.append(v)
        return vals

    # ── Figure 1: L1/L2/L3 overlay radar ─────────────────────────────

    fig1, ax1 = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    radar_plot(
        ax1,
        core_labels,
        {
            "L1 (Broad)": get_core_values("L1"),
            "L2 (Medium)": get_core_values("L2"),
            "L3 (Deep)": get_core_values("L3"),
        },
        title="CrossDisc Evaluation — L1 / L2 / L3 Comparison",
    )
    ax1.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), fontsize=10)
    fig1.tight_layout()
    p1 = os.path.join(args.output_dir, "radar_core_l123.png")
    fig1.savefig(p1, dpi=200, bbox_inches="tight")
    fig1.savefig(p1.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p1}")

    # ── Figure 2: 4-panel radar by dimension ─────────────────────────

    panels = {
        "Innovation & Novelty": [
            ("Innovation", "innovation"),
            ("Atypical Comb.", "atypical_combination"),
            ("Remote Assoc.", "remote_association_index"),
            ("Novelty Balance", "novelty_convention_balance"),
            ("Info Novelty", "info_novelty"),
            ("Emb. Bridging", "embedding_bridging"),
        ],
        "Reliability & Factuality": [
            ("Factual Prec.", "factual_precision"),
            ("1-Halluc. Rate", "hallucination_rate"),
            ("Consistency F1", "consistency_f1"),
            ("Concept F1", "concept_f1"),
            ("Evidence Cov.", "evidence_coverage"),
            ("Scientificity", "scientificity"),
        ],
        "Structure & Coherence": [
            ("Chain Coherence", "chain_coherence"),
            ("Causal Dir. Acc.", "causal_direction_accuracy"),
            ("Feasibility", "feasibility"),
            ("Testability", "testability"),
            ("Depth Quality", None),  # special: from depth_depth_quality
            ("Path Align.", "path_alignment_best"),
        ],
        "Diversity & Coverage": [
            ("Rao-Stirling", "rao_stirling"),
            ("Disc. Leap Idx", "disciplinary_leap_index"),
            ("Disc. Balance", "discipline_balance"),
            ("Entity Coverage", "entity_coverage"),
            ("Pairwise Div.", "pairwise_diversity"),
            ("Concept Recall", "concept_recall"),
        ],
    }

    fig2, axes = plt.subplots(2, 2, figsize=(14, 14), subplot_kw=dict(polar=True))

    for ax, (panel_title, metrics) in zip(axes.flat, panels.items()):
        labels = [m[0] for m in metrics]

        level_data = {}
        for level in ["L1", "L2", "L3"]:
            vals = []
            for label, metric in metrics:
                if metric is None:
                    # depth_quality is not per-level
                    v = avg.get("depth_depth_quality", 0.0)
                elif metric == "hallucination_rate":
                    v = 1.0 - g(level, metric)
                else:
                    v = g(level, metric)
                vals.append(round(v, 4))
            level_data[level] = vals

        radar_plot(ax, labels, level_data, title=panel_title)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)

    fig2.suptitle("CrossDisc Multi-Dimensional Evaluation", fontsize=14, fontweight="bold", y=1.01)
    fig2.tight_layout()
    p2 = os.path.join(args.output_dir, "radar_4panel.png")
    fig2.savefig(p2, dpi=200, bbox_inches="tight")
    fig2.savefig(p2.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p2}")

    # ── Figure 3: Per-item radar (one subplot per item) ──────────────

    n_items = len(results)
    fig3, axes3 = plt.subplots(1, n_items, figsize=(7 * n_items, 7), subplot_kw=dict(polar=True))
    if n_items == 1:
        axes3 = [axes3]

    for ax, item in zip(axes3, results):
        item_id = item["id"]
        sc = item["scores"]

        def item_g(level, metric):
            v = sc.get(f"{level}_{metric}", 0.0)
            if metric in ("innovation", "feasibility", "scientificity", "testability"):
                v = v / 10.0
            return round(v, 4)

        level_data = {}
        for level in ["L1", "L2", "L3"]:
            vals = []
            for label, metric in core_metrics:
                v = item_g(level, metric)
                if metric == "hallucination_rate":
                    v = round(1.0 - v, 4)
                vals.append(v)
            level_data[level] = vals

        radar_plot(ax, core_labels, level_data, title=f"Item {item_id[:8]}")
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)

    fig3.suptitle("Per-Item Evaluation Radar", fontsize=14, fontweight="bold", y=1.02)
    fig3.tight_layout()
    p3 = os.path.join(args.output_dir, "radar_per_item.png")
    fig3.savefig(p3, dpi=200, bbox_inches="tight")
    fig3.savefig(p3.replace(".png", ".pdf"), bbox_inches="tight")
    print(f"Saved: {p3}")

    # ── Print values table ───────────────────────────────────────────
    print("\n=== Core Metrics (normalized to 0-1) ===")
    print(f"{'Metric':<25s} {'L1':>8s} {'L2':>8s} {'L3':>8s}")
    print("-" * 50)
    for label, metric in core_metrics:
        row = []
        for level in ["L1", "L2", "L3"]:
            v = g(level, metric)
            if metric == "hallucination_rate":
                v = round(1.0 - v, 4)
            row.append(v)
        print(f"{label:<25s} {row[0]:>8.4f} {row[1]:>8.4f} {row[2]:>8.4f}")


if __name__ == "__main__":
    main()

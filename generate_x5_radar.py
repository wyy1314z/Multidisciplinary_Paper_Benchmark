"""Generate the X+5 radar chart from multimodel 16-metric summaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
plt.rcParams["axes.unicode_minus"] = False


MetricSpec = Sequence[Tuple[str, float, bool]]

SCALE_10_METRICS = {
    "innovation",
    "scientificity",
    "testability",
    "feasibility",
    "legacy_feasibility",
    "feasibility_data",
    "feasibility_method",
    "feasibility_resource",
    "feasibility_validation",
}

X5_METRICS: List[Tuple[str, str, MetricSpec]] = [
    (
        "X: Interdisciplinary Integration",
        "interdisciplinary_integration",
        (
            ("rao_stirling", 0.50, False),
            ("discipline_balance", 0.20, False),
            ("disciplinary_leap_index", 0.15, False),
            ("embedding_bridging", 0.15, False),
        ),
    ),
    (
        "Structural Validity",
        "structural_validity",
        (
            ("consistency_f1", 0.50, False),
            ("chain_coherence", 0.20, False),
            ("causal_direction_accuracy", 0.15, False),
            ("consistency_recall", 0.15, False),
        ),
    ),
    (
        "Evidence Groundedness",
        "evidence_groundedness",
        (
            ("factual_precision", 0.45, False),
            ("concept_f1", 0.15, False),
            ("relation_precision", 0.15, False),
            ("evidence_coverage", 0.10, False),
            ("path_alignment_best", 0.10, False),
            ("hallucination_rate", 0.05, True),
        ),
    ),
    (
        "Novelty",
        "novelty",
        (
            ("info_novelty", 0.50, False),
            ("atypical_combination", 0.20, False),
            ("remote_association_index", 0.20, False),
            ("novelty_convention_balance", 0.10, False),
        ),
    ),
    (
        "Testability",
        "testability",
        (
            ("testability", 1.00, False),
        ),
    ),
    (
        "Feasibility",
        "feasibility",
        (
            ("feasibility_data", 0.25, False),
            ("feasibility_method", 0.25, False),
            ("feasibility_resource", 0.25, False),
            ("feasibility_validation", 0.25, False),
        ),
    ),
]


def _clip01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _metric_value(scores: Mapping[str, float], level: str, name: str, invert: bool = False) -> float | None:
    key = f"{level}_{name}"
    if key not in scores and name == "feasibility_data":
        key = f"{level}_feasibility"
    if key not in scores:
        return None

    value = float(scores.get(key, 0.0) or 0.0)
    if name in SCALE_10_METRICS:
        value /= 10.0
    if invert:
        value = 1.0 - value
    return _clip01(value)


def _weighted_score(scores: Mapping[str, float], level: str, spec: MetricSpec) -> float:
    total = 0.0
    used = 0.0
    for metric_name, weight, invert in spec:
        value = _metric_value(scores, level, metric_name, invert=invert)
        if value is None:
            continue
        total += value * weight
        used += weight
    return _clip01(total / used) if used else 0.0


def build_x5_scores(model_overall: Mapping[str, Mapping[str, float]], level: str) -> Dict[str, Dict[str, float]]:
    x5: Dict[str, Dict[str, float]] = {}
    for model, scores in sorted(model_overall.items()):
        x5[model] = {
            metric_key: round(_weighted_score(scores, level, spec), 4)
            for _, metric_key, spec in X5_METRICS
        }
    return x5


def write_csv(path: str, rows: Mapping[str, Mapping[str, float]]) -> None:
    fields = ["model"] + [metric_key for _, metric_key, _ in X5_METRICS]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for model, values in rows.items():
            writer.writerow({"model": model, **values})


def radar_plot(path: str, scores: Mapping[str, Mapping[str, float]], title: str) -> None:
    labels = [label for label, _, _ in X5_METRICS]
    keys = [metric_key for _, metric_key, _ in X5_METRICS]
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"polar": True})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 1)
    ax.set_rlabel_position(30)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=22)

    colors = plt.cm.tab20(np.linspace(0, 1, max(len(scores), 1)))
    for idx, (model, values) in enumerate(scores.items()):
        data = [values.get(key, 0.0) for key in keys]
        data += data[:1]
        ax.plot(angles, data, "o-", linewidth=1.6, markersize=3, label=model, color=colors[idx])
        ax.fill(angles, data, alpha=0.06, color=colors[idx])

    ax.legend(loc="upper right", bbox_to_anchor=(1.55, 1.15), fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    fig.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)


def heatmap(path: str, scores: Mapping[str, Mapping[str, float]], title: str) -> None:
    labels = [label for label, _, _ in X5_METRICS]
    keys = [metric_key for _, metric_key, _ in X5_METRICS]
    models = list(scores)
    matrix = np.array([[scores[m].get(k, 0.0) for k in keys] for m in models])

    fig, ax = plt.subplots(figsize=(13, max(5, len(models) * 0.45 + 2)))
    im = ax.imshow(matrix, cmap="YlGnBu", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold")
    for i in range(len(models)):
        for j in range(len(labels)):
            value = matrix[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    fig.savefig(path.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate X+5 metric radar from multimodel summary")
    parser.add_argument("--input", required=True, help="Path to multimodel_16metrics_summary.json")
    parser.add_argument("--output-dir", required=True, help="Directory for X+5 charts and tables")
    parser.add_argument("--level", default="L1", choices=["L1", "L2", "L3"], help="Metric level prefix")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    model_overall = data.get("by_model_overall", {})
    scores = build_x5_scores(model_overall, args.level)
    if not scores:
        raise SystemExit("No model scores found in multimodel summary")

    json_path = os.path.join(args.output_dir, "x5_scores.json")
    csv_path = os.path.join(args.output_dir, "x5_scores.csv")
    radar_path = os.path.join(args.output_dir, "x5_radar_all_models.png")
    heatmap_path = os.path.join(args.output_dir, "x5_heatmap.png")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"level": args.level, "scores": scores}, f, ensure_ascii=False, indent=2)
    write_csv(csv_path, scores)
    radar_plot(radar_path, scores, title=f"Query-Centric Multi-Model Evaluation (X+5, {args.level})")
    heatmap(heatmap_path, scores, title=f"X+5 Metric Scores ({args.level})")

    print(f"X+5 scores JSON: {json_path}")
    print(f"X+5 scores CSV:  {csv_path}")
    print(f"X+5 radar:       {radar_path}")
    print(f"X+5 heatmap:      {heatmap_path}")


if __name__ == "__main__":
    main()

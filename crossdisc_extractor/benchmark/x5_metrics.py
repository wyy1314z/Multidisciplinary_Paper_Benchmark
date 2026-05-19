"""X+5 aggregate metric system for CrossDisc evaluation.

The X dimension is the CrossDisc-specific capability:
Interdisciplinary Integration.  The other five dimensions are general
scientific-hypothesis quality axes.

X+5 aggregate scores and their submetrics are reported on a 1-5 scale.
Fine-grained source metrics are kept unchanged in the evaluator output; this
module provides a compact reporting layer on top of them.
"""

from __future__ import annotations

import math
from typing import Dict, List, Mapping, Sequence, Tuple


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


# Tuple format:
# (display_label, output_key, ((source_metric_name, weight, invert), ...))
#
# The source metric names are level-local.  For example, "consistency_f1" is
# resolved as "L1_consistency_f1" when level="L1".
X5_METRICS: List[Tuple[str, str, MetricSpec]] = [
    (
        "X: Interdisciplinary Integration",
        "interdisciplinary_integration",
        (
            ("rao_stirling", 0.60, False),
            ("disciplinary_leap_index", 0.20, False),
            ("embedding_bridging", 0.20, False),
        ),
    ),
    (
        "Structural Validity",
        "structural_validity",
        (
            ("consistency_f1", 0.55, False),
            ("chain_coherence", 0.20, False),
            ("causal_direction_accuracy", 0.15, False),
            ("consistency_recall", 0.10, False),
        ),
    ),
    (
        "Evidence Groundedness",
        "evidence_groundedness",
        (
            ("factual_precision", 0.50, False),
            ("concept_f1", 0.15, False),
            ("relation_precision", 0.15, False),
            ("evidence_coverage", 0.10, False),
            ("path_alignment_best", 0.05, False),
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


X5_DESCRIPTIONS = {
    "structural_validity": {
        "primary_metric": "Structural Validity",
        "definition": (
            "Measures whether the generated hypothesis forms a complete, "
            "directionally plausible, semantically coherent scientific reasoning chain."
        ),
        "subdimensions": [
            "path_alignment",
            "chain_coherence",
            "causal_direction",
            "step_completeness",
        ],
        "implemented_metrics": [
            "consistency_f1",
            "consistency_precision",
            "consistency_recall",
            "chain_coherence",
            "causal_direction_accuracy",
        ],
    },
    "evidence_groundedness": {
        "primary_metric": "Evidence Groundedness",
        "definition": (
            "Measures whether claims, concepts, and relations are supported by "
            "the abstract, GT terms plus web-search terms, GT relations, or evidence paths."
        ),
        "subdimensions": [
            "claim_support",
            "concept_grounding",
            "relation_grounding",
            "evidence_path_support",
        ],
        "implemented_metrics": [
            "factual_precision",
            "concept_f1",
            "relation_precision",
            "evidence_coverage",
            "hallucination_rate",
            "path_alignment_best",
        ],
    },
    "interdisciplinary_integration": {
        "primary_metric": "Interdisciplinary Integration",
        "definition": (
            "Measures whether the hypothesis substantively bridges multiple disciplines "
            "with meaningful cognitive distance."
        ),
        "subdimensions": [
            "disciplinary_diversity",
            "disciplinary_disparity",
            "semantic_bridging",
        ],
        "implemented_metrics": [
            "rao_stirling",
            "disciplinary_leap_index",
            "embedding_bridging",
        ],
    },
    "novelty": {
        "primary_metric": "Novelty",
        "definition": (
            "Measures whether the hypothesis proposes rare, information-bearing "
            "knowledge recombinations relative to the historical KG and reference paths."
        ),
        "subdimensions": [
            "atypical_combination",
            "remote_association",
            "novelty_convention_balance",
        ],
        "implemented_metrics": [
            "info_novelty",
            "atypical_combination",
            "remote_association_index",
            "novelty_convention_balance",
        ],
    },
    "testability": {
        "primary_metric": "Testability",
        "definition": (
            "Measures whether the hypothesis can be operationalized into observable, "
            "measurable, falsifiable validation tasks."
        ),
        "subdimensions": [
            "specificity",
            "measurability",
            "falsifiability",
            "validation_design_clarity",
        ],
        "implemented_metrics": [
            "testability",
        ],
        "implementation_note": (
            "Current PROMPT_TESTABILITY uses specificity, measurability, "
            "falsifiability, and resource_feasibility.  The last field is kept "
            "as a proxy for validation_design_clarity for backward compatibility."
        ),
    },
    "feasibility": {
        "primary_metric": "Feasibility",
        "definition": (
            "Measures whether the hypothesis is realistically executable under "
            "current data, method, resource, and time constraints."
        ),
        "subdimensions": [
            "data_feasibility",
            "method_feasibility",
            "resource_feasibility",
            "validation_readiness",
        ],
        "implemented_metrics": [
            "feasibility_data",
            "feasibility_method",
            "feasibility_resource",
            "feasibility_validation",
        ],
    },
}


def _clip01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _to_five_point(value01: float) -> float:
    """Map a normalized [0, 1] value to the reporting scale [1, 5]."""
    return 1.0 + 4.0 * _clip01(value01)


def _metric_value(
    scores: Mapping[str, float],
    level: str,
    name: str,
    invert: bool = False,
) -> float | None:
    key = f"{level}_{name}"

    # Backward-compatible fallbacks:
    # - Older outputs may only have L*_feasibility without the four sub-scores.
    # - Future outputs may rename testability's resource_feasibility proxy.
    fallback_keys = []
    if name.startswith("feasibility_"):
        fallback_keys.append(f"{level}_feasibility")
    if name == "feasibility_validation":
        fallback_keys.append(f"{level}_validation_readiness")
    if name == "testability":
        fallback_keys.append(f"{level}_validation_design_clarity")

    if key not in scores:
        for fallback in fallback_keys:
            if fallback in scores:
                key = fallback
                break
        else:
            return None

    value = float(scores.get(key, 0.0) or 0.0)
    if name in SCALE_10_METRICS or key.endswith("_feasibility"):
        value /= 10.0
    if invert:
        value = 1.0 - value
    return _clip01(value)


def weighted_x5_score(scores: Mapping[str, float], level: str, spec: MetricSpec) -> float:
    total = 0.0
    used = 0.0
    for metric_name, weight, invert in spec:
        value = _metric_value(scores, level, metric_name, invert=invert)
        if value is None:
            continue
        total += value * weight
        used += weight
    return _clip01(total / used) if used else 0.0


def compute_x5_breakdown(
    scores: Mapping[str, float],
    level: str = "L1",
) -> Dict[str, Dict[str, Dict[str, float] | float]]:
    """Compute 1-5 X+5 scores together with 1-5 submetric breakdowns."""
    output: Dict[str, Dict[str, Dict[str, float] | float]] = {}
    for _, metric_key, spec in X5_METRICS:
        submetrics: Dict[str, float] = {}
        for metric_name, _, invert in spec:
            value = _metric_value(scores, level, metric_name, invert=invert)
            if value is None:
                continue
            submetrics[metric_name] = round(_to_five_point(value), 4)
        output[metric_key] = {
            "score": round(_to_five_point(weighted_x5_score(scores, level, spec)), 4),
            "submetrics": submetrics,
        }
    return output


def compute_x5_scores(scores: Mapping[str, float], level: str = "L1") -> Dict[str, float]:
    """Compute the six X+5 aggregate scores for one score dictionary on a 1-5 scale."""
    return {
        metric_key: round(_to_five_point(weighted_x5_score(scores, level, spec)), 4)
        for _, metric_key, spec in X5_METRICS
    }


def build_x5_scores(
    model_overall: Mapping[str, Mapping[str, float]],
    level: str,
) -> Dict[str, Dict[str, float]]:
    """Compute X+5 scores for a model -> fine-grained metrics mapping."""
    return {
        model: compute_x5_scores(scores, level=level)
        for model, scores in sorted(model_overall.items())
    }


def build_x5_scores_by_level(
    model_overall: Mapping[str, Mapping[str, float]],
    levels: Sequence[str] = ("L1", "L2", "L3"),
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Compute X+5 scores for each requested hypothesis level."""
    return {level: build_x5_scores(model_overall, level=level) for level in levels}

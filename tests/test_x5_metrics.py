"""Tests for the X+5 aggregate metric layer."""

from crossdisc_extractor.benchmark.x5_metrics import compute_x5_breakdown, compute_x5_scores


def test_compute_x5_scores_normalizes_and_aggregates_l1():
    scores = {
        "L1_rao_stirling": 0.6,
        "L1_disciplinary_leap_index": 0.4,
        "L1_embedding_bridging": 0.5,
        "L1_consistency_f1": 0.8,
        "L1_chain_coherence": 0.7,
        "L1_causal_direction_accuracy": 0.6,
        "L1_consistency_recall": 0.9,
        "L1_factual_precision": 0.75,
        "L1_concept_f1": 0.5,
        "L1_relation_precision": 0.5,
        "L1_evidence_coverage": 0.4,
        "L1_path_alignment_best": 0.8,
        "L1_hallucination_rate": 0.2,
        "L1_info_novelty": 0.9,
        "L1_atypical_combination": 0.5,
        "L1_remote_association_index": 0.5,
        "L1_novelty_convention_balance": 0.5,
        "L1_testability": 8.0,
        "L1_feasibility_data": 7.0,
        "L1_feasibility_method": 8.0,
        "L1_feasibility_resource": 6.0,
        "L1_feasibility_validation": 9.0,
    }

    x5 = compute_x5_scores(scores, level="L1")

    assert x5["interdisciplinary_integration"] == 3.16
    assert x5["structural_validity"] == 4.04
    assert x5["evidence_groundedness"] == 3.58
    assert x5["novelty"] == 3.8
    assert x5["testability"] == 4.2
    assert x5["feasibility"] == 4.0


def test_feasibility_falls_back_to_legacy_score_when_subscores_missing():
    x5 = compute_x5_scores({"L2_feasibility": 6.5}, level="L2")

    assert x5["feasibility"] == 3.6


def test_hallucination_rate_is_inverted_for_evidence_groundedness():
    low_hallucination = compute_x5_scores(
        {"L3_hallucination_rate": 0.0},
        level="L3",
    )
    high_hallucination = compute_x5_scores(
        {"L3_hallucination_rate": 1.0},
        level="L3",
    )

    assert low_hallucination["evidence_groundedness"] == 5.0
    assert high_hallucination["evidence_groundedness"] == 1.0


def test_compute_x5_breakdown_returns_submetrics_on_one_to_five_scale():
    breakdown = compute_x5_breakdown(
        {
            "L1_feasibility_data": 7.0,
            "L1_feasibility_method": 8.0,
            "L1_feasibility_resource": 6.0,
            "L1_feasibility_validation": 9.0,
        },
        level="L1",
    )

    feasibility = breakdown["feasibility"]
    assert feasibility["score"] == 4.0
    assert feasibility["submetrics"]["feasibility_data"] == 3.8
    assert feasibility["submetrics"]["feasibility_method"] == 4.2
    assert feasibility["submetrics"]["feasibility_resource"] == 3.4
    assert feasibility["submetrics"]["feasibility_validation"] == 4.6

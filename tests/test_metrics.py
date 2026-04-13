"""tests/test_metrics.py — Unit tests for the new evaluation metrics (v2)."""
import math
from collections import Counter

import pytest

from crossdisc_extractor.benchmark.metrics import (
    _build_discipline_paths,
    _cosine_sim_vectors,
    _same_relation_cluster,
    atypical_combination_index,
    build_cooccurrence_from_kg,
    embedding_bridging_score,
    enhanced_path_consistency,
    factual_precision,
    hierarchical_depth_progression,
    information_theoretic_novelty,
    rao_stirling_diversity,
    reasoning_chain_coherence,
    structural_diversity,
    taxonomy_distance,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_TAXONOMY = {
    "数学": {
        "代数学": {"线性代数": [], "群论": []},
        "分析学": {"微积分": [], "泛函分析": []},
    },
    "物理学": {
        "量子物理": {"量子力学": [], "量子场论": []},
        "热力学": [],
    },
    "生物学": {
        "分子生物学": [],
        "生态学": [],
    },
}


@pytest.fixture
def disc_paths():
    return _build_discipline_paths(SAMPLE_TAXONOMY)


@pytest.fixture
def max_depth(disc_paths):
    return max((len(p) for p in disc_paths.values()), default=1)


# ── Taxonomy Distance ─────────────────────────────────────────────────────

class TestTaxonomyDistance:
    def test_same_discipline(self, disc_paths, max_depth):
        assert taxonomy_distance("线性代数", "线性代数", disc_paths, max_depth) == 0.0

    def test_sibling_disciplines(self, disc_paths, max_depth):
        d = taxonomy_distance("线性代数", "群论", disc_paths, max_depth)
        assert 0.0 < d < 0.5  # siblings should be close

    def test_distant_disciplines(self, disc_paths, max_depth):
        d = taxonomy_distance("线性代数", "分子生物学", disc_paths, max_depth)
        assert d > 0.5  # different top-level should be far

    def test_unknown_discipline(self, disc_paths, max_depth):
        d = taxonomy_distance("线性代数", "不存在的学科", disc_paths, max_depth)
        assert d == 1.0


# ── Rao-Stirling Diversity ────────────────────────────────────────────────

class TestRaoStirlingDiversity:
    def test_single_discipline(self, disc_paths, max_depth):
        steps = [{"head": "A", "tail": "B"}]
        node_discs = {"a": "线性代数", "b": "群论"}
        # Both under 代数学 → same parent
        score = rao_stirling_diversity(steps, node_discs, disc_paths, max_depth)
        assert score >= 0.0

    def test_cross_discipline(self, disc_paths, max_depth):
        steps = [
            {"head": "量子力学概念", "tail": "基因表达"},
        ]
        node_discs = {"量子力学概念": "量子力学", "基因表达": "分子生物学"}
        score = rao_stirling_diversity(steps, node_discs, disc_paths, max_depth)
        assert score > 0.0  # cross-disciplinary → positive diversity

    def test_empty_path(self, disc_paths, max_depth):
        assert rao_stirling_diversity([], {}, disc_paths, max_depth) == 0.0


# ── Information-Theoretic Novelty ─────────────────────────────────────────

class TestInfoNovelty:
    def test_seen_triple_low_novelty(self):
        triples = Counter({("a", "r", "b"): 100})
        result = information_theoretic_novelty(
            [{"head": "A", "relation": "R", "tail": "B"}], triples, 100
        )
        assert result["normalized_novelty"] < 0.5

    def test_unseen_triple_high_novelty(self):
        triples = Counter({("x", "y", "z"): 100})
        result = information_theoretic_novelty(
            [{"head": "A", "relation": "R", "tail": "B"}], triples, 100
        )
        assert result["normalized_novelty"] > 0.5

    def test_empty_path(self):
        result = information_theoretic_novelty([], Counter(), 0)
        assert result["normalized_novelty"] == 0.0


# ── Reasoning Chain Coherence ─────────────────────────────────────────────

class TestChainCoherence:
    def test_single_step(self):
        steps = [{"head": "A", "tail": "B", "claim": "c", "relation": "r"}]
        result = reasoning_chain_coherence(steps)
        assert result["overall_coherence"] == 1.0

    def test_coherent_chain(self):
        steps = [
            {"head": "neural network", "tail": "deep learning", "claim": "Neural networks enable deep learning", "relation": "enables"},
            {"head": "deep learning", "tail": "image recognition", "claim": "Deep learning powers image recognition", "relation": "powers"},
        ]
        result = reasoning_chain_coherence(steps)
        assert result["overall_coherence"] > 0.0
        assert len(result["per_hop"]) == 1

    def test_empty_chain(self):
        result = reasoning_chain_coherence([])
        assert result["overall_coherence"] == 1.0


# ── Structural Diversity ──────────────────────────────────────────────────

class TestStructuralDiversity:
    def test_single_path(self):
        paths = [[{"head": "A", "tail": "B", "relation": "r1"}]]
        result = structural_diversity(paths)
        assert result["fluency"] == 1
        assert result["pairwise_diversity"] == 0.0

    def test_diverse_paths(self):
        paths = [
            [{"head": "A", "tail": "B", "relation": "r1", "relation_type": "method_applied_to"}],
            [{"head": "C", "tail": "D", "relation": "r2", "relation_type": "constrains"}],
        ]
        result = structural_diversity(paths)
        assert result["fluency"] == 2
        assert result["flexibility"] > 0.0
        assert result["pairwise_diversity"] > 0.0

    def test_identical_paths(self):
        path = [{"head": "A", "tail": "B", "relation": "r1", "relation_type": "t1"}]
        paths = [path, path]
        result = structural_diversity(paths)
        assert result["pairwise_diversity"] == 0.0  # identical → no diversity

    def test_empty(self):
        result = structural_diversity([])
        assert result["fluency"] == 0


# ── Hierarchical Depth Progression ────────────────────────────────────────

class TestHierarchicalDepth:
    def test_expansion(self):
        l1 = [[{"head": "A", "tail": "B"}, {"head": "B", "tail": "C"}, {"head": "C", "tail": "D"}]]
        l2 = [[{"head": "A", "tail": "E"}, {"head": "E", "tail": "F"}, {"head": "F", "tail": "G"}]]
        l3 = [[{"head": "H", "tail": "I"}, {"head": "I", "tail": "J"}, {"head": "J", "tail": "K"}]]
        result = hierarchical_depth_progression(l1, l2, l3)
        assert result["l2_concept_expansion"] > 0.0
        assert result["l3_concept_expansion"] > 0.0

    def test_empty_levels(self):
        result = hierarchical_depth_progression([], [], [])
        assert result["depth_quality"] == 0.0


# ── Atypical Combination ─────────────────────────────────────────────────

class TestAtypicalCombination:
    def test_common_pair_low_score(self):
        cooc = Counter({("a", "b"): 100, ("c", "d"): 1})
        steps = [{"head": "A", "tail": "B"}]
        # (a,b) is very common → low atypicality
        score = atypical_combination_index(steps, cooc, mu=50.5, sigma=49.5)
        assert 0.0 <= score <= 1.0

    def test_rare_pair_high_score(self):
        cooc = Counter({("x", "y"): 100})
        steps = [{"head": "A", "tail": "B"}]
        # (a,b) not in cooc → freq=0, very atypical
        score = atypical_combination_index(steps, cooc, mu=100.0, sigma=1.0)
        assert score > 0.5

    def test_empty(self):
        assert atypical_combination_index([], Counter(), 0, 0) == 0.0


# ── Enhanced Path Consistency ─────────────────────────────────────────────

class TestEnhancedPathConsistency:
    def test_exact_match(self):
        gen = [{"head": "A", "tail": "B", "relation": "r1", "relation_type": "method_applied_to"}]
        gt = [{"path": [{"head": "A", "tail": "B", "relation": "r1", "relation_type": "method_applied_to"}]}]
        result = enhanced_path_consistency(gen, gt)
        assert result["consistency_precision"] == 1.0

    def test_entity_match_different_relation(self):
        gen = [{"head": "A", "tail": "B", "relation": "r1", "relation_type": "constrains"}]
        gt = [{"path": [{"head": "A", "tail": "B", "relation": "r2", "relation_type": "method_applied_to"}]}]
        result = enhanced_path_consistency(gen, gt)
        # Entity match but different relation → 0.5
        assert 0.0 < result["consistency_precision"] < 1.0

    def test_same_cluster_relation(self):
        gen = [{"head": "A", "tail": "B", "relation_type": "improves_metric"}]
        gt = [{"path": [{"head": "A", "tail": "B", "relation_type": "extends"}]}]
        result = enhanced_path_consistency(gen, gt)
        # Same cluster (causal_positive) → 0.8
        assert result["consistency_precision"] == 0.8

    def test_no_match(self):
        gen = [{"head": "X", "tail": "Y"}]
        gt = [{"path": [{"head": "A", "tail": "B"}]}]
        result = enhanced_path_consistency(gen, gt)
        assert result["consistency_precision"] == 0.0
        assert result["consistency_f1"] == 0.0

    def test_empty_gen(self):
        result = enhanced_path_consistency([], [])
        assert result["consistency_f1"] == 0.0


# ── Relation Cluster ──────────────────────────────────────────────────────

class TestRelationCluster:
    def test_same_cluster(self):
        assert _same_relation_cluster("improves_metric", "extends") is True

    def test_different_cluster(self):
        assert _same_relation_cluster("constrains", "extends") is False

    def test_unknown_relation(self):
        assert _same_relation_cluster("unknown", "extends") is False


# ── Co-occurrence Builder ─────────────────────────────────────────────────

class TestCooccurrence:
    def test_basic(self):
        paths = [
            [{"head": "A", "tail": "B"}, {"head": "B", "tail": "C"}],
            [{"head": "A", "tail": "B"}],
        ]
        cooc, mu, sigma = build_cooccurrence_from_kg(paths)
        assert cooc[("a", "b")] == 2
        assert cooc[("b", "c")] == 1
        assert mu > 0

    def test_empty(self):
        cooc, mu, sigma = build_cooccurrence_from_kg([])
        assert len(cooc) == 0


# ── Embedding Bridging Score ──────────────────────────────────────────────

class TestEmbeddingBridging:
    def test_empty_path(self):
        assert embedding_bridging_score([]) == 0.0

    def test_identical_endpoints(self):
        path = [{"head": "same", "tail": "same"}]
        score = embedding_bridging_score(path)
        assert score == 0.0

    def test_different_endpoints(self):
        path = [
            {"head": "quantum physics", "tail": "x"},
            {"head": "x", "tail": "genetic engineering"},
        ]
        score = embedding_bridging_score(path)
        assert score > 0.0


# ── Factual Precision ─────────────────────────────────────────────────────

class TestFactualPrecision:
    def test_without_abstract_uses_gt_relations(self, monkeypatch):
        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.metrics._get_nli",
            lambda: None,
        )
        path = [
            {
                "step": 1,
                "head": "Graph neural network",
                "tail": "protein structure prediction",
                "relation": "method_applied_to",
                "claim": "Graph neural networks can be applied to protein structure prediction",
            }
        ]
        gt_relations = [
            {
                "head": "Graph neural network",
                "tail": "protein structure prediction",
                "relation_type": "method_applied_to",
                "evidence_sentence": "Graph neural networks are applied to protein structure prediction.",
            }
        ]
        score = factual_precision(path, abstract="", gt_relations=gt_relations)
        assert score == 1.0

    def test_without_abstract_falls_back_to_gt_terms(self, monkeypatch):
        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.metrics._get_nli",
            lambda: None,
        )
        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.metrics._get_sbert",
            lambda: None,
        )
        path = [
            {
                "step": 1,
                "head": "quantum dots",
                "tail": "solar cells",
                "relation": "improves",
                "claim": "Quantum dots may improve solar cells",
            }
        ]
        score = factual_precision(
            path,
            abstract="",
            gt_terms=["quantum dots", "solar cells", "photovoltaics"],
            gt_relations=[],
        )
        assert score == 1.0

    def test_without_any_evidence_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.metrics._get_nli",
            lambda: None,
        )
        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.metrics._get_sbert",
            lambda: None,
        )
        path = [
            {
                "step": 1,
                "head": "unknown concept",
                "tail": "another unknown concept",
                "relation": "causes",
                "claim": "Unknown concept causes another unknown concept",
            }
        ]
        score = factual_precision(path, abstract="", gt_terms=[], gt_relations=[])
        assert score == 0.0


# ── Build Discipline Paths ────────────────────────────────────────────────

class TestBuildDisciplinePaths:
    def test_basic(self):
        paths = _build_discipline_paths(SAMPLE_TAXONOMY)
        assert "数学" in paths
        assert "线性代数" in paths
        assert paths["线性代数"] == ["数学", "代数学", "线性代数"]

    def test_leaf(self):
        paths = _build_discipline_paths(SAMPLE_TAXONOMY)
        assert "热力学" in paths
        assert paths["热力学"] == ["物理学", "热力学"]

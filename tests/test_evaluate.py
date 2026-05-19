"""tests/test_evaluate.py - 评测模块单元测试"""
import pytest
from crossdisc_extractor.benchmark.evaluate_benchmark import (
    GraphMetricEvaluator,
    GlobalKG,
    _path_hash,
    _tokenize_for_bridging,
    evaluate_single_path,
    normalize_paths_structure,
    parse_llm_score,
)


class TestTokenizeForBridging:
    def test_english_words(self):
        tokens = _tokenize_for_bridging("neural network")
        assert "neural" in tokens or "network" in tokens

    def test_chinese_non_empty(self):
        tokens = _tokenize_for_bridging("神经网络")
        assert len(tokens) > 0

    def test_mixed_language(self):
        tokens = _tokenize_for_bridging("deep学习模型")
        assert "deep" in tokens
        assert len(tokens) >= 2

    def test_empty_string(self):
        tokens = _tokenize_for_bridging("")
        assert len(tokens) == 0


class TestPathHash:
    def test_same_path_same_hash(self):
        path = [{"step": 1, "head": "A", "tail": "B"}]
        assert _path_hash(path) == _path_hash(path)

    def test_different_paths_different_hash(self):
        path1 = [{"step": 1, "head": "A", "tail": "B"}]
        path2 = [{"step": 1, "head": "X", "tail": "Y"}]
        assert _path_hash(path1) != _path_hash(path2)

    def test_hash_is_string(self):
        assert isinstance(_path_hash([]), str)


class TestGraphMetricEvaluator:
    def _make_path(self, head, mid, tail):
        return [
            {"step": 1, "head": head, "relation": "r", "tail": mid, "claim": "c"},
            {"step": 2, "head": mid, "relation": "r", "tail": tail, "claim": "c"},
            {"step": 3, "head": tail, "relation": "r", "tail": "Z", "claim": "final"},
        ]

    # ── calculate_bridging_score ──────────────────────────────────────────────

    def test_bridging_empty_path(self):
        assert GraphMetricEvaluator.calculate_bridging_score([]) == 0.0

    def test_bridging_identical_endpoints(self):
        path = [
            {"step": 1, "head": "量子力学", "tail": "量子力学", "claim": "c"},
        ]
        score = GraphMetricEvaluator.calculate_bridging_score(path)
        assert score == 0.0  # 完全相同 → 距离为 0

    def test_bridging_different_disciplines(self):
        """跨学科路径：首尾差异大，分数应偏高"""
        path = [
            {"step": 1, "head": "量子纠缠", "tail": "X", "claim": "c"},
            {"step": 2, "head": "X", "tail": "基因组学", "claim": "final"},
        ]
        score = GraphMetricEvaluator.calculate_bridging_score(path)
        assert score > 0.5

    def test_bridging_chinese_aware(self):
        """验证中文字符被正确分词（非 \\w+ 整词匹配）"""
        # "量子力学" vs "分子生物学"：有公共字"学"，但应识别为不同领域
        path = [
            {"step": 1, "head": "量子力学", "tail": "X", "claim": "c"},
            {"step": 2, "head": "X", "tail": "分子生物学", "claim": "final"},
        ]
        score = GraphMetricEvaluator.calculate_bridging_score(path)
        assert 0.0 < score <= 1.0

    # ── calculate_path_consistency ────────────────────────────────────────────

    def test_consistency_empty(self):
        assert GraphMetricEvaluator.calculate_path_consistency([], []) == 0.0

    def test_consistency_full_match(self):
        gen = [{"head": "A", "tail": "B"}, {"head": "B", "tail": "C"}]
        gt = [{"path": [{"head": "A", "tail": "B"}, {"head": "B", "tail": "C"}]}]
        score = GraphMetricEvaluator.calculate_path_consistency(gen, gt)
        assert score == 1.0

    def test_consistency_no_match(self):
        gen = [{"head": "X", "tail": "Y"}]
        gt = [{"path": [{"head": "A", "tail": "B"}]}]
        score = GraphMetricEvaluator.calculate_path_consistency(gen, gt)
        assert score == 0.0

    def test_consistency_partial_match(self):
        gen = [{"head": "A", "tail": "B"}, {"head": "X", "tail": "Y"}]
        gt = [{"path": [{"head": "A", "tail": "B"}]}]
        score = GraphMetricEvaluator.calculate_path_consistency(gen, gt)
        assert 0.0 < score < 1.0


class TestNormalizePathsStructure:
    def test_nested_list_passthrough(self):
        nested = [[{"step": 1}], [{"step": 1}]]
        result = normalize_paths_structure(nested)
        assert result == nested

    def test_flat_list_regrouped(self):
        flat = [
            {"step": 1, "head": "A"},
            {"step": 2, "head": "B"},
            {"step": 3, "head": "C"},
            {"step": 1, "head": "D"},
            {"step": 2, "head": "E"},
            {"step": 3, "head": "F"},
        ]
        result = normalize_paths_structure(flat)
        assert len(result) == 2
        assert result[0][0]["head"] == "A"
        assert result[1][0]["head"] == "D"

    def test_empty_returns_empty(self):
        assert normalize_paths_structure([]) == []


class TestParseLlmScore:
    def test_parse_default_scores(self):
        resp = '{"innovation_score": 7.5, "feasibility_score": 6.0, "scientificity_score": 8.0}'
        parsed = parse_llm_score(resp)
        assert parsed["innovation"] == 7.5
        assert parsed["feasibility"] == 6.0
        assert parsed["scientificity"] == 8.0

    def test_parse_feasibility_subscores(self):
        resp = (
            '{"data_feasibility": 7.0, "method_feasibility": 6.5, '
            '"resource_feasibility": 5.0, "validation_readiness": 8.0}'
        )
        parsed = parse_llm_score(
            resp,
            fields=[
                "data_feasibility",
                "method_feasibility",
                "resource_feasibility",
                "validation_readiness",
            ],
        )
        assert parsed["data_feasibility"] == 7.0
        assert parsed["method_feasibility"] == 6.5
        assert parsed["resource_feasibility"] == 5.0
        assert parsed["validation_readiness"] == 8.0


class TestEvaluateSinglePathOptimization:
    def test_x5_only_skips_legacy_outputs(self, monkeypatch):
        def fake_chat_completion(messages, temperature=0.0):
            return (
                '{"data_feasibility": 7.0, "method_feasibility": 6.5, '
                '"resource_feasibility": 6.0, "validation_readiness": 8.0, '
                '"specificity": 7.0, "measurability": 7.5, '
                '"falsifiability": 8.0}'
            )

        monkeypatch.setattr(
            "crossdisc_extractor.benchmark.evaluate_benchmark.chat_completion_with_retry",
            fake_chat_completion,
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
        gt_paths = [{"path": path}]
        gt_relations = [
            {
                "head": "Graph neural network",
                "tail": "protein structure prediction",
                "relation_type": "method_applied_to",
                "evidence_sentence": "Graph neural networks are applied to protein structure prediction.",
            }
        ]

        scores = evaluate_single_path(
            path,
            gt_paths,
            query="protein structure prediction",
            discipline="计算机科学技术",
            level="L1",
            gt_terms=["Graph neural network", "protein structure prediction"],
            gt_relations=gt_relations,
            gt_evidence_paths=gt_paths,
            abstract="Graph neural networks are applied to protein structure prediction.",
            fast_mode=True,
            x5_only=True,
            include_legacy_llm_judge=False,
        )

        assert "innovation" not in scores
        assert "scientificity" not in scores
        assert "legacy_feasibility" not in scores
        assert "consistency" not in scores
        assert "concept_precision" not in scores
        assert "concept_recall" not in scores
        assert "path_alignment_mean" not in scores
        assert "concept_f1" in scores
        assert "path_alignment_best" in scores
        assert "feasibility" in scores
        assert "testability" in scores


class TestGlobalKGReferenceSource:
    def test_default_loads_evidence_paths_not_legacy(self, tmp_path):
        benchmark = [
            {
                "id": "paper-1",
                "input": {
                    "title": "Paper 1",
                    "primary_discipline": "计算机科学技术",
                    "abstract": "A evidence B.",
                },
                "ground_truth": {
                    "terms": [
                        {"normalized": "Evidence A", "discipline": "计算机科学技术"},
                        {"normalized": "Evidence B", "discipline": "生物学"},
                    ],
                    "paths": [
                        {
                            "path": [
                                {
                                    "step": 1,
                                    "head": "Evidence A",
                                    "relation_type": "method_applied_to",
                                    "relation": "method_applied_to",
                                    "tail": "Evidence B",
                                    "evidence": "A evidence B.",
                                    "support_level": "direct",
                                }
                            ],
                            "support_level": "direct",
                        }
                    ],
                    "hypothesis_paths": {
                        "L1": [[{"step": 1, "head": "Legacy A", "relation": "r", "tail": "Legacy B"}]],
                        "L2": [],
                        "L3": [],
                    },
                },
            }
        ]
        path = tmp_path / "benchmark.json"
        path.write_text(__import__("json").dumps(benchmark, ensure_ascii=False), encoding="utf-8")

        kg = GlobalKG(str(path))

        assert kg.total_triples == 1
        assert ("evidence a", "method_applied_to", "evidence b") in kg.all_triples
        assert ("legacy a", "r", "legacy b") not in kg.all_triples

    def test_legacy_reference_requires_explicit_allow(self, tmp_path):
        benchmark = [{"id": "paper-1", "input": {}, "ground_truth": {"hypothesis_paths": {}}}]
        path = tmp_path / "benchmark.json"
        path.write_text(__import__("json").dumps(benchmark), encoding="utf-8")

        with pytest.raises(ValueError):
            GlobalKG(str(path), reference_source="legacy_llm")

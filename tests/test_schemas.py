"""tests/test_schemas.py - schemas 核心逻辑单元测试"""
import pytest
from crossdisc_extractor.schemas import (
    normalize_relation_type,
    _semantic_chain_match,
    HypothesisStep,
    Hypothesis3Levels,
    ConceptEntry,
    Concepts,
    RelationEntry,
)


# ── normalize_relation_type ────────────────────────────────────────────────────

class TestNormalizeRelationType:
    def test_exact_match_returned_as_is(self):
        assert normalize_relation_type("method_applied_to") == "method_applied_to"
        assert normalize_relation_type("maps_to") == "maps_to"
        assert normalize_relation_type("other") == "other"

    def test_english_variant_mapped(self):
        assert normalize_relation_type("used_for") == "method_applied_to"
        assert normalize_relation_type("applies_to") == "method_applied_to"
        assert normalize_relation_type("mapped_to") == "maps_to"
        assert normalize_relation_type("requires") == "depends_on"
        assert normalize_relation_type("builds_on") == "extends"

    def test_chinese_keyword_mapped(self):
        assert normalize_relation_type("用于预测") == "method_applied_to"
        assert normalize_relation_type("显著提升了准确率") == "improves_metric"
        assert normalize_relation_type("映射到特征空间") == "maps_to"
        assert normalize_relation_type("依赖于先验知识") == "depends_on"

    def test_unknown_returns_none(self):
        assert normalize_relation_type("xyz_completely_unknown_relation") is None

    def test_empty_and_none_return_none(self):
        assert normalize_relation_type("") is None
        assert normalize_relation_type(None) is None

    def test_whitespace_stripped(self):
        assert normalize_relation_type("  method_applied_to  ") == "method_applied_to"
        assert normalize_relation_type("  used_for  ") == "method_applied_to"


# ── _semantic_chain_match ──────────────────────────────────────────────────────

class TestSemanticChainMatch:
    def test_exact_match(self):
        ok, sim = _semantic_chain_match("神经网络", "神经网络")
        assert ok is True
        assert sim == 1.0

    def test_case_insensitive(self):
        ok, sim = _semantic_chain_match("Neural Network", "neural network")
        assert ok is True

    def test_near_match_passes(self):
        # "深度神经网络" vs "神经网络"：相似度应 >= 0.75
        ok, sim = _semantic_chain_match("深度神经网络", "神经网络")
        assert ok is True
        assert 0.0 < sim < 1.0

    def test_unrelated_fails(self):
        ok, sim = _semantic_chain_match("量子力学", "基因组学")
        assert ok is False

    def test_empty_strings(self):
        ok, sim = _semantic_chain_match("", "")
        assert ok is True  # 空字符串精确相等


# ── HypothesisStep ─────────────────────────────────────────────────────────────

class TestHypothesisStep:
    def test_valid_step(self):
        s = HypothesisStep(step=1, head="A", relation="r", tail="B", claim="c")
        assert s.step == 1

    def test_zero_step_raises(self):
        with pytest.raises(Exception):
            HypothesisStep(step=0, head="A", relation="r", tail="B", claim="c")

    def test_fields_stripped(self):
        s = HypothesisStep(step=1, head="  A  ", relation="r", tail="B ", claim="c")
        assert s.head == "A"
        assert s.tail == "B"


# ── Hypothesis3Levels ──────────────────────────────────────────────────────────

def _make_valid_path(head="概念A", mid="概念B", tail="概念C"):
    """构造一条合法的 3-step 路径"""
    return [
        HypothesisStep(step=1, head=head, relation="r1", tail=mid, claim="c1"),
        HypothesisStep(step=2, head=mid, relation="r2", tail=tail, claim="c2"),
        HypothesisStep(step=3, head=tail, relation="r3", tail="概念D", claim="最终假设陈述"),
    ]


class TestHypothesis3LevelsValidation:
    def test_valid_one_path_accepted(self):
        path = _make_valid_path()
        h = Hypothesis3Levels(一级=[path], 一级总结=["总结1"])
        assert len(h.一级) == 1

    def test_chain_break_raises(self):
        """step1.tail != step2.head → 应报错"""
        broken = [
            HypothesisStep(step=1, head="A", relation="r1", tail="B", claim="c1"),
            HypothesisStep(step=2, head="X", relation="r2", tail="C", claim="c2"),  # X != B
            HypothesisStep(step=3, head="C", relation="r3", tail="D", claim="final"),
        ]
        with pytest.raises(Exception, match="链路不一致|相似度"):
            Hypothesis3Levels(一级=[broken], 一级总结=["s"])

    def test_wrong_step_count_raises(self):
        path_2step = _make_valid_path()[:2]
        with pytest.raises(Exception, match="恰好包含 3 个 step"):
            Hypothesis3Levels(一级=[path_2step], 一级总结=["s"])

    def test_wrong_step_numbers_raises(self):
        path_bad_nums = [
            HypothesisStep(step=1, head="A", relation="r", tail="B", claim="c"),
            HypothesisStep(step=2, head="B", relation="r", tail="C", claim="c"),
            HypothesisStep(step=5, head="C", relation="r", tail="D", claim="final"),  # 5 != 3
        ]
        with pytest.raises(Exception, match="step 必须依次为"):
            Hypothesis3Levels(一级=[path_bad_nums], 一级总结=["s"])

    def test_empty_last_claim_raises(self):
        path = [
            HypothesisStep(step=1, head="A", relation="r", tail="B", claim="c"),
            HypothesisStep(step=2, head="B", relation="r", tail="C", claim="c"),
            HypothesisStep(step=3, head="C", relation="r", tail="D", claim=""),  # 空 claim
        ]
        with pytest.raises(Exception, match="claim 不得为空"):
            Hypothesis3Levels(一级=[path], 一级总结=["s"])

    def test_summary_length_mismatch_raises(self):
        """
        summary 长度校验位于 Extraction._check_alignment，而非 Hypothesis3Levels 本身。
        Hypothesis3Levels 接受 summary 数量与路径数不一致的情况；
        Extraction 层才会做严格检查。
        此处验证 Hypothesis3Levels 本身不抛出（符合设计意图）。
        """
        path = _make_valid_path()
        # Hypothesis3Levels 自身不校验 summary 长度，不应 raise
        h = Hypothesis3Levels(一级=[path], 一级总结=["s1", "s2"])
        # summary 被原样保留（清理后）
        assert len(h.一级总结) == 2

    def test_near_synonym_chain_accepted(self):
        """近义词链路应通过（语义相似度匹配）"""
        near = [
            HypothesisStep(step=1, head="深度神经网络", relation="r", tail="神经网络模型", claim="c"),
            HypothesisStep(step=2, head="神经网络", relation="r", tail="C", claim="c"),  # 近义词
            HypothesisStep(step=3, head="C", relation="r", tail="D", claim="最终结论"),
        ]
        # 不应 raise（语义相似度 >= 0.75）
        h = Hypothesis3Levels(一级=[near], 一级总结=["总结"])
        assert len(h.一级) == 1


# ── ConceptEntry ───────────────────────────────────────────────────────────────

class TestConceptEntry:
    def test_valid_entry(self):
        c = ConceptEntry(term="deep learning", evidence="...", source="abstract", confidence=0.9)
        assert c.term == "deep learning"

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            ConceptEntry(term="t", evidence="e", source="s", confidence=1.5)

    def test_fields_trimmed(self):
        c = ConceptEntry(term="  dl  ", evidence="e", source="s", confidence=0.8)
        assert c.term == "dl"

    def test_none_evidence_and_source_are_coerced(self):
        c = ConceptEntry(term="dl", evidence=None, source=None, confidence=0.8)
        assert c.evidence == ""
        assert c.source == "abstract"


class TestSchemaRecovery:
    def test_concepts_aux_group_unwraps_dict_wrapper(self):
        from crossdisc_extractor.schemas import Concepts

        c = Concepts.model_validate(
            {
                "主学科": [],
                "辅学科": {
                    "化学": {
                        "ConceptEntry": [
                            {"term": "catalyst", "evidence": None, "source": None, "confidence": 0.8}
                        ]
                    }
                },
            }
        )
        assert len(c.辅学科["化学"]) == 1
        assert c.辅学科["化学"][0].source == "abstract"

    def test_relation_direction_is_normalized(self):
        r = RelationEntry(
            head="a",
            relation="rel",
            relation_type="other",
            tail="b",
            direction="<-",
            evidence=None,
            source=None,
            confidence=0.8,
        )
        assert r.direction == "->"
        assert r.source == "abstract"

    def test_classified_bucket_fills_missing_rationale(self):
        from crossdisc_extractor.schemas import ClassifiedBucket

        bucket = ClassifiedBucket.model_validate({"概念": ["x", "y"], "关系": [0, 1]})
        assert bucket.rationale

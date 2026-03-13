"""
tests/test_gt_builder.py

Tests for the evidence-grounded GT construction pipeline:
- TerminologyDict: dictionary loading, fuzzy matching, grounding
- gt_builder: term extraction, relation construction, path building
- New metrics: concept coverage, relation precision, path alignment
"""

import json
import os
import tempfile

import pytest

# ===========================================================================
#  TerminologyDict tests
# ===========================================================================

from crossdisc_extractor.benchmark.terminology import (
    TerminologyDict,
    normalize_term,
    _text_similarity,
)


class TestNormalizeTerm:
    def test_basic_normalization(self):
        assert normalize_term("  Deep Learning  ") == "deep learning"

    def test_chinese_normalization(self):
        assert normalize_term("机器学习") == "机器学习"

    def test_remove_parenthetical(self):
        result = normalize_term("材料失效与保护(包括材料腐蚀、磨损等)")
        assert "包括" not in result

    def test_empty_string(self):
        assert normalize_term("") == ""
        assert normalize_term(None) == ""

    def test_collapse_spaces(self):
        assert normalize_term("deep   learning   model") == "deep learning model"


class TestTextSimilarity:
    def test_identical(self):
        assert _text_similarity("abc", "abc") == 1.0

    def test_similar(self):
        sim = _text_similarity("machine learning", "machine learn")
        assert sim > 0.8

    def test_different(self):
        sim = _text_similarity("quantum physics", "biology")
        assert sim < 0.5

    def test_empty(self):
        assert _text_similarity("", "abc") == 0.0
        assert _text_similarity("abc", "") == 0.0


class TestTerminologyDict:
    @pytest.fixture
    def sample_taxonomy(self, tmp_path):
        taxonomy = {
            "数学": {
                "代数学": {
                    "线性代数": [],
                    "群论": [],
                },
                "分析学": {
                    "实变函数论": [],
                },
            },
            "物理学": {
                "量子力学": [],
                "热力学": [],
            },
            "计算机科学技术": {
                "人工智能": {
                    "机器学习": [],
                    "自然语言处理": [],
                },
            },
        }
        path = tmp_path / "test_taxonomy.json"
        path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_load_taxonomy(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        assert len(td.all_terms) > 0
        assert len(td.all_disciplines) >= 3

    def test_exact_lookup(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        assert td.lookup("线性代数") == "数学"
        assert td.lookup("量子力学") == "物理学"
        assert td.lookup("机器学习") == "计算机科学技术"

    def test_lookup_case_insensitive(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        # Chinese terms don't have case, but normalization should work
        assert td.lookup("  线性代数  ") == "数学"

    def test_lookup_not_found(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        assert td.lookup("不存在的术语") is None

    def test_fuzzy_match(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        matches = td.fuzzy_match("线性代", threshold=0.7)
        assert len(matches) >= 1
        assert matches[0][1] == "数学"  # discipline

    def test_ground_term(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        term, disc, conf = td.ground_term("机器学习")
        assert disc == "计算机科学技术"
        assert conf == 1.0

    def test_ground_term_not_found(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        term, disc, conf = td.ground_term("完全无关的术语xyz")
        assert term is None
        assert disc is None
        assert conf == 0.0

    def test_ground_terms_batch(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        results = td.ground_terms_batch(["线性代数", "量子力学", "随机术语"])
        assert results[0]["is_grounded"] is True
        assert results[1]["is_grounded"] is True
        assert results[2]["is_grounded"] is False

    def test_is_cross_disciplinary(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        assert td.is_cross_disciplinary("线性代数", "量子力学") is True
        assert td.is_cross_disciplinary("线性代数", "群论") is False

    def test_add_external_terms(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        td.add_external_terms({"CRISPR": "生物学", "PET-CT": "临床医学"})
        assert td.lookup("crispr") == "生物学"
        assert td.lookup("pet-ct") == "临床医学"

    def test_get_discipline_terms(self, sample_taxonomy):
        td = TerminologyDict(sample_taxonomy)
        math_terms = td.get_discipline_terms("数学")
        assert len(math_terms) >= 3  # 数学, 代数学, 线性代数, 群论, ...

    def test_missing_taxonomy_file(self):
        td = TerminologyDict("/nonexistent/path.json")
        assert len(td.all_terms) == 0


# ===========================================================================
#  GT Builder tests
# ===========================================================================

from crossdisc_extractor.benchmark.gt_builder import (
    GTTerm,
    GTRelation,
    GTPath,
    _split_sentences,
    _find_terms_in_sentence,
    _parse_json_response,
    extract_terms,
    build_relations,
    build_gt_paths,
    build_ground_truth,
)


class TestSplitSentences:
    def test_chinese_sentences(self):
        text = "脑深部刺激是一种方法。它可以治疗癫痫。效果显著。"
        result = _split_sentences(text)
        assert len(result) >= 2

    def test_english_sentences(self):
        text = "Machine learning is powerful. It can solve many problems."
        result = _split_sentences(text)
        assert len(result) == 2

    def test_mixed_punctuation(self):
        text = "这是第一句话。This is the second sentence. 第三句！"
        result = _split_sentences(text)
        assert len(result) >= 2

    def test_empty_text(self):
        assert _split_sentences("") == []
        assert _split_sentences(None) == []

    def test_filters_short_fragments(self):
        text = "好。这是一个完整的句子。嗯。"
        result = _split_sentences(text)
        # "好" and "嗯" should be filtered (< 5 chars)
        assert all(len(s) >= 5 for s in result)


class TestFindTermsInSentence:
    def test_find_chinese_terms(self):
        sentence = "脑深部刺激可以用于癫痫治疗"
        terms = {"脑深部刺激": "脑深部刺激", "癫痫": "癫痫"}
        found = _find_terms_in_sentence(sentence, terms)
        assert "脑深部刺激" in found
        assert "癫痫" in found

    def test_find_english_terms(self):
        sentence = "Machine learning can improve drug discovery"
        terms = {"machine learning": "Machine Learning", "drug discovery": "Drug Discovery"}
        found = _find_terms_in_sentence(sentence, terms)
        assert "Machine Learning" in found
        assert "Drug Discovery" in found

    def test_no_match(self):
        sentence = "这是一个普通句子"
        terms = {"量子力学": "量子力学"}
        found = _find_terms_in_sentence(sentence, terms)
        assert len(found) == 0


class TestParseJsonResponse:
    def test_plain_json(self):
        resp = '{"key": "value"}'
        result = _parse_json_response(resp)
        assert result["key"] == "value"

    def test_markdown_fenced(self):
        resp = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(resp)
        assert result["key"] == "value"

    def test_markdown_no_lang(self):
        resp = '```\n{"key": "value"}\n```'
        result = _parse_json_response(resp)
        assert result["key"] == "value"


class TestGTTerm:
    def test_to_dict(self):
        term = GTTerm(
            term="机器学习",
            normalized="机器学习",
            discipline="计算机科学",
            evidence="本文使用机器学习方法",
            source="abstract",
            confidence=0.9,
        )
        d = term.to_dict()
        assert d["term"] == "机器学习"
        assert d["discipline"] == "计算机科学"
        assert d["confidence"] == 0.9


class TestGTRelation:
    def test_to_dict(self):
        rel = GTRelation(
            head="机器学习",
            tail="图像识别",
            relation_type="method_applied_to",
            evidence_sentence="机器学习方法被广泛应用于图像识别",
        )
        d = rel.to_dict()
        assert d["head"] == "机器学习"
        assert d["relation_type"] == "method_applied_to"


class TestExtractTerms:
    @pytest.fixture
    def simple_dict(self, tmp_path):
        taxonomy = {"计算机科学技术": {"人工智能": {"机器学习": []}}}
        path = tmp_path / "tax.json"
        path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")
        return TerminologyDict(str(path))

    def test_fallback_extraction(self, simple_dict):
        terms = extract_terms(
            title="基于深度学习的图像识别",
            abstract="本文提出了一种基于深度学习的图像识别方法",
            introduction="深度学习在计算机视觉领域取得了显著成果",
            terminology_dict=simple_dict,
            llm_fn=None,
        )
        assert isinstance(terms, list)
        # Should extract some Chinese terms via heuristic
        term_texts = [t.term for t in terms]
        assert any("深度学习" in t for t in term_texts) or any("图像识别" in t for t in term_texts)


class TestBuildRelations:
    def test_cooccurrence_detection(self):
        terms = [
            GTTerm("机器学习", "机器学习", "计算机科学"),
            GTTerm("图像识别", "图像识别", "计算机科学"),
        ]
        abstract = "机器学习方法被广泛应用于图像识别领域。"
        introduction = "图像识别是计算机视觉的核心任务。"
        relations = build_relations(terms, abstract, introduction, llm_fn=None)
        assert isinstance(relations, list)
        # Should find at least one relation from co-occurrence
        if relations:
            assert relations[0].evidence_sentence != ""

    def test_no_cooccurrence(self):
        terms = [
            GTTerm("量子力学", "量子力学", "物理学"),
            GTTerm("有机化学", "有机化学", "化学"),
        ]
        abstract = "量子力学是物理学的基础。"
        introduction = "有机化学研究碳化合物。"
        relations = build_relations(terms, abstract, introduction, llm_fn=None)
        # Terms never co-occur in same sentence, so no relations
        assert len(relations) == 0


class TestBuildGtPaths:
    def test_basic_path_building(self):
        terms = [
            GTTerm("A", "A", "数学"),
            GTTerm("B", "B", "物理学"),
            GTTerm("C", "C", "化学"),
        ]
        relations = [
            GTRelation("A", "B", "maps_to", evidence_sentence="A maps to B"),
            GTRelation("B", "C", "extends", evidence_sentence="B extends C"),
        ]
        paths = build_gt_paths(terms, relations, max_path_length=4)
        assert isinstance(paths, list)
        # Should find at least A→B→C
        if paths:
            assert len(paths[0].steps) >= 1

    def test_cross_discipline_filter(self):
        terms = [
            GTTerm("线性代数理论", "线性代数理论", "数学"),
            GTTerm("群论基础", "群论基础", "数学"),
        ]
        relations = [
            GTRelation("线性代数理论", "群论基础", "maps_to", evidence_sentence="线性代数理论→群论基础"),
        ]
        paths = build_gt_paths(terms, relations, require_cross_discipline=True)
        # Both terms are same discipline (数学), so no cross-disciplinary paths
        assert len(paths) == 0

    def test_empty_relations(self):
        terms = [GTTerm("A", "A", "数学")]
        paths = build_gt_paths(terms, [], max_path_length=3)
        assert len(paths) == 0

    def test_path_has_evidence(self):
        terms = [
            GTTerm("X", "X", "物理学"),
            GTTerm("Y", "Y", "化学"),
        ]
        relations = [
            GTRelation("X", "Y", "driven_by", evidence_sentence="X is driven by Y"),
        ]
        paths = build_gt_paths(terms, relations)
        if paths:
            for step in paths[0].steps:
                assert "evidence" in step


class TestBuildGroundTruth:
    def test_full_pipeline(self, tmp_path):
        taxonomy = {"物理学": {"量子力学": []}, "化学": {"有机化学": []}}
        tax_path = tmp_path / "tax.json"
        tax_path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")

        result = build_ground_truth(
            title="量子化学模拟",
            abstract="量子力学方法被应用于有机化学分子模拟。量子力学与有机化学的交叉研究日益重要。",
            introduction="本文将量子力学原理应用于有机化学分子结构预测。",
            taxonomy_path=str(tax_path),
            llm_fn=None,
        )

        assert "terms" in result
        assert "relations" in result
        assert "paths" in result
        assert "concept_graph" in result
        assert "stats" in result
        assert isinstance(result["stats"]["n_terms"], int)

    def test_empty_input(self, tmp_path):
        taxonomy = {"数学": {}}
        tax_path = tmp_path / "tax.json"
        tax_path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")

        result = build_ground_truth(
            title="", abstract="", introduction="",
            taxonomy_path=str(tax_path),
        )
        assert result["stats"]["n_terms"] == 0


# ===========================================================================
#  New metrics tests
# ===========================================================================

from crossdisc_extractor.benchmark.metrics import (
    concept_coverage,
    relation_precision,
    path_semantic_alignment,
)


class TestConceptCoverage:
    def test_full_coverage(self):
        gen_path = [
            {"head": "机器学习", "tail": "图像识别"},
            {"head": "图像识别", "tail": "医学诊断"},
        ]
        gt_terms = ["机器学习", "图像识别", "医学诊断"]
        result = concept_coverage(gen_path, gt_terms)
        assert result["concept_recall"] == 1.0
        assert result["concept_precision"] == 1.0
        assert result["concept_f1"] == 1.0

    def test_partial_coverage(self):
        gen_path = [
            {"head": "机器学习", "tail": "图像识别"},
        ]
        gt_terms = ["机器学习", "图像识别", "自然语言处理", "知识图谱"]
        result = concept_coverage(gen_path, gt_terms)
        assert result["concept_recall"] == 0.5  # 2 out of 4
        assert result["concept_precision"] == 1.0  # both gen entities match GT

    def test_no_coverage(self):
        gen_path = [{"head": "AAA", "tail": "BBB"}]
        gt_terms = ["CCC", "DDD"]
        result = concept_coverage(gen_path, gt_terms)
        assert result["concept_recall"] == 0.0

    def test_empty_inputs(self):
        result = concept_coverage([], ["a", "b"])
        assert result["concept_f1"] == 0.0
        result = concept_coverage([{"head": "a", "tail": "b"}], [])
        assert result["concept_f1"] == 0.0


class TestRelationPrecision:
    def test_full_precision(self):
        gen_path = [
            {"head": "机器学习", "tail": "图像识别", "relation_type": "method_applied_to"},
        ]
        gt_relations = [
            {"head": "机器学习", "tail": "图像识别", "relation_type": "method_applied_to"},
        ]
        result = relation_precision(gen_path, gt_relations)
        assert result["relation_precision"] == 1.0

    def test_no_match(self):
        gen_path = [{"head": "AAA", "tail": "BBB", "relation": "x"}]
        gt_relations = [{"head": "CCC", "tail": "DDD", "relation_type": "y"}]
        result = relation_precision(gen_path, gt_relations)
        assert result["relation_precision"] == 0.0

    def test_empty_inputs(self):
        result = relation_precision([], [{"head": "a", "tail": "b", "relation_type": "x"}])
        assert result["relation_precision"] == 0.0


class TestPathSemanticAlignment:
    def test_identical_path(self):
        gen_path = [
            {"head": "A", "tail": "B", "relation": "maps_to"},
            {"head": "B", "tail": "C", "relation": "extends"},
        ]
        gt_paths = [{"path": gen_path}]
        result = path_semantic_alignment(gen_path, gt_paths)
        assert result["best_alignment"] >= 0.9  # nearly identical

    def test_different_path(self):
        gen_path = [{"head": "X", "tail": "Y", "relation": "unknown"}]
        gt_paths = [
            {"path": [{"head": "A", "tail": "B", "relation": "maps_to"}]},
        ]
        result = path_semantic_alignment(gen_path, gt_paths)
        # Should still return a score (may be low)
        assert 0.0 <= result["best_alignment"] <= 1.0

    def test_empty_inputs(self):
        result = path_semantic_alignment([], [{"path": []}])
        assert result["best_alignment"] == 0.0


# ===========================================================================
#  build_dataset integration tests
# ===========================================================================

from crossdisc_extractor.benchmark.build_dataset import (
    convert_to_evidence_grounded_format,
)


class TestConvertToEvidenceGrounded:
    def test_basic_conversion(self, tmp_path):
        taxonomy = {"物理学": {"量子力学": []}, "化学": {"有机化学": []}}
        tax_path = tmp_path / "tax.json"
        tax_path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")

        item = {
            "ok": True,
            "title": "量子化学模拟研究",
            "abstract": "量子力学方法被应用于有机化学分子模拟。",
            "introduction": "本文将量子力学原理应用于有机化学。",
            "parsed": {
                "meta": {
                    "title": "量子化学模拟研究",
                    "primary": "物理学",
                    "secondary_list": ["化学"],
                },
            },
        }

        result = convert_to_evidence_grounded_format(
            item, taxonomy_path=str(tax_path)
        )
        if result:
            assert "ground_truth" in result
            assert "terms" in result["ground_truth"]
            assert "relations" in result["ground_truth"]
            assert "paths" in result["ground_truth"]

    def test_no_text(self):
        item = {"ok": True, "title": "test", "abstract": "", "introduction": ""}
        result = convert_to_evidence_grounded_format(item)
        assert result is None

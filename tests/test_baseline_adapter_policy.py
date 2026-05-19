"""baseline 输入白名单与主假设选择策略测试"""
from baseline.common import PaperInput, get_external_baseline_input
from baseline.evaluate_all import select_primary_hypothesis


def test_external_baseline_input_whitelists_only_text_and_labels():
    paper = PaperInput(
        paper_id="p1",
        title="  Title  ",
        abstract="Abstract text.",
        introduction="Intro text.",
        primary_discipline="计算机科学技术",
        secondary_disciplines=["生物学", " 材料科学 "],
        concepts={"main": ["secret"]},
        relations=[{"head": "A", "tail": "B"}],
        queries={"一级": "hidden"},
    )

    data = get_external_baseline_input(paper)

    assert data.title == "Title"
    assert data.abstract == "Abstract text."
    assert data.introduction == "Intro text."
    assert data.primary_discipline == "计算机科学技术"
    assert data.secondary_disciplines == ("生物学", "材料科学")
    assert data.secondary_text == "生物学, 材料科学"
    assert not hasattr(data, "concepts")
    assert not hasattr(data, "relations")
    assert not hasattr(data, "queries")


def test_select_primary_hypothesis_prefers_first_valid():
    hyps = ["first short", "second hypothesis is much longer and more detailed"]
    assert select_primary_hypothesis(hyps) == "first short"


def test_select_primary_hypothesis_falls_back_to_longest_valid():
    hyps = ["[ERROR] timeout", "ok", "this is the longest valid hypothesis"]
    assert select_primary_hypothesis(hyps) == "this is the longest valid hypothesis"


def test_select_primary_hypothesis_returns_empty_when_no_valid():
    hyps = ["[ERROR] fail", " ", ""]
    assert select_primary_hypothesis(hyps) == ""

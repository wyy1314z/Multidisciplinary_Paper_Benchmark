"""Recovery tests for query prompt parsing."""

from __future__ import annotations

from crossdisc_extractor.config import set_language_mode
from crossdisc_extractor.prompts.query_prompt import parse_query_output


def test_parse_query_output_recovers_missing_rationale():
    text = """
    {
      "按辅助学科分类": {
        "化学": {
          "概念": ["催化剂", "反应位点"],
          "关系": [0, 2]
        }
      },
      "查询": {
        "一级": "如何提升反应效率？",
        "二级": ["化学如何支持反应效率提升？"],
        "三级": ["如何整合化学机制与实验验证形成工作流？"]
      }
    }
    """
    parsed = parse_query_output(text)
    assert "化学" in parsed.按辅助学科分类
    assert parsed.按辅助学科分类["化学"].rationale


def test_parse_query_output_original_mode_keeps_english_query():
    text = """
    {
      "按辅助学科分类": {},
      "查询": {
        "一级": "How can graph neural networks improve protein folding?",
        "二级": ["How can biophysics constrain graph neural networks?"],
        "三级": ["How can graph neural networks and biophysics form a validation workflow?"]
      }
    }
    """
    set_language_mode("original")
    try:
        parsed = parse_query_output(text)
    finally:
        set_language_mode("chinese")

    assert "graph neural networks" in parsed.查询.一级
    assert "biophysics" in parsed.查询.二级[0]

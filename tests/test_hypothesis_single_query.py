"""Tests for per-query hypothesis prompt construction."""

from __future__ import annotations

from crossdisc_extractor.prompts.hypothesis_prompt_split import (
    build_hypothesis_messages_l2_single,
    build_hypothesis_messages_l3_single,
)
from crossdisc_extractor.schemas import Query3Levels, StructExtraction


def _minimal_struct() -> StructExtraction:
    return StructExtraction.model_validate(
        {
            "meta": {
                "title": "t",
                "primary": "生物学",
                "secondary_list": ["化学", "材料科学"],
            },
            "概念": {
                "主学科": [
                    {"term": "细胞", "normalized": "细胞", "evidence": "", "source": "abstract", "confidence": 0.9}
                ],
                "辅学科": {
                    "化学": [
                        {"term": "催化剂", "normalized": "催化剂", "evidence": "", "source": "abstract", "confidence": 0.9}
                    ],
                    "材料科学": [
                        {"term": "纳米材料", "normalized": "纳米材料", "evidence": "", "source": "abstract", "confidence": 0.9}
                    ],
                },
            },
            "跨学科关系": [],
        }
    )


def test_l2_single_query_prompt_contains_only_selected_l2_query():
    query = Query3Levels(
        一级="如何改进生物学目标？",
        二级=["化学如何支持机制刻画？", "材料科学如何支持结构优化？"],
        三级=["如何形成化学验证闭环？", "如何形成材料验证闭环？"],
    )

    user_content = build_hypothesis_messages_l2_single(_minimal_struct(), query, 1)[-1]["content"]

    assert "材料科学如何支持结构优化？" in user_content
    assert "化学如何支持机制刻画？" not in user_content
    assert "假设.二级` 必须恰好包含 1 条路径" in user_content


def test_l3_single_query_prompt_contains_only_selected_l3_query():
    query = Query3Levels(
        一级="如何改进生物学目标？",
        二级=["化学如何支持机制刻画？", "材料科学如何支持结构优化？"],
        三级=["如何形成化学验证闭环？", "如何形成材料验证闭环？"],
    )

    user_content = build_hypothesis_messages_l3_single(_minimal_struct(), query, 0)[-1]["content"]

    assert "如何形成化学验证闭环？" in user_content
    assert "如何形成材料验证闭环？" not in user_content
    assert "化学如何支持机制刻画？" in user_content
    assert "材料科学如何支持结构优化？" not in user_content
    assert "假设.三级` 必须恰好包含 1 条路径" in user_content

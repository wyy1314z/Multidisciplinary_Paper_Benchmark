"""Tests for LLM usage telemetry helpers and summaries."""

from __future__ import annotations

from crossdisc_extractor.utils.usage_telemetry import estimate_messages_tokens, normalize_usage
from scripts.summarize_llm_usage import build_summary


def test_normalize_usage_accepts_openai_style_keys():
    usage = normalize_usage({"input_tokens": 10, "output_tokens": 7, "total_tokens": 17})
    assert usage == {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17}


def test_estimate_messages_tokens_is_positive():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "请总结这篇文章"},
    ]
    assert estimate_messages_tokens(messages, model="qwen3-235b-a22b") > 0


def test_build_usage_summary_aggregates_stage_and_command():
    rows = [
        {
            "stage": "stage1",
            "command": "classify",
            "call_kind": "classifier_ainvoke",
            "model": "model-a",
            "success": True,
            "latency_sec": 1.2,
            "usage_source": "actual",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
        {
            "stage": "stage2",
            "command": "extract",
            "call_kind": "chat_completion",
            "model": "model-a",
            "success": False,
            "latency_sec": 2.0,
            "usage_source": "estimate",
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "total_tokens": 28,
        },
    ]

    summary = build_summary(rows)
    assert summary["overall"]["total_tokens"] == 43
    assert summary["by_stage"]["stage1"]["calls"] == 1
    assert summary["by_stage"]["stage2"]["error_calls"] == 1
    assert summary["largest_token_commands"][0]["command_key"] == "stage2::extract"

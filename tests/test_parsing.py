"""tests/test_parsing.py - JSON 解析工具单元测试"""
import pytest
from crossdisc_extractor.utils.parsing import (
    strip_code_fences,
    coerce_json_object,
    _extract_first_balanced_json_object,
)


class TestStripCodeFences:
    def test_json_fence_removed(self):
        result = strip_code_fences("```json\n{\"a\": 1}\n```")
        assert result == '{"a": 1}'

    def test_plain_fence_removed(self):
        result = strip_code_fences("```\n{\"a\": 1}\n```")
        assert result == '{"a": 1}'

    def test_no_fence_unchanged(self):
        result = strip_code_fences('{"a": 1}')
        assert result == '{"a": 1}'

    def test_whitespace_stripped(self):
        result = strip_code_fences("  \n  {\"a\": 1}  \n  ")
        assert result == '{"a": 1}'


class TestExtractFirstBalancedJsonObject:
    def test_clean_json(self):
        result = _extract_first_balanced_json_object('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_with_surrounding_text(self):
        result = _extract_first_balanced_json_object('some text {"key": "val"} more text')
        assert result == '{"key": "val"}'

    def test_nested_braces(self):
        result = _extract_first_balanced_json_object('{"a": {"b": 1}}')
        assert result == '{"a": {"b": 1}}'

    def test_braces_in_string_ignored(self):
        result = _extract_first_balanced_json_object('{"key": "has { brace }"}')
        assert result == '{"key": "has { brace }"}'

    def test_truncated_returns_none(self):
        result = _extract_first_balanced_json_object('{"key": "value"')
        assert result is None

    def test_no_brace_returns_none(self):
        result = _extract_first_balanced_json_object("no json here")
        assert result is None


class TestCoerceJsonObject:
    def test_clean_json(self):
        result = coerce_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_with_code_fence(self):
        result = coerce_json_object('```json\n{"key": "val"}\n```')
        assert result["key"] == "val"

    def test_chinese_punctuation_normalized(self):
        result = coerce_json_object('{"key"："value"}')  # 中文冒号
        assert result["key"] == "value"

    def test_chinese_comma_normalized(self):
        result = coerce_json_object('{"a": 1，"b": 2}')  # 中文逗号
        assert result["a"] == 1
        assert result["b"] == 2

    def test_with_surrounding_text(self):
        result = coerce_json_object('Here is the result: {"key": "val"} Done.')
        assert result["key"] == "val"

    def test_required_keys_present(self):
        result = coerce_json_object('{"a": 1, "b": 2}', required_top_keys={"a", "b"})
        assert result["a"] == 1

    def test_required_keys_missing_raises(self):
        with pytest.raises(ValueError):
            coerce_json_object('{"a": 1}', required_top_keys={"a", "b"})

    def test_truncated_raises(self):
        with pytest.raises(ValueError, match="截断|JSON"):
            coerce_json_object('{"key": "value"')

    def test_non_string_input_raises(self):
        with pytest.raises(ValueError, match="不是字符串"):
            coerce_json_object(None)

    def test_nested_json(self):
        text = '{"meta": {"title": "T"}, "概念": []}'
        result = coerce_json_object(text)
        assert result["meta"]["title"] == "T"

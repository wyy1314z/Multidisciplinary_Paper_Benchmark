"""Tests for LLM parsing utilities."""

from crossdisc_extractor.classifier.llm.base import BaseLLM

STRICT_REGEX = r"^\[(?:[^\[\]\n,]{1,128})(?:,(?:[^\[\]\n,]{1,128}))*\]$"
BRACKET_REGEX = r"\[([^\[\]\n]*)\]"


class TestParseBracketList:
    def test_strict_format(self):
        result = BaseLLM.parse_bracket_list(
            "[Physics; Math; Biology]", STRICT_REGEX, BRACKET_REGEX
        )
        assert result == ["Physics", "Math", "Biology"]

    def test_loose_format(self):
        result = BaseLLM.parse_bracket_list(
            "The answer is [Physics; Math]", STRICT_REGEX, BRACKET_REGEX
        )
        assert result == ["Physics", "Math"]

    def test_deduplication(self):
        result = BaseLLM.parse_bracket_list(
            "[Physics; physics; Math]", STRICT_REGEX, BRACKET_REGEX
        )
        assert result == ["Physics", "Math"]

    def test_empty_input(self):
        assert BaseLLM.parse_bracket_list("", STRICT_REGEX, BRACKET_REGEX) == []
        assert BaseLLM.parse_bracket_list(None, STRICT_REGEX, BRACKET_REGEX) == []

    def test_term_max_len(self):
        result = BaseLLM.parse_bracket_list(
            "[A very long term]", STRICT_REGEX, BRACKET_REGEX, term_max_len=5
        )
        assert len(result[0]) <= 5

    def test_removes_brackets(self):
        result = BaseLLM.parse_bracket_list(
            "[[Biology]; [Ecology]]", STRICT_REGEX, BRACKET_REGEX
        )
        for item in result:
            assert "[" not in item
            assert "]" not in item

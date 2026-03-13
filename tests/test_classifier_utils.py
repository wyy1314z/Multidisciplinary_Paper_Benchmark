"""Tests for utility functions."""

from crossdisc_extractor.classifier.utils.formatting import format_final_path, format_multiple_paths
from crossdisc_extractor.classifier.utils.parsing import (
    extract_multidisciplinary,
    parse_levels,
    extract_discipline_levels,
    extract_main_discipline,
    levels_from_paths,
)


class TestFormatting:
    def test_format_final_path(self):
        assert format_final_path(["A", "B", "C"]) == "[A; B; C]"

    def test_format_final_path_single(self):
        assert format_final_path(["A"]) == "[A]"

    def test_format_multiple_paths(self):
        paths = [["A", "B"], ["C", "D"]]
        result = format_multiple_paths(paths)
        assert result == "[A; B]\n[C; D]"


class TestParsing:
    def test_extract_multidisciplinary_yes(self):
        raws = ["Some text\nMultidisciplinary: Yes\nMore text"]
        assert extract_multidisciplinary(raws) == "Yes"

    def test_extract_multidisciplinary_no(self):
        raws = ["Multidisciplinary: No"]
        assert extract_multidisciplinary(raws) == "No"

    def test_extract_multidisciplinary_majority_vote(self):
        raws = [
            "Multidisciplinary: Yes",
            "Multidisciplinary: No",
            "Multidisciplinary: Yes",
        ]
        assert extract_multidisciplinary(raws) == "Yes"

    def test_extract_multidisciplinary_unknown(self):
        assert extract_multidisciplinary(["no match here"]) == "Unknown"

    def test_parse_levels(self):
        block = "[[Biology];[Ecology];[Microbiology]]"
        levels = parse_levels(block)
        assert levels == [("1", "Biology"), ("2", "Ecology"), ("3", "Microbiology")]

    def test_parse_levels_two(self):
        block = "[[Pharmacy];[Pharmaceutical Chemistry]]"
        levels = parse_levels(block)
        assert levels == [("1", "Pharmacy"), ("2", "Pharmaceutical Chemistry")]

    def test_extract_main_discipline(self):
        raws = ["Main discipline: [[Math];[Algebra];[Linear Algebra]]"]
        assert "Math" in extract_main_discipline(raws)

    def test_extract_main_discipline_unknown(self):
        assert extract_main_discipline(["no match"]) == "Unknown"

    def test_extract_discipline_levels(self):
        raw = (
            "[[Physics];[Mechanics];[Classical]]\n"
            "[[Math];[Algebra];[Linear]]\n"
            "Multidisciplinary: Yes\n"
            "Main discipline: [[Physics];[Mechanics];[Classical]]"
        )
        main_levels, non_main_levels = extract_discipline_levels([raw])
        assert len(main_levels) > 0
        assert len(non_main_levels) > 0


class TestLevelsFromPaths:
    def test_empty_paths(self):
        main, non_main = levels_from_paths([], [])
        assert main == []
        assert non_main == []

    def test_single_path(self):
        paths = [["生物学", "生物化学", "核酸生物化学"]]
        main, non_main = levels_from_paths(paths, [])
        assert main == [("1", "生物学"), ("2", "生物化学"), ("3", "核酸生物化学")]
        assert non_main == []

    def test_multi_paths_with_main_discipline(self):
        paths = [
            ["生物学", "生物化学", "核酸生物化学"],
            ["计算机科学技术", "人工智能", "深度学习"],
        ]
        raw_outputs = [
            "Multidisciplinary: Yes\n"
            "Main discipline: [[生物学];[生物化学];[核酸生物化学]]"
        ]
        main, non_main = levels_from_paths(paths, raw_outputs)
        assert main == [("1", "生物学"), ("2", "生物化学"), ("3", "核酸生物化学")]
        assert non_main == [("1", "计算机科学技术"), ("2", "人工智能"), ("3", "深度学习")]

    def test_multi_paths_main_is_second(self):
        paths = [
            ["数学", "代数学", "线性代数"],
            ["物理学", "理论物理", "量子力学"],
        ]
        raw_outputs = [
            "Multidisciplinary: Yes\n"
            "Main discipline: [[物理学];[理论物理];[量子力学]]"
        ]
        main, non_main = levels_from_paths(paths, raw_outputs)
        assert main == [("1", "物理学"), ("2", "理论物理"), ("3", "量子力学")]
        assert non_main == [("1", "数学"), ("2", "代数学"), ("3", "线性代数")]

    def test_multi_paths_no_main_hint_defaults_to_first(self):
        paths = [
            ["生物学", "生物化学"],
            ["化学", "有机化学"],
        ]
        main, non_main = levels_from_paths(paths, ["no match here"])
        assert main == [("1", "生物学"), ("2", "生物化学")]
        assert non_main == [("1", "化学"), ("2", "有机化学")]

    def test_level_numbers_are_correct(self):
        """Ensure a L3 discipline is never assigned L1."""
        paths = [["生物学", "生物化学", "核酸生物化学"]]
        main, _ = levels_from_paths(paths, [])
        level_map = {name: lvl for lvl, name in main}
        assert level_map["生物学"] == "1"
        assert level_map["生物化学"] == "2"
        assert level_map["核酸生物化学"] == "3"

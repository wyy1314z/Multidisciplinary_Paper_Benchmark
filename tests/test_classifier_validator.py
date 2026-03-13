"""Tests for the choice validator."""

from crossdisc_extractor.classifier.validator import ChoiceValidator


class TestChoiceValidator:
    def test_validate_one_valid(self):
        v = ChoiceValidator(["A", "B", "C"])
        assert v.validate_one("A")

    def test_validate_one_invalid(self):
        v = ChoiceValidator(["A", "B", "C"])
        assert not v.validate_one("D")

    def test_validate_many_filters(self):
        v = ChoiceValidator(["A", "B", "C"], max_k=2)
        assert v.validate_many(["D", "A", "E", "B", "C"]) == ["A", "B"]

    def test_validate_many_deduplicates(self):
        v = ChoiceValidator(["A", "B"], max_k=3)
        assert v.validate_many(["A", "A", "B", "A"]) == ["A", "B"]

    def test_validate_many_respects_max_k(self):
        v = ChoiceValidator(["A", "B", "C"], max_k=1)
        assert v.validate_many(["A", "B", "C"]) == ["A"]

    def test_validate_many_empty(self):
        v = ChoiceValidator(["A"], max_k=1)
        assert v.validate_many(["X", "Y"]) == []

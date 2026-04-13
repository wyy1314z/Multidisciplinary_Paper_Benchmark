"""Regression tests for secondary-list cleanup and SBERT device fallback helpers."""

from __future__ import annotations

from crossdisc_extractor.benchmark import metrics
from crossdisc_extractor.extractor_multi_stage import _normalize_secondary_list


def test_normalize_secondary_list_removes_primary_and_duplicates():
    result = _normalize_secondary_list(
        "材料科学",
        ["材料科学", "化学", "计算机科学技术", "化学", "", "材料科学"],
    )
    assert result == ["化学", "计算机科学技术"]


def test_resolve_sbert_device_respects_no_gpu(monkeypatch):
    monkeypatch.setenv("CROSSDISC_SBERT_DEVICE", "no-gpu")
    assert metrics._resolve_sbert_device() == "cpu"


def test_candidate_sbert_devices_keeps_cpu_fallback():
    assert metrics._candidate_sbert_devices("cpu") == ["cpu"]
    assert metrics._candidate_sbert_devices("cuda") == ["cuda", "cpu"]

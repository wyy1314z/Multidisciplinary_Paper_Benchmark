"""Tests for the temporal run diagnosis helper."""

from __future__ import annotations

import json

from scripts.diagnose_temporal_run import (
    _count_stage_sizes,
    _diagnose_extractions,
    _diagnose_validity,
)


def test_diagnose_extractions_detects_primary_pollution(tmp_path):
    path = tmp_path / "validity_extractions_2025.jsonl"
    rows = [
        {
            "title": "Paper A",
            "ok": True,
            "parsed": {
                "meta": {
                    "primary": "材料科学",
                    "secondary_list": ["材料科学", "化学"],
                },
                "查询": {"一级": "query"},
                "假设": {"一级": [{"steps": []}]},
            },
        },
        {
            "title": "Paper B",
            "ok": False,
            "error": "parse failed",
        },
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    diag = _diagnose_extractions(path)
    assert diag["total"] == 2
    assert diag["ok"] == 1
    assert diag["failed"] == 1
    assert diag["primary_in_secondary_list_count"] == 1
    assert diag["empty_query_count"] == 0
    assert diag["empty_hypothesis_count"] == 0


def test_count_stage_sizes_and_validity_metadata_detection(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "benchmark_raw_2023_2024.jsonl").write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    (out / "benchmark_classified_2023_2024.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (out / "benchmark_extractions_2023_2024.jsonl").write_text('{"ok": true}\n', encoding="utf-8")
    (out / "benchmark_dataset_2023_2024.json").write_text("[]", encoding="utf-8")
    (out / "validity_raw_2025.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (out / "validity_classified_2025.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (out / "validity_extractions_2025.jsonl").write_text('{"ok": true}\n', encoding="utf-8")
    (out / "query_eval_2025.json").write_text("[]", encoding="utf-8")
    (out / "query_eval_scores").mkdir()
    (out / "query_eval_scores" / "multimodel_16metrics_results.json").write_text("[]", encoding="utf-8")

    validity = {
        "num_papers": 1,
        "summary": {},
        "papers": [
            {
                "paper_id": "abc",
                "journal": None,
                "fwci": None,
                "cited_by_count": None,
                "overall_scores": {
                    "consistency": 0.0,
                    "concept_f1": 0.2,
                    "relation_precision": 0.0,
                    "path_alignment_best": 0.0,
                    "rao_stirling": 0.0,
                    "innovation": 7.0,
                    "scientificity": 8.0,
                    "testability": 6.0,
                },
                "metadata": {
                    "journal": "Nature",
                    "fwci": 10.0,
                    "cited_by_count": 5,
                },
            }
        ],
    }
    (out / "benchmark_validity_2025.json").write_text(
        json.dumps(validity, ensure_ascii=False),
        encoding="utf-8",
    )

    counts = _count_stage_sizes(out)
    assert counts["benchmark_raw"] == 2
    assert counts["benchmark_classified"] == 1
    assert counts["validity_result"] == 1

    validity_diag = _diagnose_validity(out)
    assert validity_diag["num_papers"] == 1
    assert validity_diag["metadata_nested_present_count"] == 1
    assert validity_diag["metadata_top_level_missing_count"] == 1
    assert validity_diag["overall_metric_summary"]["consistency"]["zero_count"] == 1

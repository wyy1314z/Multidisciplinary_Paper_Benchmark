"""Tests for the temporal benchmark workflow helpers."""

from __future__ import annotations

import json

from run_multimodel_eval_16metrics import build_paper_map
from scripts.build_query_eval_set import build_query_eval_rows
from scripts.prepare_temporal_papers import keep_by_journal, normalize_row


class TestPrepareTemporalPapers:
    def test_normalize_row_from_openalex_style_columns(self):
        row = {
            "display_name": "Paper Title",
            "abstract": "Paper abstract",
            "primary_location.source.display_name": "Nature Communications",
            "primary_location.source.id": "https://openalex.org/S123",
            "primary_location.source.issn_l": "2041-1723",
            "primary_location.source.type": "journal",
            "doi": "https://doi.org/10.1038/test",
            "publication_date": "2025-01-02",
            "publication_year": "2025",
            "fwci": "3.14",
            "cited_by_count": "42",
            "primary_topic.display_name": "Biology",
            "best_oa_location.pdf_url": "https://example.org/paper.pdf",
        }
        rec = normalize_row(row)
        assert rec is not None
        assert rec["title"] == "Paper Title"
        assert rec["journal"] == "Nature Communications"
        assert rec["publication_year"] == 2025
        assert rec["fwci"] == 3.14
        assert rec["cited_by_count"] == 42

    def test_keep_by_journal_is_case_insensitive_and_exact(self):
        record = {"journal": "Nature Communications"}
        assert keep_by_journal(record, ["nature communications"])
        assert keep_by_journal(record, ["Nature", "Nature Communications"])
        assert not keep_by_journal(record, ["Nature"])


class TestBuildQueryEvalRows:
    def test_build_query_eval_rows_keeps_metadata_and_queries(self):
        items = [
            {
                "ok": True,
                "title": "Paper A",
                "abstract": "Abstract A",
                "journal": "Nature",
                "publication_year": 2025,
                "fwci": 5.0,
                "cited_by_count": 10,
                "parsed": {
                    "meta": {
                        "title": "Paper A",
                        "primary": "生物学",
                        "secondary_list": ["材料科学"],
                        "journal": "Nature",
                        "publication_year": 2025,
                        "fwci": 5.0,
                        "cited_by_count": 10,
                    },
                    "概念": {
                        "主学科": [
                            {"term": "cell", "normalized": "cell", "evidence": "", "source": "abstract", "confidence": 0.9}
                        ],
                        "辅学科": {},
                    },
                    "跨学科关系": [],
                    "查询": {"一级": "L1 query", "二级": ["L2 query"], "三级": ["L3 query"]},
                },
            }
        ]
        rows = build_query_eval_rows(items)
        assert len(rows) == 1
        assert rows[0]["queries"]["L1"] == "L1 query"
        assert rows[0]["metadata"]["journal"] == "Nature"
        assert rows[0]["metadata"]["fwci"] == 5.0


class TestBuildPaperMap:
    def test_build_paper_map_accepts_query_eval_mode(self, tmp_path):
        rows = [
            {
                "paper_id": "abc123",
                "title": "Paper A",
                "abstract": "Abstract A",
                "primary_discipline": "生物学",
                "secondary_disciplines": ["材料科学"],
                "queries": {"L1": "L1 query", "L2": ["L2 query"], "L3": ["L3 query"]},
                "gt_terms": ["cell", "material"],
                "gt_relations": [{"head": "cell", "tail": "material"}],
                "metadata": {"journal": "Nature Communications", "fwci": 3.0},
            }
        ]
        path = tmp_path / "query_eval.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        paper_map = build_paper_map(str(path), input_mode="query_eval")
        assert "abc123" in paper_map
        assert paper_map["abc123"]["l1_query"] == "L1 query"
        assert paper_map["abc123"]["metadata"]["journal"] == "Nature Communications"

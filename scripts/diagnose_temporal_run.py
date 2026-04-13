#!/usr/bin/env python3
"""Diagnose a temporal benchmark pipeline run and summarize failure modes."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Tuple


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _safe_mean(values: Iterable[float]) -> float | None:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not vals:
        return None
    return mean(vals)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _parse_pipeline_log(log_path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "non_multidisciplinary_count": 0,
        "below_threshold_count": 0,
        "no_valid_items_count": 0,
        "non_multidisciplinary_examples": [],
        "below_threshold_examples": [],
        "no_valid_items_examples": [],
    }
    if not log_path.exists():
        return info

    non_multi_re = re.compile(r"Non-multidisciplinary .*?: (.+)$")
    below_re = re.compile(r"Below cross-disc confidence threshold .*?: (.+)$")
    no_valid_re = re.compile(r"Level \d+ attempt \d+/\d+: no valid items, (.+)$")

    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "Non-multidisciplinary" in line:
            info["non_multidisciplinary_count"] += 1
            m = non_multi_re.search(line)
            if m and len(info["non_multidisciplinary_examples"]) < 8:
                info["non_multidisciplinary_examples"].append(m.group(1).strip())
        if "Below cross-disc confidence threshold" in line:
            info["below_threshold_count"] += 1
            m = below_re.search(line)
            if m and len(info["below_threshold_examples"]) < 8:
                info["below_threshold_examples"].append(m.group(1).strip())
        if "no valid items" in line:
            info["no_valid_items_count"] += 1
            m = no_valid_re.search(line)
            if m and len(info["no_valid_items_examples"]) < 8:
                info["no_valid_items_examples"].append(m.group(1).strip())
    return info


def _count_stage_sizes(output_dir: Path) -> Dict[str, Any]:
    mapping = {
        "benchmark_raw": output_dir / "benchmark_raw_2023_2024.jsonl",
        "benchmark_classified": output_dir / "benchmark_classified_2023_2024.jsonl",
        "benchmark_extractions": output_dir / "benchmark_extractions_2023_2024.jsonl",
        "benchmark_dataset": output_dir / "benchmark_dataset_2023_2024.json",
        "validity_raw": output_dir / "validity_raw_2025.jsonl",
        "validity_classified": output_dir / "validity_classified_2025.jsonl",
        "validity_extractions": output_dir / "validity_extractions_2025.jsonl",
        "validity_result": output_dir / "benchmark_validity_2025.json",
        "query_eval": output_dir / "query_eval_2025.json",
        "query_results": output_dir / "query_eval_scores" / "multimodel_16metrics_results.json",
    }

    counts: Dict[str, Any] = {}
    for key, path in mapping.items():
        if not path.exists():
            counts[key] = None
            continue
        if path.suffix == ".jsonl":
            counts[key] = len(_load_jsonl(path))
        else:
            data = _load_json(path)
            if isinstance(data, list):
                counts[key] = len(data)
            elif isinstance(data, dict):
                counts[key] = data.get("num_papers") if "num_papers" in data else len(data)
            else:
                counts[key] = None
    return counts


def _diagnose_extractions(path: Path) -> Dict[str, Any]:
    rows = _load_jsonl(path)
    ok_rows = [row for row in rows if row.get("ok")]
    errors = [row for row in rows if not row.get("ok")]
    primary_repeat_titles: List[str] = []
    primary_repeat_count = 0
    empty_query_count = 0
    empty_hyp_count = 0

    for row in ok_rows:
        parsed = row.get("parsed") or {}
        meta = parsed.get("meta") or {}
        primary = meta.get("primary") or row.get("primary")
        secondary_list = meta.get("secondary_list") or row.get("secondary_list") or []
        if primary and primary in secondary_list:
            primary_repeat_count += 1
            if len(primary_repeat_titles) < 8:
                primary_repeat_titles.append(row.get("title", "")[:120])
        query_obj = parsed.get("查询") or {}
        hyp_obj = parsed.get("假设") or {}
        if not query_obj or not (query_obj.get("一级") or query_obj.get("二级") or query_obj.get("三级")):
            empty_query_count += 1
        if not hyp_obj or not (hyp_obj.get("一级") or hyp_obj.get("二级") or hyp_obj.get("三级")):
            empty_hyp_count += 1

    error_samples = []
    for row in errors[:5]:
        error_samples.append(
            {
                "title": row.get("title", "")[:120],
                "error": str(row.get("error", ""))[:300],
            }
        )

    return {
        "total": len(rows),
        "ok": len(ok_rows),
        "failed": len(errors),
        "primary_in_secondary_list_count": primary_repeat_count,
        "primary_in_secondary_list_examples": primary_repeat_titles,
        "empty_query_count": empty_query_count,
        "empty_hypothesis_count": empty_hyp_count,
        "failed_examples": error_samples,
    }


def _diagnose_validity(output_dir: Path) -> Dict[str, Any]:
    path = output_dir / "benchmark_validity_2025.json"
    if not path.exists():
        return {}
    data = _load_json(path)
    papers = data.get("papers", [])
    top_level_missing = 0
    nested_present = 0
    for paper in papers:
        meta = paper.get("metadata") or {}
        has_nested = any(meta.get(k) not in ("", None) for k in ("journal", "fwci", "cited_by_count"))
        has_top_level = any(paper.get(k) not in ("", None) for k in ("journal", "fwci", "cited_by_count"))
        if has_nested:
            nested_present += 1
        if has_nested and not has_top_level:
            top_level_missing += 1

    metric_names = [
        "consistency",
        "concept_f1",
        "relation_precision",
        "path_alignment_best",
        "rao_stirling",
        "innovation",
        "scientificity",
        "testability",
    ]
    metric_summary: Dict[str, Dict[str, float | None]] = {}
    for metric in metric_names:
        vals = [paper.get("overall_scores", {}).get(metric) for paper in papers]
        finite_vals = [float(v) for v in vals if v is not None and not math.isnan(float(v))]
        metric_summary[metric] = {
            "mean": _round(_safe_mean(finite_vals)),
            "zero_count": sum(1 for v in finite_vals if v == 0),
            "non_null_count": len(finite_vals),
        }

    return {
        "num_papers": data.get("num_papers", len(papers)),
        "metadata_nested_present_count": nested_present,
        "metadata_top_level_missing_count": top_level_missing,
        "overall_metric_summary": metric_summary,
    }


def _summarize_zero_like_metrics(rows: List[Dict[str, Any]], metric_names: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for metric in metric_names:
        vals = []
        for row in rows:
            scores = row.get("scores") or {}
            if metric in scores and scores[metric] is not None:
                vals.append(float(scores[metric]))
        out[metric] = {
            "mean": _round(_safe_mean(vals)),
            "zero_count": sum(1 for v in vals if v == 0),
            "non_null_count": len(vals),
        }
    return out


def _diagnose_query_eval(output_dir: Path) -> Dict[str, Any]:
    results_path = output_dir / "query_eval_scores" / "multimodel_16metrics_results.json"
    summary_path = output_dir / "query_eval_scores" / "multimodel_16metrics_summary.json"
    parse_cache_dir = output_dir / "query_eval_scores" / "parse_cache"

    if not results_path.exists():
        return {}

    rows = _load_json(results_path)
    parse_error_count = sum(1 for row in rows if row.get("parse_error"))
    model_counts = Counter((row.get("model") or row.get("method") or "unknown") for row in rows)

    metrics = [
        "L1_concept_f1",
        "L1_relation_precision",
        "L1_path_alignment_best",
        "L1_rao_stirling",
        "L2_concept_f1",
        "L2_relation_precision",
        "L2_path_alignment_best",
        "L3_concept_f1",
        "L3_relation_precision",
        "L3_path_alignment_best",
        "L1_factual_precision",
        "L1_innovation",
        "L1_scientificity",
        "L1_testability",
    ]

    summary = {
        "num_rows": len(rows),
        "parse_error_count": parse_error_count,
        "parse_cache_count": len(list(parse_cache_dir.glob("*.json"))) if parse_cache_dir.exists() else 0,
        "model_counts": dict(model_counts),
        "metric_summary": _summarize_zero_like_metrics(rows, metrics),
    }

    if summary_path.exists():
        data = _load_json(summary_path)
        summary["summary_keys"] = list(data.keys())
    return summary


def _build_findings(stage_counts: Dict[str, Any], log_info: Dict[str, Any], extraction_diag: Dict[str, Any], validity_diag: Dict[str, Any], query_diag: Dict[str, Any]) -> List[str]:
    findings: List[str] = []

    raw_b = stage_counts.get("benchmark_raw") or 0
    cls_b = stage_counts.get("benchmark_classified") or 0
    ds_b = stage_counts.get("benchmark_dataset") or 0
    raw_v = stage_counts.get("validity_raw") or 0
    cls_v = stage_counts.get("validity_classified") or 0
    qe_v = stage_counts.get("query_eval") or 0

    if raw_b and cls_b < raw_b:
        findings.append(f"benchmark 候选在分类阶段从 {raw_b} 降到 {cls_b}，缩水 {raw_b - cls_b} 篇。")
    if raw_v and cls_v < raw_v:
        findings.append(f"2025 验证集在分类阶段从 {raw_v} 降到 {cls_v}，缩水 {raw_v - cls_v} 篇。")
    if log_info.get("below_threshold_count"):
        findings.append(f"日志中出现 {log_info['below_threshold_count']} 次低于 cross-disc 阈值过滤。")
    if log_info.get("non_multidisciplinary_count"):
        findings.append(f"日志中出现 {log_info['non_multidisciplinary_count']} 次单学科过滤。")
    if log_info.get("no_valid_items_count"):
        findings.append(f"分类层级选择中出现 {log_info['no_valid_items_count']} 次 'no valid items'，说明模型输出与候选层级不匹配。")
    if extraction_diag.get("primary_in_secondary_list_count"):
        findings.append(
            f"抽取结果里有 {extraction_diag['primary_in_secondary_list_count']} 条记录出现 primary 落入 secondary_list，跨学科元信息被污染。"
        )
    if validity_diag.get("metadata_top_level_missing_count"):
        findings.append(
            f"validity 结果中有 {validity_diag['metadata_top_level_missing_count']} 篇文章只在嵌套 metadata 中保留期刊/影响信号，顶层字段为空。"
        )
    if query_diag.get("num_rows"):
        rel_zero = query_diag["metric_summary"]["L1_relation_precision"]["zero_count"]
        rel_n = query_diag["metric_summary"]["L1_relation_precision"]["non_null_count"]
        align_zero = query_diag["metric_summary"]["L1_path_alignment_best"]["zero_count"]
        align_n = query_diag["metric_summary"]["L1_path_alignment_best"]["non_null_count"]
        if rel_n and rel_zero == rel_n:
            findings.append("query 评测中 L1_relation_precision 全为 0，关系级对齐完全失效。")
        if align_n and align_zero == align_n:
            findings.append("query 评测中 L1_path_alignment_best 全为 0，路径对齐指标完全失效。")
        if qe_v and qe_v <= 12:
            findings.append(f"query eval 只有 {qe_v} 条样本，统计解释力偏弱。")
    return findings


def _render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Temporal Run Diagnosis")
    lines.append("")
    lines.append("## Key Findings")
    for finding in report["key_findings"]:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("## Stage Counts")
    for key, value in report["stage_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Log Diagnostics")
    log_info = report["log_diagnostics"]
    for key in [
        "non_multidisciplinary_count",
        "below_threshold_count",
        "no_valid_items_count",
    ]:
        lines.append(f"- `{key}`: {log_info.get(key)}")
    if log_info.get("below_threshold_examples"):
        lines.append("- `below_threshold_examples`:")
        for item in log_info["below_threshold_examples"]:
            lines.append(f"  - {item}")
    if log_info.get("non_multidisciplinary_examples"):
        lines.append("- `non_multidisciplinary_examples`:")
        for item in log_info["non_multidisciplinary_examples"]:
            lines.append(f"  - {item}")
    if log_info.get("no_valid_items_examples"):
        lines.append("- `no_valid_items_examples`:")
        for item in log_info["no_valid_items_examples"]:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append("## Extraction Diagnostics")
    for name, section in report["extraction_diagnostics"].items():
        lines.append(f"### {name}")
        for key, value in section.items():
            lines.append(f"- `{key}`: {value}")
        lines.append("")
    lines.append("## Validity Diagnostics")
    for key, value in report["validity_diagnostics"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Query Evaluation Diagnostics")
    for key, value in report["query_diagnostics"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a temporal benchmark pipeline output directory")
    parser.add_argument("--output-dir", required=True, help="Temporal pipeline output directory")
    parser.add_argument("--json-out", default=None, help="Optional JSON report path")
    parser.add_argument("--md-out", default=None, help="Optional Markdown report path")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    stage_counts = _count_stage_sizes(output_dir)
    log_info = _parse_pipeline_log(output_dir / "pipeline.log")
    extraction_diag = {
        "benchmark_extractions": _diagnose_extractions(output_dir / "benchmark_extractions_2023_2024.jsonl"),
        "validity_extractions": _diagnose_extractions(output_dir / "validity_extractions_2025.jsonl"),
    }
    validity_diag = _diagnose_validity(output_dir)
    query_diag = _diagnose_query_eval(output_dir)

    report = {
        "output_dir": str(output_dir),
        "stage_counts": stage_counts,
        "log_diagnostics": log_info,
        "extraction_diagnostics": extraction_diag,
        "validity_diagnostics": validity_diag,
        "query_diagnostics": query_diag,
    }
    report["key_findings"] = _build_findings(
        stage_counts=stage_counts,
        log_info=log_info,
        extraction_diag=extraction_diag["validity_extractions"],
        validity_diag=validity_diag,
        query_diag=query_diag,
    )

    json_out = Path(args.json_out) if args.json_out else output_dir / "diagnosis_summary.json"
    md_out = Path(args.md_out) if args.md_out else output_dir / "diagnosis_report.md"
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_render_markdown(report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n诊断摘要已保存到: {json_out}")
    print(f"诊断报告已保存到: {md_out}")


if __name__ == "__main__":
    main()

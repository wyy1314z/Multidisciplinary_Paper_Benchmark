"""Export a first-N query/hypothesis demo from full model generation results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _load_json_or_jsonl(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("items", [])
    return list(data or [])


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _model_file(model_results_dir: Path, model: str) -> Path:
    return model_results_dir / f"{model.replace('/', '_').replace(':', '_')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export first-N query/hypothesis demo")
    parser.add_argument("--queries", required=True, help="Full query eval JSON/JSONL")
    parser.add_argument("--model-results-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    queries = _load_json_or_jsonl(Path(args.queries))
    queries.sort(key=lambda row: int(row.get("input_index", 0)))
    demo_queries = queries[: args.limit]
    demo_ids = {row.get("paper_id") for row in demo_queries}

    _write_json(output_dir / "demo_queries_first50.json", demo_queries)

    results_by_model: Dict[str, List[Dict[str, Any]]] = {}
    result_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    model_dir = Path(args.model_results_dir)
    for model in args.models:
        path = _model_file(model_dir, model)
        rows = _load_json_or_jsonl(path) if path.exists() else []
        rows = [row for row in rows if row.get("paper_id") in demo_ids]
        rows.sort(
            key=lambda row: next(
                (
                    int(q.get("input_index", 0))
                    for q in demo_queries
                    if q.get("paper_id") == row.get("paper_id")
                ),
                10**9,
            )
        )
        results_by_model[model] = rows
        result_index[model] = {row.get("paper_id"): row for row in rows}
        _write_json(output_dir / f"{model.replace('/', '_').replace(':', '_')}_first50.json", rows)

    combined = []
    for query in demo_queries:
        pid = query.get("paper_id")
        combined.append(
            {
                "paper_id": pid,
                "title": query.get("title", ""),
                "journal": (query.get("metadata") or {}).get("journal", ""),
                "primary_discipline": query.get("primary_discipline", ""),
                "secondary_disciplines": query.get("secondary_disciplines", []),
                "L1_query": (query.get("queries") or {}).get("L1", ""),
                "hypotheses_by_model": {
                    model: (result_index.get(model, {}).get(pid) or {}).get("free_text_hypotheses", [])
                    for model in args.models
                },
                "errors_by_model": {
                    model: (result_index.get(model, {}).get(pid) or {}).get("error", "")
                    for model in args.models
                },
            }
        )

    _write_json(output_dir / "demo_first50_combined.json", combined)

    summary_lines = [
        "# First 50 L1 Query Hypothesis Demo",
        "",
        f"- queries: {len(demo_queries)}",
        f"- models: {', '.join(args.models)}",
        "",
        "| # | paper_id | journal | title |",
        "|---:|---|---|---|",
    ]
    for idx, query in enumerate(demo_queries, start=1):
        title = str(query.get("title", "")).replace("|", "\\|")
        journal = str((query.get("metadata") or {}).get("journal", "")).replace("|", "\\|")
        summary_lines.append(f"| {idx} | {query.get('paper_id', '')} | {journal} | {title} |")
    (output_dir / "README.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

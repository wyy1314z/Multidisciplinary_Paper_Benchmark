#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


LEVELS = ("L1", "L2", "L3")


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _paper_id_from_title(title: str) -> str:
    return hashlib.md5((title or "").encode("utf-8")).hexdigest()[:12]


def _iter_models(items: Iterable[Dict[str, Any]]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        generated = item.get("generated_hypotheses", {})
        for level in LEVELS:
            for model in (generated.get(level, {}) or {}).keys():
                if model not in seen:
                    seen.add(model)
                    ordered.append(model)
    return ordered


def _build_record(item: Dict[str, Any], level: str, model: str) -> Dict[str, Any]:
    generated = item.get("generated_hypotheses", {})
    info = ((generated.get(level) or {}).get(model) or {})
    title = item.get("title", "")
    doi = item.get("doi", "")
    paper_id = _paper_id_from_title(title)
    query = (item.get("query", {}) or {}).get(level, "")
    text = info.get("text", "")

    return {
        "paper_id": paper_id,
        "method_name": info.get("method_name") or f"{model}-{level}",
        "prompt_level": info.get("prompt_level") or level,
        "hypothesis_format": info.get("hypothesis_format", ""),
        "query": query,
        "free_text_hypotheses": [text] if text else [],
        "structured_paths": {},
        "error": info.get("error", ""),
        "metadata": {
            "title": title,
            "journal": item.get("journal", ""),
            "doi": doi,
            "publication_date": item.get("publication_date", ""),
            "primary_discipline": item.get("primary_discipline", ""),
            "secondary_disciplines": item.get("secondary_disciplines", []),
            "source_level": level,
            "source_model": model,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert merged L1/L2/L3 multi-model hypotheses into run_multimodel_eval_16metrics input files."
    )
    parser.add_argument("--input", required=True, help="Merged three-level hypotheses JSON")
    parser.add_argument("--output-dir", required=True, help="Directory for per-model JSON files")
    parser.add_argument(
        "--models",
        default="",
        help="Optional comma-separated model whitelist. Default: auto-detect all models in input.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = _load_json(input_path)
    if not isinstance(items, list):
        raise SystemExit("Input must be a JSON list.")

    models = [m.strip() for m in args.models.split(",") if m.strip()] or _iter_models(items)
    if not models:
        raise SystemExit("No models found in input.")

    rows_by_model: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        for model in models:
            for level in LEVELS:
                rows_by_model[model].append(_build_record(item, level, model))

    manifest = {
        "input": str(input_path),
        "num_papers": len(items),
        "num_models": len(models),
        "models": models,
        "records_per_model": len(items) * len(LEVELS),
    }

    for model in models:
        out_path = output_dir / f"{model}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(rows_by_model[model], f, ensure_ascii=False, indent=2)

    with (output_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(
        f"Prepared {len(models)} model files in {output_dir} "
        f"({len(items)} papers x {len(LEVELS)} levels each)."
    )


if __name__ == "__main__":
    main()

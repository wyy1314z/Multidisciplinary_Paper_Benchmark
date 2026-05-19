#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


LEVELS = ("L1", "L2", "L3")


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _paper_id_from_title(title: str) -> str:
    return hashlib.md5((title or "").encode("utf-8")).hexdigest()[:12]


def _infer_framework_name(path: Path) -> str:
    run_tag = path.stem.replace("_l1_l2_l3_hypotheses", "")
    m = re.match(r"computer158_(.+?)_gpt55$", run_tag)
    if m:
        return m.group(1)
    m = re.match(r"computer\d+_(.+?)_[a-z0-9]+$", run_tag)
    if m:
        return m.group(1)
    return run_tag


def _iter_merged_files(input_globs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    seen = set()
    for pattern in input_globs:
        for path in sorted(Path().glob(pattern)):
            resolved = path.resolve()
            if resolved not in seen and path.is_file():
                seen.add(resolved)
                files.append(path)
    return files


def _pick_model_name(item: Dict[str, Any]) -> str:
    generated = item.get("generated_hypotheses", {})
    for level in LEVELS:
        level_block = generated.get(level) or {}
        if isinstance(level_block, dict):
            for model_name in level_block.keys():
                return str(model_name)
    return ""


def _paper_id_from_item(item: Dict[str, Any]) -> str:
    return _paper_id_from_title(item.get("title", ""))


def _load_allowed_ids(query_subset_path: Optional[str]) -> Optional[Set[str]]:
    if not query_subset_path:
        return None
    data = _load_json(Path(query_subset_path))
    if not isinstance(data, list):
        raise SystemExit("--query-subset must be a JSON list")
    allowed = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        allowed.add(_paper_id_from_item(item))
    return allowed


def _build_record(item: Dict[str, Any], level: str, framework_name: str, model_name: str) -> Dict[str, Any]:
    generated = item.get("generated_hypotheses", {})
    info = ((generated.get(level) or {}).get(model_name) or {})
    title = item.get("title", "")
    paper_id = _paper_id_from_title(title)
    query = (item.get("query", {}) or {}).get(level, "")
    text = info.get("text", "")
    primary = item.get("primary_discipline", "")

    return {
        "paper_id": paper_id,
        "method_name": info.get("method_name") or f"{framework_name}-{level}",
        "prompt_level": info.get("prompt_level") or level,
        "hypothesis_format": info.get("hypothesis_format", ""),
        "query": query,
        "free_text_hypotheses": [text] if text else [],
        "structured_paths": {},
        "error": info.get("error", ""),
        "metadata": {
            "title": title,
            "journal": item.get("journal", ""),
            "doi": item.get("doi", ""),
            "publication_date": item.get("publication_date", ""),
            "primary_discipline": primary,
            "secondary_disciplines": item.get("secondary_disciplines", []),
            "framework": framework_name,
            "source_model": model_name,
            "source_level": level,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert multiple multi-agent merged three-level hypothesis JSON files into run_multimodel_eval_16metrics input files."
    )
    parser.add_argument(
        "--input-glob",
        action="append",
        default=[],
        help="Glob(s) for merged multi-agent JSON files. Can be passed multiple times.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for per-framework JSON files")
    parser.add_argument(
        "--query-subset",
        default="",
        help="Optional query-eval JSON subset; when provided only those paper_ids are kept.",
    )
    args = parser.parse_args()

    input_globs = args.input_glob or [
        "outputs/nature_nc_2026_single_query_hyp/computer158_*_gpt55/computer158_*_gpt55_l1_l2_l3_hypotheses.json",
    ]
    merged_files = _iter_merged_files(input_globs)
    if not merged_files:
        raise SystemExit("No merged multi-agent JSON files found.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    allowed_ids = _load_allowed_ids(args.query_subset or None)

    manifest: Dict[str, Any] = {
        "input_globs": list(input_globs),
        "query_subset": args.query_subset or None,
        "frameworks": {},
    }

    for merged_file in merged_files:
        framework_name = _infer_framework_name(merged_file)
        items = _load_json(merged_file)
        if not isinstance(items, list):
            raise SystemExit(f"{merged_file} must be a JSON list.")
        if not items:
            continue

        if allowed_ids is not None:
            items = [item for item in items if _paper_id_from_item(item) in allowed_ids]
            if not items:
                continue

        model_name = _pick_model_name(items[0])
        if not model_name:
            raise SystemExit(f"{merged_file} does not contain generated_hypotheses model keys.")

        rows: List[Dict[str, Any]] = []
        for item in items:
            for level in LEVELS:
                rows.append(_build_record(item, level, framework_name, model_name))

        out_path = output_dir / f"{framework_name}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

        manifest["frameworks"][framework_name] = {
            "input": str(merged_file),
            "source_model": model_name,
            "num_papers": len(items),
            "records": len(rows),
            "output": str(out_path),
        }

    manifest["num_frameworks"] = len(manifest["frameworks"])
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(
        f"Prepared {manifest['num_frameworks']} framework files in {output_dir} "
        f"from {len(merged_files)} merged JSON inputs."
    )


if __name__ == "__main__":
    main()

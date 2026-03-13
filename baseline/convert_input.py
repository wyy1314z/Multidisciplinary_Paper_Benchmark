"""
baseline/convert_input.py — 将 paper_1.json (JSONL) 转换为统一 PaperInput 列表。

用法:
    python -m baseline.convert_input \
        --input data/paper_1.json \
        --output baseline/data/papers_unified.json \
        [--max-papers 5]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import List

from baseline.common import PaperInput


def _parse_discipline(raw: str) -> str:
    """从 '[[生物学]; [生物物理学]; [生物化学]]' 提取第一个学科。"""
    # 去掉最外层 [[ ]]，然后按 ; 分割，取第一个 [...] 内的内容
    cleaned = (raw or "").strip()
    # 去掉最外层一对方括号
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1].strip()
    # 提取所有 [xxx] 中的内容
    match = re.findall(r"\[([^\]]+)\]", cleaned)
    if match:
        return match[0].strip()
    # fallback
    return cleaned.split(";")[0].strip("[] ") if cleaned else ""


def _parse_secondary(fields_str: str, primary: str) -> List[str]:
    """从 field 字段提取辅学科（去掉主学科重复）。"""
    parts = [p.strip() for p in (fields_str or "").split("|") if p.strip()]
    seen = set()
    result = []
    for p in parts:
        if p.lower() != primary.lower() and p not in seen:
            seen.add(p)
            result.append(p)
    return result


def convert_paper_jsonl(input_path: str, max_papers: int = 0) -> List[PaperInput]:
    papers: List[PaperInput] = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            title = obj.get("title", "")
            abstract = obj.get("abstract", "")
            if not title or not abstract:
                continue

            paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
            primary = _parse_discipline(obj.get("main_discipline", ""))
            secondary = _parse_secondary(obj.get("field", ""), primary)

            papers.append(PaperInput(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                introduction=obj.get("introduction", ""),
                primary_discipline=primary,
                secondary_disciplines=secondary,
            ))
            if max_papers and len(papers) >= max_papers:
                break
    return papers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-papers", type=int, default=0)
    args = parser.parse_args()

    papers = convert_paper_jsonl(args.input, args.max_papers)
    data = [p.to_dict() for p in papers]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Converted {len(papers)} papers → {args.output}")


if __name__ == "__main__":
    main()

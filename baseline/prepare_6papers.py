#!/usr/bin/env python3
"""
baseline/prepare_6papers.py — 从 classified.jsonl 提取6篇2025年Nature Communications论文。

输出统一的 PaperInput JSON 格式，供 run_batch_demo.py 和 run_comparison.py 使用。

用法:
    python -m baseline.prepare_6papers \
        --input outputs/nature_comm_100_v6/classified.jsonl \
        --output baseline/data/papers_6_2025.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List


# 选定的6篇2025年论文（通过DOI中的 s41467-025- 确认为2025年）
# 覆盖6个不同主学科，跨学科评分 ≥ 0.7
SELECTED_PAPERS = [
    {
        "line_index": 8,   # 0-based
        "doi_fragment": "s41467-025-56572",
        "reason": "生物学×计算机×化学, crossdisc=0.80",
    },
    {
        "line_index": 33,
        "doi_fragment": "s41467-025-56788",
        "reason": "化学×材料×计算机, crossdisc=0.80",
    },
    {
        "line_index": 4,
        "doi_fragment": "s41467-025-56485",
        "reason": "计算机×材料, crossdisc=0.70",
    },
    {
        "line_index": 9,
        "doi_fragment": "s41467-025-57981",
        "reason": "农学×地球科学×环境, crossdisc=0.70",
    },
    {
        "line_index": 27,
        "doi_fragment": "s41467-025-57045",
        "reason": "材料×基础医学, crossdisc=0.70",
    },
    {
        "line_index": 22,
        "doi_fragment": "s41467-025-60872",
        "reason": "计算机×生物, crossdisc=0.70",
    },
]


def load_selected_papers(input_path: str) -> List[Dict[str, Any]]:
    """从 classified.jsonl 中按行号提取选定的论文。"""
    with open(input_path, encoding="utf-8") as f:
        lines = f.readlines()

    papers = []
    for spec in SELECTED_PAPERS:
        idx = spec["line_index"]
        if idx >= len(lines):
            print(f"[WARN] Line index {idx} out of range (total {len(lines)} lines)")
            continue

        raw = json.loads(lines[idx].strip())

        # 验证 DOI
        doi = raw.get("pdf_url", "")
        if spec["doi_fragment"] not in doi:
            print(f"[WARN] DOI mismatch at line {idx}: expected {spec['doi_fragment']}, got {doi}")
            # 尝试搜索正确的行
            found = False
            for j, line in enumerate(lines):
                d = json.loads(line.strip())
                if spec["doi_fragment"] in d.get("pdf_url", ""):
                    raw = d
                    print(f"  → Found at line {j} instead")
                    found = True
                    break
            if not found:
                print(f"  → Paper not found, skipping")
                continue

        # 转换为 PaperInput 格式
        title = raw.get("title", "")
        paper_id = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
        primary = raw.get("primary", "")
        secondary_list = raw.get("secondary_list", [])
        if isinstance(secondary_list, str):
            secondary_list = [s.strip() for s in secondary_list.split(",") if s.strip()]

        paper = {
            "paper_id": paper_id,
            "title": title,
            "abstract": raw.get("abstract", ""),
            "introduction": "",
            "primary_discipline": primary,
            "secondary_disciplines": secondary_list,
        }
        # 额外元数据（仅用于展示，不写入输出文件）
        paper["_meta"] = {
            "doi": raw.get("pdf_url", ""),
            "crossdisc_score": raw.get("crossdisc_score", 0),
            "selection_reason": spec["reason"],
        }
        papers.append(paper)

    return papers


def main():
    parser = argparse.ArgumentParser(
        description="从 classified.jsonl 提取6篇2025年论文，输出 PaperInput 格式"
    )
    parser.add_argument(
        "--input",
        default="outputs/nature_comm_100_v6/classified.jsonl",
        help="classified.jsonl 路径",
    )
    parser.add_argument(
        "--output",
        default="baseline/data/papers_6_2025.json",
        help="输出 JSON 路径",
    )
    args = parser.parse_args()

    papers = load_selected_papers(args.input)

    if not papers:
        print("ERROR: No papers loaded!", file=sys.stderr)
        sys.exit(1)

    # 输出时去掉 _meta 字段（PaperInput 不接受）
    output_papers = []
    for p in papers:
        meta = p.pop("_meta", {})
        output_papers.append(p)
        p["_meta"] = meta  # 恢复（用于后续打印）

    with open(args.output, "w", encoding="utf-8") as f:
        # 只写入 PaperInput 兼容的字段
        clean = [{k: v for k, v in p.items() if not k.startswith("_")} for p in papers]
        json.dump(clean, f, ensure_ascii=False, indent=2)

    print(f"成功提取 {len(papers)} 篇论文 → {args.output}")
    print()
    for i, p in enumerate(papers):
        meta = p.get("_meta", {})
        print(f"  [{i+1}] {p['title'][:70]}...")
        print(f"      主学科: {p['primary_discipline']}")
        print(f"      辅学科: {p['secondary_disciplines']}")
        print(f"      跨学科: {meta.get('crossdisc_score', 'N/A')}")
        print()


if __name__ == "__main__":
    main()

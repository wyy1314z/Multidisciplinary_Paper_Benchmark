"""
baseline/adapters/crossdisc.py — CrossDisc (我们项目) adapter。

调用我们项目的完整管线：
概念抽取 → 关系抽取 → 查询生成 → 多层级结构化假设路径生成

输出包含 L1/L2/L3 三个层级的结构化假设路径，
同时也提供自由文本形式的假设总结（用于与其他 baseline 公平比较）。
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import (
    BaseHypothesisAdapter,
    HypothesisOutput,
    HypothesisPath,
    PaperInput,
)


class CrossDiscAdapter(BaseHypothesisAdapter):
    """CrossDisc：完整管线生成结构化假设路径。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"CrossDisc-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.extractor_multi_stage import run_pipeline_for_item

        t0 = time.time()
        try:
            final, raw_all, introduction = run_pipeline_for_item(
                title=paper.title,
                abstract=paper.abstract,
                primary=paper.primary_discipline or "",
                secondary_list=paper.secondary_disciplines or [],
                pdf_url="",
            )
        except Exception as e:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=[f"[ERROR] {e}"],
                elapsed_seconds=time.time() - t0,
            )
        elapsed = time.time() - t0

        # 解析结构化输出
        parsed = final.model_dump() if hasattr(final, "model_dump") else {}
        hyp_data = parsed.get("假设", {})

        structured_paths = {}
        free_text = []

        for level_key, cn_key, summary_key in [
            ("L1", "一级", "一级总结"),
            ("L2", "二级", "二级总结"),
            ("L3", "三级", "三级总结"),
        ]:
            raw_paths = hyp_data.get(cn_key, [])
            summaries = hyp_data.get(summary_key, [])
            paths = []
            for i, rp in enumerate(raw_paths):
                steps = rp if isinstance(rp, list) else []
                summary = summaries[i] if i < len(summaries) else ""
                paths.append(HypothesisPath(steps=steps, summary=summary))
                if summary:
                    free_text.append(f"[{level_key}] {summary}")
            if paths:
                structured_paths[level_key] = paths

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=free_text,
            structured_paths=structured_paths,
            raw_responses=[json.dumps(parsed, ensure_ascii=False)],
            elapsed_seconds=elapsed,
        )

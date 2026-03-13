"""
baseline/adapters/moose_chem.py — MOOSE-Chem (UIUC, 2024) 风格 baseline。

复现 MOOSE-Chem 的假设生成方式：
- 核心思路：Inspiration-driven hypothesis — 从论文中提取"灵感片段"，
  然后组合不同灵感生成新假设
- 输入：论文 abstract 作为 seed + 从中提取的关键发现作为 inspirations
- 输出：组合式假设（明确标注灵感来源）
- 特点：两阶段——先提取 inspirations，再组合生成 hypothesis

参考: Yang et al., "MOOSE-Chem: Large Language Models for Rediscovering
Unseen Chemistry Scientific Hypotheses", UIUC, 2024.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import BaseHypothesisAdapter, PaperInput, HypothesisOutput


# Stage 1: 提取灵感片段
MOOSE_INSPIRATION_PROMPT = """You are a scientific literature analyst. Extract the key \
scientific findings, methods, and insights from the following paper as a list of \
"inspiration fragments" — concise statements of what was discovered or proposed.

Title: {title}
Abstract: {abstract}

Output as JSON: {{"inspirations": ["finding 1", "finding 2", ...]}}
Extract 3-5 key inspirations. Only output JSON."""

# Stage 2: 组合灵感生成假设
MOOSE_HYPOTHESIS_PROMPT = """You are a creative scientist who generates novel hypotheses \
by combining insights from different sources.

Given the following inspiration fragments extracted from a scientific paper:
{inspirations}

Primary Field: {primary}
Related Fields: {secondary}

Task: Combine these inspirations in unexpected ways to generate {num} novel, \
testable scientific hypotheses. Each hypothesis should:
1. Clearly state which inspirations it combines
2. Propose a specific mechanism or prediction
3. Be falsifiable and experimentally testable

Output as JSON: {{"hypotheses": [
  {{"inspiration_sources": [0, 2], "hypothesis": "..."}},
  ...
]}}
Only output JSON."""


class MooseChemAdapter(BaseHypothesisAdapter):
    """MOOSE-Chem 风格：inspiration-driven 两阶段假设生成。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"MOOSE-Chem-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        t0 = time.time()
        raw_responses = []

        # Stage 1: Extract inspirations
        insp_msg = MOOSE_INSPIRATION_PROMPT.format(
            title=paper.title, abstract=paper.abstract,
        )
        try:
            insp_resp = chat_completion_with_retry(
                [{"role": "user", "content": insp_msg}], temperature=0.3,
            )
            raw_responses.append(insp_resp)
            try:
                insp_obj = json.loads(insp_resp)
                inspirations = insp_obj.get("inspirations", [])
            except json.JSONDecodeError:
                inspirations = [insp_resp.strip()]
        except Exception as e:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=[f"[ERROR] Stage 1 failed: {e}"],
                elapsed_seconds=time.time() - t0,
            )

        # Stage 2: Combine inspirations into hypotheses
        insp_text = "\n".join(f"  [{i}] {ins}" for i, ins in enumerate(inspirations))
        hyp_msg = MOOSE_HYPOTHESIS_PROMPT.format(
            inspirations=insp_text,
            primary=paper.primary_discipline or "N/A",
            secondary=", ".join(paper.secondary_disciplines) if paper.secondary_disciplines else "N/A",
            num=num_hypotheses,
        )
        try:
            hyp_resp = chat_completion_with_retry(
                [{"role": "user", "content": hyp_msg}], temperature=0.7,
            )
            raw_responses.append(hyp_resp)
            try:
                hyp_obj = json.loads(hyp_resp)
                hyp_list = hyp_obj.get("hypotheses", [])
                hypotheses = []
                for h in hyp_list:
                    if isinstance(h, dict):
                        hypotheses.append(h.get("hypothesis", str(h)))
                    else:
                        hypotheses.append(str(h))
            except json.JSONDecodeError:
                hypotheses = [hyp_resp.strip()]
        except Exception as e:
            hypotheses = [f"[ERROR] Stage 2 failed: {e}"]

        elapsed = time.time() - t0

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=hypotheses,
            raw_responses=raw_responses,
            elapsed_seconds=elapsed,
        )

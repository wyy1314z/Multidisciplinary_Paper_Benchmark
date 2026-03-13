"""
baseline/adapters/vanilla_llm.py — Vanilla LLM baseline adapter。

最简单的 baseline：直接让 LLM 根据论文信息生成假设，
不做任何概念抽取、关系构建或结构化约束。

对应学术界常见的 "zero-shot hypothesis generation" 设定，
类似 Si et al. (2024) 的实验设计。
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import BaseHypothesisAdapter, PaperInput, HypothesisOutput


VANILLA_SYSTEM = """You are a scientific research expert. Given a paper's title and abstract, \
generate novel, specific, and testable research hypotheses that could extend or build upon this work.

Requirements:
- Each hypothesis should be specific and falsifiable
- Hypotheses should go beyond what is stated in the abstract
- Consider cross-disciplinary connections where relevant
- Output as a JSON object: {"hypotheses": ["hypothesis 1", "hypothesis 2", ...]}"""

VANILLA_USER_TEMPLATE = """Paper Title: {title}

Abstract: {abstract}

Primary Discipline: {primary}
Related Disciplines: {secondary}

Please generate {num} novel research hypotheses based on this paper. \
Output strictly as JSON: {{"hypotheses": [...]}}"""


class VanillaLLMAdapter(BaseHypothesisAdapter):
    """Vanilla LLM：直接 prompt 生成自由文本假设。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"VanillaLLM-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        user_msg = VANILLA_USER_TEMPLATE.format(
            title=paper.title,
            abstract=paper.abstract,
            primary=paper.primary_discipline or "N/A",
            secondary=", ".join(paper.secondary_disciplines) if paper.secondary_disciplines else "N/A",
            num=num_hypotheses,
        )
        messages = [
            {"role": "system", "content": VANILLA_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        t0 = time.time()
        try:
            resp = chat_completion_with_retry(messages, temperature=0.7)
            raw_responses = [resp]
            # 尝试解析 JSON
            try:
                obj = json.loads(resp)
                hypotheses = obj.get("hypotheses", [resp])
            except json.JSONDecodeError:
                hypotheses = [resp.strip()]
        except Exception as e:
            raw_responses = [str(e)]
            hypotheses = [f"[ERROR] {e}"]

        elapsed = time.time() - t0

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=hypotheses,
            raw_responses=raw_responses,
            elapsed_seconds=elapsed,
        )

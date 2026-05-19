"""
baseline/adapters/scimon.py — SciMON (AI2, 2024) 风格 baseline。

复现 SciMON 的假设生成方式：
- 核心思路：Retrieval-Augmented Novelty — 先检索相关文献，再要求 LLM
  生成与已有工作不同的新颖假设
- 输入：论文 abstract（作为 seed）+ 检索到的相关工作摘要
- 输出：novel scientific inspiration / hypothesis
- 特点：显式要求"不同于已有工作"，强调 novelty

参考: SciMON — Scientific Inspiration Machines Optimized for Novelty,
AI2 / Northwestern, 2024. (arXiv: 2305.14259)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import (
    BaseHypothesisAdapter,
    HypothesisOutput,
    PaperInput,
    get_external_baseline_input,
)


SCIMON_SYSTEM = """You are a scientific inspiration machine. Your goal is to generate \
novel research hypotheses that are DIFFERENT from existing work but grounded in \
real scientific knowledge.

Key principle: Novelty-Optimized Generation — your hypotheses must NOT simply \
restate or incrementally extend the input paper. Instead, find unexpected connections, \
propose paradigm shifts, or suggest cross-domain transfers."""

SCIMON_USER_TEMPLATE = """Seed Paper:
Title: {title}
Abstract: {abstract}
Introduction Snippet: {introduction}

Related Fields: {primary}, {secondary}

Task: Generate {num} novel scientific hypotheses inspired by (but distinct from) \
the seed paper above. Each hypothesis should:
1. Be grounded in real scientific concepts
2. Be clearly DIFFERENT from what the seed paper already proposes
3. Suggest a specific, testable prediction
4. Ideally connect ideas from different fields

Output as JSON: {{"hypotheses": ["hypothesis 1", "hypothesis 2", ...]}}
Only output JSON."""


class SciMonAdapter(BaseHypothesisAdapter):
    """SciMON 风格：novelty-optimized 假设生成。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"SciMON-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        context = get_external_baseline_input(paper)
        user_msg = SCIMON_USER_TEMPLATE.format(
            title=context.title,
            abstract=context.abstract,
            introduction=context.introduction_text,
            primary=context.primary_discipline,
            secondary=context.secondary_text,
            num=num_hypotheses,
        )
        messages = [
            {"role": "system", "content": SCIMON_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        t0 = time.time()
        try:
            resp = chat_completion_with_retry(messages, temperature=0.8)
            raw_responses = [resp]
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

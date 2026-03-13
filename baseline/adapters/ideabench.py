"""
baseline/adapters/ideabench.py — IdeaBench 风格 baseline adapter。

复现 IdeaBench 的假设生成方式：
- 输入：论文 abstract + 参考文献 abstract（此处简化为仅用目标论文 abstract）
- Prompt：biomedical researcher 角色，给定 background abstracts，生成 novel hypothesis
- 输出：自由文本假设段落
- 评估：BERTScore, ROUGE, BLEU, LLM overlap rating

这是最典型的"单句/段落假设"生成范式。
"""
from __future__ import annotations

import time
from typing import Optional

from baseline.common import BaseHypothesisAdapter, PaperInput, HypothesisOutput


# IdeaBench 原始 prompt 模板（从 IdeaBench/src/generation/generate_hypotheses.py 提取）
IDEABENCH_SYSTEM = (
    "You are a biomedical researcher. You are tasked with creating a hypothesis "
    "or research idea given some background knowledge."
)

IDEABENCH_USER_TEMPLATE = """Here is the background information:

Title: {title}

Abstract: {abstract}

Using this information, reason over it and come up with a novel hypothesis. \
Please avoid copying ideas directly, rather use the insights to inspire a novel \
hypothesis in the form of a brief and concise paragraph."""


class IdeaBenchAdapter(BaseHypothesisAdapter):
    """IdeaBench 风格：自由文本假设生成。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"IdeaBench-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        user_msg = IDEABENCH_USER_TEMPLATE.format(
            title=paper.title,
            abstract=paper.abstract,
        )
        messages = [
            {"role": "system", "content": IDEABENCH_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        hypotheses = []
        raw_responses = []
        t0 = time.time()

        for _ in range(num_hypotheses):
            try:
                resp = chat_completion_with_retry(messages, temperature=0.7)
                hypotheses.append(resp.strip())
                raw_responses.append(resp)
            except Exception as e:
                hypotheses.append(f"[ERROR] {e}")
                raw_responses.append(str(e))

        elapsed = time.time() - t0

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=hypotheses,
            raw_responses=raw_responses,
            elapsed_seconds=elapsed,
        )

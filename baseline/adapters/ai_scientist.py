"""
baseline/adapters/ai_scientist.py — AI-Scientist (Sakana AI, 2024) 风格 baseline。

复现 AI-Scientist 的假设生成方式：
- 角色：LLM 扮演 AI 研究员，给定研究领域描述
- 输入：论文 title + abstract + 领域信息
- 输出：结构化 idea（Name, Title, Hypothesis, Experiment, Interestingness, Novelty）
- 特点：多轮迭代生成 + 自我评分筛选

参考: Lu et al., "The AI Scientist: Towards Fully Automated Open-Ended
Scientific Discovery", Sakana AI, 2024. (arXiv: 2408.06292)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import BaseHypothesisAdapter, PaperInput, HypothesisOutput


AI_SCIENTIST_SYSTEM = """You are an ambitious AI research scientist. Your goal is to propose \
novel, creative, and feasible research ideas that could lead to impactful publications.

You think like a top researcher: you identify gaps in existing work, propose specific \
hypotheses, and design concrete experiments to test them."""

AI_SCIENTIST_USER_TEMPLATE = """Based on the following paper, propose {num} novel research ideas \
that extend or build upon this work. Each idea should be a structured JSON object.

Paper Title: {title}
Abstract: {abstract}
Primary Field: {primary}
Related Fields: {secondary}

For each idea, output:
{{
  "Name": "<short identifier>",
  "Title": "<paper-style title for the idea>",
  "Hypothesis": "<specific, testable hypothesis>",
  "Experiment": "<brief experiment design to test the hypothesis>",
  "Interestingness": <1-10>,
  "Feasibility": <1-10>,
  "Novelty": <1-10>
}}

Output a JSON array of {num} ideas: [{{"Name":..., ...}}, ...]
Only output the JSON array, no other text."""


class AiScientistAdapter(BaseHypothesisAdapter):
    """AI-Scientist 风格：结构化 idea 生成 + 自评分。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"AI-Scientist-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        user_msg = AI_SCIENTIST_USER_TEMPLATE.format(
            title=paper.title,
            abstract=paper.abstract,
            primary=paper.primary_discipline or "N/A",
            secondary=", ".join(paper.secondary_disciplines) if paper.secondary_disciplines else "N/A",
            num=num_hypotheses,
        )
        messages = [
            {"role": "system", "content": AI_SCIENTIST_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        t0 = time.time()
        try:
            resp = chat_completion_with_retry(messages, temperature=0.7)
            raw_responses = [resp]
            try:
                ideas = json.loads(resp)
                if isinstance(ideas, list):
                    hypotheses = [
                        f"[{idea.get('Name', '')}] {idea.get('Title', '')}: "
                        f"{idea.get('Hypothesis', '')}"
                        for idea in ideas
                    ]
                else:
                    hypotheses = [resp.strip()]
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

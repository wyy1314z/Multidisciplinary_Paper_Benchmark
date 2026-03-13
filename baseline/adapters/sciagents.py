"""
baseline/adapters/sciagents.py — SciAgents (MIT, 2024) 风格 baseline。

复现 SciAgents 的假设生成方式：
- 核心思路：Multi-agent graph reasoning — 多个 LLM agent 分工协作，
  通过知识图谱推理生成跨领域假设
- Agent 角色：Ontologist（概念定义）→ Scientist（假设生成）→ Critic（评审）
- 输入：论文信息 + 学科知识
- 输出：经过多轮 agent 对话后的精炼假设
- 特点：模拟科研团队的协作过程

参考: Ghafarollahi & Buehler, "SciAgents: Automating scientific discovery
through multi-agent intelligent graph reasoning", MIT, 2024. (arXiv: 2409.05556)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from baseline.common import BaseHypothesisAdapter, PaperInput, HypothesisOutput


ONTOLOGIST_PROMPT = """You are the Ontologist agent. Your role is to analyze a scientific \
paper and define the key concepts, their relationships, and the knowledge domain structure.

Paper Title: {title}
Abstract: {abstract}
Primary Field: {primary}
Related Fields: {secondary}

Identify and output:
1. Key concepts (5-8 domain-specific terms)
2. Relationships between concepts
3. Knowledge gaps or unexplored connections

Output as JSON:
{{"concepts": ["..."], "relationships": ["A -> relates_to -> B", ...], "gaps": ["..."]}}
Only output JSON."""

SCIENTIST_PROMPT = """You are the Scientist agent. Based on the ontological analysis below, \
propose novel research hypotheses that bridge knowledge gaps.

Ontological Analysis:
{ontology}

Original Paper:
Title: {title}
Abstract: {abstract}

Generate {num} novel hypotheses. Each should:
1. Address an identified knowledge gap
2. Connect concepts from different domains
3. Be specific and testable

Output as JSON: {{"hypotheses": [
  {{"gap_addressed": "...", "hypothesis": "...", "mechanism": "...", "testable_prediction": "..."}},
  ...
]}}
Only output JSON."""

CRITIC_PROMPT = """You are the Critic agent. Evaluate and refine the following hypotheses \
for scientific rigor, novelty, and feasibility.

Original Paper Context:
Title: {title}

Proposed Hypotheses:
{hypotheses}

For each hypothesis, provide:
1. A refined version (more specific, more testable)
2. Strengths and weaknesses
3. A score (1-10) for novelty, feasibility, and impact

Output as JSON: {{"refined_hypotheses": [
  {{"original": "...", "refined": "...", "novelty": <1-10>, "feasibility": <1-10>, "impact": <1-10>}},
  ...
]}}
Only output JSON."""


class SciAgentsAdapter(BaseHypothesisAdapter):
    """SciAgents 风格：multi-agent 协作假设生成。"""

    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key

    @property
    def name(self) -> str:
        return f"SciAgents-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        t0 = time.time()
        raw_responses = []

        # Agent 1: Ontologist
        onto_msg = ONTOLOGIST_PROMPT.format(
            title=paper.title,
            abstract=paper.abstract,
            primary=paper.primary_discipline or "N/A",
            secondary=", ".join(paper.secondary_disciplines) if paper.secondary_disciplines else "N/A",
        )
        try:
            onto_resp = chat_completion_with_retry(
                [{"role": "user", "content": onto_msg}], temperature=0.3,
            )
            raw_responses.append(onto_resp)
        except Exception as e:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=[f"[ERROR] Ontologist failed: {e}"],
                elapsed_seconds=time.time() - t0,
            )

        # Agent 2: Scientist
        sci_msg = SCIENTIST_PROMPT.format(
            ontology=onto_resp,
            title=paper.title,
            abstract=paper.abstract,
            num=num_hypotheses,
        )
        try:
            sci_resp = chat_completion_with_retry(
                [{"role": "user", "content": sci_msg}], temperature=0.7,
            )
            raw_responses.append(sci_resp)
        except Exception as e:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=[f"[ERROR] Scientist failed: {e}"],
                raw_responses=raw_responses,
                elapsed_seconds=time.time() - t0,
            )

        # Agent 3: Critic (refine)
        critic_msg = CRITIC_PROMPT.format(
            title=paper.title,
            hypotheses=sci_resp,
        )
        try:
            critic_resp = chat_completion_with_retry(
                [{"role": "user", "content": critic_msg}], temperature=0.3,
            )
            raw_responses.append(critic_resp)
        except Exception as e:
            # Critic 失败时退回 Scientist 的结果
            critic_resp = sci_resp

        # 解析最终结果
        hypotheses = []
        try:
            obj = json.loads(critic_resp)
            refined = obj.get("refined_hypotheses", [])
            for h in refined:
                if isinstance(h, dict):
                    hypotheses.append(h.get("refined", h.get("original", str(h))))
                else:
                    hypotheses.append(str(h))
        except json.JSONDecodeError:
            # fallback: 尝试解析 Scientist 的输出
            try:
                obj = json.loads(sci_resp)
                for h in obj.get("hypotheses", []):
                    if isinstance(h, dict):
                        hypotheses.append(h.get("hypothesis", str(h)))
                    else:
                        hypotheses.append(str(h))
            except json.JSONDecodeError:
                hypotheses = [sci_resp.strip()]

        elapsed = time.time() - t0

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=hypotheses,
            raw_responses=raw_responses,
            elapsed_seconds=elapsed,
        )

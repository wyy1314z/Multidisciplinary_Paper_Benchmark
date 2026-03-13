"""
baseline/adapters/prompt_level.py — P1–P5 prompt 梯度消融 adapter。

对同一篇论文，使用 P1–P5 五种不同信息量的 prompt 生成假设，
用于消融实验：评估不同引导程度对跨学科假设生成质量的影响。

| 级别 | Query       | 论文信息            | 结构化知识        | 格式约束            |
|------|-------------|--------------------|-----------------|--------------------|
| P1   | L1 only     | 无                 | 无              | 自由文本            |
| P2   | L1 + L2     | abstract + 学科角色 | 无              | 自由文本            |
| P3   | L1+L2+L3    | abstract + 学科角色 | 概念列表         | 半结构化            |
| P4   | L1+L2+L3    | abstract + 学科角色 | 概念 + 关系      | 半结构化（含推理链） |
| P5   | L1+L2+L3    | 完整结构化摘要      | 概念+关系+路径约束 | 严格 3-step 路径    |
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from baseline.common import (
    BaseHypothesisAdapter,
    HypothesisOutput,
    HypothesisPath,
    PaperInput,
)
from crossdisc_extractor.prompts.hypothesis_prompt_levels import (
    PromptLevel,
    build_messages,
    build_p5_all_levels,
)


class PromptLevelAdapter(BaseHypothesisAdapter):
    """
    P1–P5 prompt 梯度 adapter。

    通过 prompt_level 参数控制使用哪种级别的 prompt。
    P1–P4 生成自由文本假设，P5 生成结构化路径假设。
    """

    def __init__(
        self,
        prompt_level: str = "P1",
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
    ):
        self._level = PromptLevel(prompt_level)
        self._model_name = model_name
        self._api_key = api_key
        self._temperature = temperature

    @property
    def name(self) -> str:
        return f"PromptLevel-{self._level.value}-{self._model_name}"

    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        if self._level == PromptLevel.P5:
            return self._generate_p5(paper, num_hypotheses)
        return self._generate_free_text(paper, num_hypotheses)

    # ------------------------------------------------------------------
    #  P1–P4: 自由文本生成
    # ------------------------------------------------------------------

    def _generate_free_text(
        self, paper: PaperInput, num_hypotheses: int,
    ) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry

        # 从 PaperInput 中提取 query 信息
        queries = paper.queries or {}
        l1_query = queries.get("一级", "")
        l2_queries = queries.get("二级", [])
        l3_queries = queries.get("三级", [])

        if not l1_query:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=["[ERROR] No L1 query available"],
                elapsed_seconds=0.0,
            )

        # 准备概念和关系（P3/P4 需要）
        concepts = paper.concepts
        relations = paper.relations

        messages = build_messages(
            self._level,
            l1_query=l1_query,
            l2_queries=l2_queries if self._level.value >= "P2" else None,
            l3_queries=l3_queries if self._level.value >= "P3" else None,
            abstract=paper.abstract if self._level.value >= "P2" else "",
            primary=paper.primary_discipline,
            secondary_list=paper.secondary_disciplines,
            concepts=concepts if self._level.value >= "P3" else None,
            relations=relations if self._level.value >= "P4" else None,
        )

        hypotheses: List[str] = []
        raw_responses: List[str] = []
        t0 = time.time()

        for _ in range(num_hypotheses):
            try:
                resp = chat_completion_with_retry(
                    messages, temperature=self._temperature,
                )
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

    # ------------------------------------------------------------------
    #  P5: 结构化路径生成（复用 CrossDisc 管线）
    # ------------------------------------------------------------------

    def _generate_p5(
        self, paper: PaperInput, num_hypotheses: int,
    ) -> HypothesisOutput:
        from crossdisc_extractor.utils.llm import chat_completion_with_retry
        from crossdisc_extractor.prompts.hypothesis_prompt_split import (
            parse_partial_hypothesis,
        )

        # P5 需要完整的 struct 和 query_3levels
        # 通过 PaperInput 中的 concepts/relations/queries 重建
        queries = paper.queries or {}
        l1_query = queries.get("一级", "")
        if not l1_query:
            return HypothesisOutput(
                paper_id=paper.paper_id,
                method_name=self.name,
                free_text_hypotheses=["[ERROR] No queries available for P5"],
                elapsed_seconds=0.0,
            )

        # 构建 StructExtraction 和 Query3Levels 对象
        from crossdisc_extractor.schemas import (
            Concepts,
            MetaInfo,
            Query3Levels,
            StructExtraction,
        )

        meta = MetaInfo(
            title=paper.title,
            primary=paper.primary_discipline or "",
            secondary_list=paper.secondary_disciplines or [],
        )
        concepts_obj = Concepts.model_validate(paper.concepts or {})
        from crossdisc_extractor.schemas import RelationEntry
        relations_objs = []
        for r in (paper.relations or []):
            try:
                relations_objs.append(RelationEntry.model_validate(r))
            except Exception:
                continue

        struct = StructExtraction(
            meta=meta,
            概念=concepts_obj,
            跨学科关系=relations_objs,
        )
        query_3levels = Query3Levels(
            一级=l1_query,
            二级=queries.get("二级", []),
            三级=queries.get("三级", []),
        )

        all_level_messages = build_p5_all_levels(struct, query_3levels)

        structured_paths: Dict[str, List[HypothesisPath]] = {}
        free_text: List[str] = []
        raw_responses: List[str] = []
        t0 = time.time()

        for level_key, level_num, cn_key, summary_key in [
            ("L1", 1, "一级", "一级总结"),
            ("L2", 2, "二级", "二级总结"),
            ("L3", 3, "三级", "三级总结"),
        ]:
            msgs = all_level_messages[level_key]
            try:
                resp = chat_completion_with_retry(
                    msgs, temperature=self._temperature,
                )
                raw_responses.append(resp)
                parsed = parse_partial_hypothesis(resp, level_num, struct)
                raw_paths = parsed.get(cn_key, [])
                summaries = parsed.get(summary_key, [])

                paths = []
                for i, rp in enumerate(raw_paths):
                    if hasattr(rp, "__iter__"):
                        steps = [
                            s.model_dump() if hasattr(s, "model_dump") else s
                            for s in rp
                        ]
                    else:
                        steps = []
                    summary = summaries[i] if i < len(summaries) else ""
                    paths.append(HypothesisPath(steps=steps, summary=summary))
                    if summary:
                        free_text.append(f"[{level_key}] {summary}")

                if paths:
                    structured_paths[level_key] = paths

            except Exception as e:
                raw_responses.append(str(e))
                free_text.append(f"[{level_key} ERROR] {e}")

        elapsed = time.time() - t0

        return HypothesisOutput(
            paper_id=paper.paper_id,
            method_name=self.name,
            free_text_hypotheses=free_text,
            structured_paths=structured_paths,
            raw_responses=raw_responses,
            elapsed_seconds=elapsed,
        )

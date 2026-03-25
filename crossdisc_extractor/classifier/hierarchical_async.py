"""Asynchronous hierarchical classifier."""

import asyncio
import json
import logging
import re
from typing import List, Optional, Tuple, Union

from crossdisc_extractor.classifier.config import LLMConfig
from crossdisc_extractor.classifier.llm.base import BaseLLM
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy
from crossdisc_extractor.classifier.prompts.base import PromptBuilder
from crossdisc_extractor.classifier.validator import ChoiceValidator
from crossdisc_extractor.classifier.result import ClassificationResult

logger = logging.getLogger(__name__)

# Type alias: (title, abstract) or (title, abstract, introduction)
PaperInput = Union[Tuple[str, str], Tuple[str, str, str]]


class AsyncHierarchicalClassifier:
    """Classifies papers into the taxonomy hierarchy using async LLM calls."""

    def __init__(
        self,
        taxonomy: Taxonomy,
        prompt_builder: PromptBuilder,
        cfg: LLMConfig,
    ) -> None:
        self.taxonomy = taxonomy
        self.prompt_builder = prompt_builder
        self.cfg = cfg
        self.llm = BaseLLM(cfg)

    def classify(
        self,
        question: PaperInput,
        target_depth: Optional[int] = None,
    ) -> ClassificationResult:
        """Synchronous wrapper around ``classify_async``."""
        return asyncio.run(self.classify_async(question, target_depth))

    async def _assess_crossdisc_confidence(
        self,
        question: PaperInput,
        distinct_l1: List[str],
    ) -> Tuple[float, str]:
        """Call LLM to assess cross-disciplinary confidence score.

        Returns:
            (score, reason) tuple. score in [0.0, 1.0].
        """
        if not hasattr(self.prompt_builder, "build_crossdisc_confidence_prompt"):
            return 1.0, "prompt_builder does not support confidence assessment"

        introduction = question[2] if len(question) > 2 else None
        prompt = self.prompt_builder.build_crossdisc_confidence_prompt(
            title=question[0],
            abstract=question[1],
            disciplines=distinct_l1,
            introduction=introduction,
        )

        for attempt in range(self.cfg.max_retries + 1):
            raw = await self.llm.ainvoke(prompt)
            try:
                # Extract JSON from response
                m = re.search(r"\{[^{}]*\}", raw)
                if m:
                    obj = json.loads(m.group(0))
                    score = float(obj.get("score", 0.0))
                    reason = str(obj.get("reason", ""))
                    if 0.0 <= score <= 1.0:
                        return score, reason
                logger.warning(
                    "Cross-disc confidence attempt %d/%d: invalid output: %.200s",
                    attempt + 1, self.cfg.max_retries + 1, raw,
                )
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning(
                    "Cross-disc confidence attempt %d/%d: parse error: %s, raw: %.200s",
                    attempt + 1, self.cfg.max_retries + 1, e, raw,
                )

        logger.warning("Cross-disc confidence: all retries exhausted, defaulting to 0.5")
        return 0.5, "confidence assessment failed"

    async def classify_async(
        self,
        question: PaperInput,
        target_depth: Optional[int] = None,
    ) -> ClassificationResult:
        """Classify a paper through the taxonomy hierarchy asynchronously.

        Args:
            question: ``(title, abstract)`` or ``(title, abstract, introduction)``.
            target_depth: Max taxonomy depth to classify to (default: full depth).
        """
        depth = target_depth or self.taxonomy.depth()
        partial_paths: List[List[str]] = [[]]
        raw_outputs: List[str] = []

        introduction = question[2] if len(question) > 2 else None

        for level_idx in range(depth):
            next_partial: List[List[str]] = []
            level_raws: List[str] = []

            for base_path in partial_paths:
                options = self.taxonomy.children_of(base_path)
                if not options:
                    continue

                options_exp = {
                    opt: ",".join(self.taxonomy.children_of(base_path + [opt]))
                    for opt in options
                }

                k = self.cfg.max_choices_per_level + level_idx
                prompt = self.prompt_builder.build_level_prompt(
                    title=question[0],
                    abstract=question[1],
                    level_index=level_idx,
                    parent_path=base_path,
                    options=options,
                    options_exp=options_exp,
                    max_choices=k,
                    introduction=introduction,
                )

                validator = ChoiceValidator(options, max_k=k)
                choices: List[str] = []
                last_raw = ""

                for attempt in range(self.cfg.max_retries + 1):
                    raw = await self.llm.ainvoke(prompt)
                    last_raw = raw
                    items = BaseLLM.parse_bracket_list(
                        raw,
                        strict_list_regex=self.cfg.strict_list_regex,
                        bracket_inner_regex=self.cfg.bracket_inner_regex,
                        term_max_len=self.cfg.term_max_len,
                    )
                    valid_items = validator.validate_many(items)
                    if valid_items:
                        choices = valid_items
                        break
                    logger.warning(
                        "Level %d attempt %d/%d: no valid items, base_path=%s, "
                        "parsed_items=%s, raw_output=%.200s",
                        level_idx, attempt + 1, self.cfg.max_retries + 1,
                        base_path, items, raw,
                    )

                if choices:
                    level_raws.append(last_raw)
                    for ch in choices:
                        next_partial.append(base_path + [ch])
                else:
                    logger.warning(
                        "Level %d: all retries exhausted for base_path=%s",
                        level_idx, base_path,
                    )

            raw_outputs.extend(level_raws)
            partial_paths = next_partial
            if not partial_paths:
                return ClassificationResult(paths=[], raw_outputs=raw_outputs, valid=False)

        # Cross-disciplinary = multiple distinct L1 (first-level) disciplines
        distinct_l1 = {path[0] for path in partial_paths if path}
        multidisciplinary = "Yes" if len(distinct_l1) > 1 else "No"
        raw_outputs.append(f"Multidisciplinary: {multidisciplinary}")

        # Assess cross-disciplinary confidence if multiple L1 disciplines found
        crossdisc_score = None
        crossdisc_reason = ""
        if len(distinct_l1) > 1:
            crossdisc_score, crossdisc_reason = await self._assess_crossdisc_confidence(
                question, sorted(distinct_l1),
            )
            threshold = self.cfg.crossdisc_confidence_threshold
            raw_outputs.append(
                f"CrossDisc confidence: {crossdisc_score:.2f} "
                f"(threshold={threshold:.2f}, reason={crossdisc_reason})"
            )
            logger.info(
                "Cross-disc confidence=%.2f (threshold=%.2f): %s",
                crossdisc_score, threshold, crossdisc_reason,
            )

        return ClassificationResult(
            paths=partial_paths,
            raw_outputs=raw_outputs,
            valid=len(partial_paths) > 0,
            crossdisc_score=crossdisc_score,
            crossdisc_reason=crossdisc_reason,
        )

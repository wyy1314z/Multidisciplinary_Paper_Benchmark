"""Synchronous hierarchical classifier."""

import logging
from typing import List, Optional, Tuple

from crossdisc_extractor.classifier.config import LLMConfig
from crossdisc_extractor.classifier.llm.base import BaseLLM
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy
from crossdisc_extractor.classifier.prompts.base import PromptBuilder
from crossdisc_extractor.classifier.validator import ChoiceValidator
from crossdisc_extractor.classifier.result import ClassificationResult

logger = logging.getLogger(__name__)


class SyncHierarchicalClassifier:
    """Classifies a paper into the taxonomy hierarchy using synchronous LLM calls."""

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
        question: Tuple[str, str],
        target_depth: Optional[int] = None,
    ) -> ClassificationResult:
        """Classify a (title, abstract) pair through the taxonomy hierarchy.

        At each level the LLM is queried, its output parsed and validated,
        with up to ``cfg.max_retries`` retry attempts per level.
        """
        depth = target_depth or self.taxonomy.depth()
        partial_paths: List[List[str]] = [[]]
        raws: List[str] = []

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
                )

                validator = ChoiceValidator(options, max_k=k)
                choices: List[str] = []
                last_raw = ""

                for attempt in range(self.cfg.max_retries + 1):
                    raw = self.llm.invoke(prompt)
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
                        "Level %d attempt %d/%d: no valid items, base_path=%s",
                        level_idx, attempt + 1, self.cfg.max_retries + 1, base_path,
                    )

                level_raws.append(last_raw)
                if not choices:
                    logger.warning(
                        "Level %d: all retries exhausted for base_path=%s",
                        level_idx, base_path,
                    )
                    continue

                for ch in choices:
                    next_partial.append(base_path + [ch])

            raws.append("\n".join(level_raws))
            partial_paths = next_partial
            if not partial_paths:
                return ClassificationResult(paths=[], raw_outputs=raws, valid=False)

        return ClassificationResult(
            paths=partial_paths,
            raw_outputs=raws,
            valid=len(partial_paths) > 0,
        )

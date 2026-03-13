"""Abstract base class for prompt builders."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class PromptBuilder(ABC):
    """Interface for constructing level-specific classification prompts."""

    @abstractmethod
    def build_level_prompt(
        self,
        title: str,
        abstract: str,
        level_index: int,
        parent_path: List[str],
        options: List[str],
        options_exp: Dict[str, str],
        max_choices: int,
        introduction: Optional[str] = None,
    ) -> str:
        """Build a single-level selection prompt.

        Args:
            title: Paper title.
            abstract: Paper abstract.
            level_index: 0-based taxonomy level.
            parent_path: Already-selected path (e.g. ``["L1", "L2"]``).
            options: Valid labels at this level.
            options_exp: Mapping of label -> description/hint.
            max_choices: Maximum candidates to return (1..k).
            introduction: Optional paper introduction text.

        Returns:
            A fully formatted prompt string.
        """
        ...

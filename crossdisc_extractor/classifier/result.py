"""Classification result data class."""

from dataclasses import dataclass
from typing import List


@dataclass
class ClassificationResult:
    """Result of a hierarchical classification run."""

    paths: List[List[str]]
    raw_outputs: List[str]
    valid: bool

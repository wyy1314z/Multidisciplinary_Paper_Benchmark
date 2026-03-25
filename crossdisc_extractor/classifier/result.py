"""Classification result data class."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClassificationResult:
    """Result of a hierarchical classification run."""

    paths: List[List[str]]
    raw_outputs: List[str]
    valid: bool
    crossdisc_score: Optional[float] = None
    crossdisc_reason: str = ""

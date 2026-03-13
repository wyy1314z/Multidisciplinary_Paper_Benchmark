"""Taxonomy data types."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class TaxonNode:
    """A single node in the taxonomy tree."""

    name: str
    children: Dict[str, "TaxonNode"] = field(default_factory=dict)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def child_names(self) -> List[str]:
        return list(self.children.keys())

"""N-level taxonomy loader from JSON files."""

import json
import logging
from typing import Any, Dict, List, Optional

from .types import TaxonNode

logger = logging.getLogger(__name__)


class Taxonomy:
    """A generic N-level taxonomy tree.

    Expected JSON format::

        {
          "L1 name A": {
              "L2 name a1": ["L3 leaf a1-1", "L3 leaf a1-2"],
              "L2 name a2": ["L3 leaf a2-1"]
          },
          "L1 name B": { ... }
        }

    Deeper nesting (dicts of dicts) is also supported.
    """

    def __init__(self, root: Dict[str, TaxonNode]) -> None:
        self.root = root

    @classmethod
    def from_json_file(cls, path: str) -> "Taxonomy":
        """Load taxonomy from a JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Taxonomy file not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in taxonomy file {path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Taxonomy JSON root must be a dict, got {type(data).__name__}")

        root: Dict[str, TaxonNode] = {}
        for name, subtree in data.items():
            root[name] = cls._build_tree(name, subtree)
        logger.info("Loaded taxonomy with %d L1 categories from %s", len(root), path)
        return cls(root)

    @classmethod
    def _build_tree(cls, name: str, obj: Any) -> TaxonNode:
        node = TaxonNode(name=name)
        if isinstance(obj, list):
            for leaf_name in obj:
                node.children[leaf_name] = TaxonNode(name=leaf_name)
        elif isinstance(obj, dict):
            for child_name, child_obj in obj.items():
                node.children[child_name] = cls._build_tree(child_name, child_obj)
        return node

    def level1_options(self) -> List[str]:
        """Return the list of top-level category names."""
        return list(self.root.keys())

    def children_of(self, path: List[str]) -> List[str]:
        """Return child names of the node at *path*."""
        if not path:
            return self.level1_options()
        node = self._find_node(path)
        return node.child_names() if node else []

    def _find_node(self, path: List[str]) -> Optional[TaxonNode]:
        if not path:
            return TaxonNode(name="__ROOT__", children=self.root)
        cur_children = self.root
        cur_node: Optional[TaxonNode] = None
        for name in path:
            cur_node = cur_children.get(name)
            if cur_node is None:
                return None
            cur_children = cur_node.children
        return cur_node

    def is_valid_choice(self, path: List[str], choice: str) -> bool:
        """Check whether *choice* is a valid child at *path*."""
        return choice in set(self.children_of(path))

    def depth(self) -> int:
        """Return the maximum depth of the taxonomy tree."""
        def _depth(node: TaxonNode) -> int:
            if node.is_leaf:
                return 1
            return 1 + max((_depth(c) for c in node.children.values()), default=0)
        return max((_depth(n) for n in self.root.values()), default=0)

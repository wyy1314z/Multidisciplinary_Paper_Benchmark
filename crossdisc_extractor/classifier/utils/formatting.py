"""Path formatting utilities."""

from typing import List


def format_final_path(path: List[str]) -> str:
    """Format a single path as ``[L1; L2; L3]``."""
    inner = "; ".join(path)
    return f"[{inner}]"


def format_multiple_paths(paths: List[List[str]]) -> str:
    """Format multiple paths, one per line."""
    return "\n".join(format_final_path(p) for p in paths)

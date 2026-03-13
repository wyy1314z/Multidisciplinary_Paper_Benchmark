"""Output parsing utilities for raw LLM classification results."""

import re
from collections import Counter
from typing import List, Optional, Tuple


def extract_multidisciplinary(raw_outputs: List[str]) -> str:
    """Determine multidisciplinary status by majority vote across raw outputs."""
    votes: List[str] = []
    for raw in raw_outputs:
        m = re.search(r"Multidisciplinary:\s*(Yes|No)", raw)
        if m:
            votes.append(m.group(1))
    if not votes:
        return "Unknown"
    return Counter(votes).most_common(1)[0][0]


def parse_levels(block: str) -> List[Tuple[str, str]]:
    """Parse ``[[L1];[L2];[L3]]`` into ``[("1", "L1"), ("2", "L2"), ...]``."""
    levels: List[Tuple[str, str]] = []
    matches = re.findall(r"\[\[(.*?)\]\]", block)
    for m in matches:
        parts = [p.strip() for p in m.split(";")]
        for i, p in enumerate(parts, start=1):
            if i > 3:
                break
            p_clean = p.strip("[]").strip()
            if p_clean:
                levels.append((str(i), p_clean))
    return levels


def extract_discipline_levels(
    raw_outputs: List[str],
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Extract main and non-main discipline levels from raw outputs.

    Returns:
        (main_levels, non_main_levels) where each is a list of (level_num, name).
    """
    main_levels: List[Tuple[str, str]] = []
    non_main_levels: List[Tuple[str, str]] = []

    for raw in raw_outputs:
        m = re.search(r"Multidisciplinary:\s*(Yes|No)", raw)
        if not m or m.group(1) != "Yes":
            continue

        main_match = re.search(r"Main discipline:\s*(\[\[.*?\]\])", raw, re.DOTALL)
        main_blocks = re.findall(r"\[\[.*?\]\]", main_match.group(1)) if main_match else []
        all_blocks = re.findall(r"\[\[.*?\]\]", raw)

        for blk in main_blocks:
            main_levels.extend(parse_levels(blk))
        for blk in all_blocks:
            if blk not in main_blocks:
                non_main_levels.extend(parse_levels(blk))

    return main_levels, non_main_levels


def extract_main_discipline(raw_outputs: List[str]) -> str:
    """Extract the main discipline path string from raw outputs."""
    for raw in raw_outputs:
        m = re.search(r"Main discipline:\s*(\[\[.*?\]\](?:;\[.*?\])*)", raw, re.DOTALL)
        if m:
            return m.group(1).strip()
    return "Unknown"


def _match_main_path(paths: List[List[str]], raw_outputs: List[str]) -> int:
    """Find the index in *paths* that best matches the LLM's Main discipline hint."""
    main_disc_raw = extract_main_discipline(raw_outputs)
    if main_disc_raw == "Unknown":
        return 0

    # Parse terms from the Main discipline string
    main_terms: List[str] = []
    for m in re.findall(r"\[\[(.*?)\]\]", main_disc_raw):
        for part in m.split(";"):
            t = part.strip().strip("[]").strip()
            if t:
                main_terms.append(t)

    if not main_terms:
        return 0

    best_idx, best_score = 0, -1
    for idx, path in enumerate(paths):
        score = sum(1 for t in main_terms if t in path)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def levels_from_paths(
    paths: List[List[str]],
    raw_outputs: List[str],
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Derive (main_levels, non_main_levels) from validated taxonomy paths.

    Unlike ``extract_discipline_levels`` which re-parses raw LLM text (and may
    assign wrong level numbers), this function uses the already-validated
    ``ClassificationResult.paths`` so that each discipline name is guaranteed
    to sit at its correct taxonomy level.

    Args:
        paths: Validated taxonomy paths from ClassificationResult.paths.
        raw_outputs: Raw LLM outputs (used only to identify the main discipline).

    Returns:
        (main_levels, non_main_levels) — each a list of ``(level_num, name)`` tuples.
    """
    if not paths:
        return [], []

    if len(paths) == 1:
        main_levels = [(str(i + 1), name) for i, name in enumerate(paths[0])]
        return main_levels, []

    # Multiple paths — determine which is the main discipline
    main_path_idx = _match_main_path(paths, raw_outputs)

    main_levels = [(str(i + 1), name) for i, name in enumerate(paths[main_path_idx])]
    non_main_levels: List[Tuple[str, str]] = []
    for idx, path in enumerate(paths):
        if idx != main_path_idx:
            non_main_levels.extend([(str(i + 1), name) for i, name in enumerate(path)])

    return main_levels, non_main_levels

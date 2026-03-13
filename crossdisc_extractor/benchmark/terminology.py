"""
crossdisc_extractor/benchmark/terminology.py

Domain terminology dictionary for grounding extracted terms.

Provides:
- Taxonomy-based term→discipline mapping from MSC hierarchy
- Fuzzy matching for term grounding (normalize + similarity)
- Support for external dictionaries (MeSH, IEEE, etc.)
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("eval_terminology")

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
# __file__ = crossdisc_extractor/benchmark/terminology.py
# → dirname x3 = project root (benchmark/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_TAXONOMY = os.path.join(_PROJECT_ROOT, "data", "msc_converted.json")
_DEFAULT_EN_ZH_MAPPING = os.path.join(_PROJECT_ROOT, "data", "discipline_mapping_en_zh.json")


# ===========================================================================
#  Term normalization helpers
# ===========================================================================

def normalize_term(text: str) -> str:
    """
    Normalize a term for matching:
    - Strip whitespace, lowercase
    - Remove parenthetical notes
    - Collapse multiple spaces
    """
    s = (text or "").strip().lower()
    # Remove content in parentheses like (包括...等)
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _text_similarity(a: str, b: str) -> float:
    """SequenceMatcher-based similarity in [0, 1]."""
    a = normalize_term(a)
    b = normalize_term(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ===========================================================================
#  TerminologyDict: taxonomy-based term grounding
# ===========================================================================

class TerminologyDict:
    """
    Manages a term→discipline mapping built from MSC taxonomy + optional
    external dictionaries.

    Features:
    - Builds flat term→discipline mapping from hierarchical taxonomy
    - Fuzzy matching for grounding extracted terms
    - Tracks all known disciplines for validation
    """

    def __init__(
        self,
        taxonomy_path: Optional[str] = None,
        en_zh_mapping_path: Optional[str] = None,
    ):
        self.term_to_discipline: Dict[str, str] = {}
        self.term_to_path: Dict[str, List[str]] = {}
        self.all_disciplines: Set[str] = set()
        self.all_terms: Set[str] = set()

        # Normalized term → original term (for reverse lookup)
        self._norm_index: Dict[str, str] = {}

        # English→Chinese discipline mapping (for bilingual grounding)
        self._en_to_zh_discipline: Dict[str, str] = {}

        tax_path = taxonomy_path or _DEFAULT_TAXONOMY
        if os.path.exists(tax_path):
            self._load_taxonomy(tax_path)
        else:
            logger.warning("Taxonomy file not found: %s", tax_path)

        # Load bilingual mapping
        mapping_path = en_zh_mapping_path or _DEFAULT_EN_ZH_MAPPING
        if os.path.exists(mapping_path):
            self._load_en_zh_mapping(mapping_path)

        logger.info(
            "Loaded terminology dictionary: %d terms, %d disciplines",
            len(self.term_to_discipline),
            len(self.all_disciplines),
        )

    def _load_taxonomy(self, path: str) -> None:
        """Load MSC-style hierarchical taxonomy and flatten it."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._walk_taxonomy(data, [])

    def _walk_taxonomy(
        self, tree: Dict[str, Any], path: List[str]
    ) -> None:
        """Recursively walk taxonomy tree, registering every node as a term."""
        for key, value in tree.items():
            current_path = path + [key]
            # The top-level key is the discipline
            discipline = current_path[0] if current_path else "unknown"

            # Register this node as a term
            norm_key = normalize_term(key)
            self.term_to_discipline[norm_key] = discipline
            self.term_to_path[norm_key] = current_path
            self.all_disciplines.add(discipline)
            self.all_terms.add(norm_key)
            self._norm_index[norm_key] = key

            if isinstance(value, dict) and value:
                self._walk_taxonomy(value, current_path)
            elif isinstance(value, list):
                # Leaf list entries are also terms
                for item in value:
                    if isinstance(item, str) and item.strip():
                        norm_item = normalize_term(item)
                        self.term_to_discipline[norm_item] = discipline
                        self.term_to_path[norm_item] = current_path + [item]
                        self.all_terms.add(norm_item)
                        self._norm_index[norm_item] = item

    def add_external_terms(self, terms: Dict[str, str]) -> None:
        """
        Add external dictionary entries: {term: discipline}.
        e.g. from MeSH, IEEE Thesaurus, ACM CCS.
        """
        for term, disc in terms.items():
            norm = normalize_term(term)
            if norm:
                self.term_to_discipline[norm] = disc
                self.all_terms.add(norm)
                self.all_disciplines.add(disc)
                self._norm_index[norm] = term

    def _load_en_zh_mapping(self, path: str) -> None:
        """
        Load English-Chinese bilingual mapping for discipline and term grounding.

        The mapping file has three sections:
        - "disciplines": {zh_name: [en_alias1, en_alias2, ...]}
        - "subdisciplines": {zh_name: [en_alias1, en_alias2, ...]}
        - "common_terms": {en_term: zh_discipline}
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Failed to load EN-ZH mapping: %s", e)
            return

        # 1) Discipline aliases: register English names → Chinese discipline
        for section in ("disciplines", "subdisciplines"):
            for zh_name, en_aliases in data.get(section, {}).items():
                for en_alias in en_aliases:
                    norm_en = normalize_term(en_alias)
                    if norm_en:
                        self._en_to_zh_discipline[norm_en] = zh_name
                        # Also register as terms in the dictionary
                        # so English terms can be looked up directly
                        disc = self.term_to_discipline.get(
                            normalize_term(zh_name)
                        )
                        if disc:
                            self.term_to_discipline[norm_en] = disc
                            self.all_terms.add(norm_en)
                            self._norm_index[norm_en] = en_alias

        # 2) Common scientific terms: register with discipline
        for en_term, zh_disc in data.get("common_terms", {}).items():
            norm_en = normalize_term(en_term)
            if norm_en:
                self.term_to_discipline[norm_en] = zh_disc
                self.all_terms.add(norm_en)
                self.all_disciplines.add(zh_disc)
                self._norm_index[norm_en] = en_term
                self._en_to_zh_discipline[norm_en] = zh_disc

        logger.info(
            "Loaded EN-ZH mapping: %d English aliases",
            len(self._en_to_zh_discipline),
        )

    def resolve_discipline_name(self, name: str) -> str:
        """
        Resolve a discipline name to its canonical Chinese form.
        Handles English names, abbreviations, and Chinese names.
        """
        if not name:
            return name
        norm = normalize_term(name)
        # Already a known Chinese discipline?
        if norm in {normalize_term(d) for d in self.all_disciplines}:
            return name
        # English → Chinese mapping?
        zh = self._en_to_zh_discipline.get(norm)
        if zh:
            return zh
        return name

    def lookup(self, term: str) -> Optional[str]:
        """
        Exact lookup after normalization.
        Returns discipline if found, None otherwise.
        """
        norm = normalize_term(term)
        return self.term_to_discipline.get(norm)

    def fuzzy_match(
        self,
        term: str,
        threshold: float = 0.75,
        top_k: int = 3,
    ) -> List[Tuple[str, str, float]]:
        """
        Fuzzy match a term against the dictionary.

        Returns: List of (matched_term, discipline, similarity) sorted by
        similarity descending. Only matches with similarity >= threshold.
        """
        norm_query = normalize_term(term)
        if not norm_query:
            return []

        # Exact match first
        if norm_query in self.term_to_discipline:
            orig = self._norm_index.get(norm_query, term)
            return [(orig, self.term_to_discipline[norm_query], 1.0)]

        # Fuzzy search
        candidates: List[Tuple[str, str, float]] = []
        for norm_term, disc in self.term_to_discipline.items():
            sim = _text_similarity(norm_query, norm_term)
            if sim >= threshold:
                orig = self._norm_index.get(norm_term, norm_term)
                candidates.append((orig, disc, sim))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:top_k]

    def ground_term(
        self,
        term: str,
        threshold: float = 0.75,
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Ground a single term to the dictionary.

        Returns: (canonical_term, discipline, confidence)
        If no match found: (None, None, 0.0)
        """
        matches = self.fuzzy_match(term, threshold=threshold, top_k=1)
        if matches:
            return matches[0]
        return None, None, 0.0

    def ground_terms_batch(
        self,
        terms: List[str],
        threshold: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """
        Ground a batch of terms. Returns list of grounding results.

        Each result: {
            "original": str,
            "grounded": str | None,
            "discipline": str | None,
            "confidence": float,
            "is_grounded": bool,
        }
        """
        results = []
        for term in terms:
            canonical, disc, conf = self.ground_term(term, threshold)
            results.append({
                "original": term,
                "grounded": canonical,
                "discipline": disc,
                "confidence": conf,
                "is_grounded": canonical is not None,
            })
        return results

    def get_discipline_terms(self, discipline: str) -> List[str]:
        """Get all terms belonging to a specific discipline."""
        norm_disc = normalize_term(discipline)
        result = []
        for norm_term, disc in self.term_to_discipline.items():
            if normalize_term(disc) == norm_disc:
                orig = self._norm_index.get(norm_term, norm_term)
                result.append(orig)
        return result

    def is_cross_disciplinary(self, term_a: str, term_b: str) -> bool:
        """Check if two terms belong to different disciplines."""
        disc_a = self.lookup(term_a)
        disc_b = self.lookup(term_b)
        if disc_a is None or disc_b is None:
            return False  # Can't determine
        return disc_a != disc_b

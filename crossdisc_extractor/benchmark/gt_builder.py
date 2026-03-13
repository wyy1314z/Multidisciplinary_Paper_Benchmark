"""
crossdisc_extractor/benchmark/gt_builder.py

Evidence-grounded Ground Truth construction pipeline.

Architecture:
  Stage 1: Constrained terminology extraction (LLM + dictionary grounding)
  Stage 2: Evidence-based relation construction (co-occurrence + LLM classification)
  Stage 3: Graph traversal for path construction (no LLM generation)

Each GT edge carries an evidence sentence from the original paper,
making the entire GT traceable and verifiable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from itertools import combinations, permutations
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from crossdisc_extractor.benchmark.gt_prompts import (
    PROMPT_RELATION_BATCH,
    PROMPT_TERM_EXTRACTION,
)
from crossdisc_extractor.benchmark.terminology import TerminologyDict, normalize_term

logger = logging.getLogger("gt_builder")


# ===========================================================================
#  Data structures for GT
# ===========================================================================

class GTTerm:
    """A grounded term extracted from a paper."""

    __slots__ = (
        "term", "normalized", "discipline", "evidence",
        "source", "confidence", "grounded_to", "grounding_confidence",
    )

    def __init__(
        self,
        term: str,
        normalized: str,
        discipline: str,
        evidence: str = "",
        source: str = "",
        confidence: float = 1.0,
        grounded_to: Optional[str] = None,
        grounding_confidence: float = 0.0,
    ):
        self.term = term
        self.normalized = normalized
        self.discipline = discipline
        self.evidence = evidence
        self.source = source
        self.confidence = confidence
        self.grounded_to = grounded_to
        self.grounding_confidence = grounding_confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "normalized": self.normalized,
            "discipline": self.discipline,
            "evidence": self.evidence,
            "source": self.source,
            "confidence": self.confidence,
            "grounded_to": self.grounded_to,
            "grounding_confidence": self.grounding_confidence,
        }


class GTRelation:
    """An evidence-backed relation between two terms."""

    __slots__ = (
        "head", "tail", "relation_type", "relation_detail",
        "evidence_sentence", "confidence", "source_method",
    )

    def __init__(
        self,
        head: str,
        tail: str,
        relation_type: str,
        relation_detail: str = "",
        evidence_sentence: str = "",
        confidence: float = 1.0,
        source_method: str = "cooccurrence",
    ):
        self.head = head
        self.tail = tail
        self.relation_type = relation_type
        self.relation_detail = relation_detail
        self.evidence_sentence = evidence_sentence
        self.confidence = confidence
        self.source_method = source_method

    def to_dict(self) -> Dict[str, Any]:
        return {
            "head": self.head,
            "tail": self.tail,
            "relation_type": self.relation_type,
            "relation_detail": self.relation_detail,
            "evidence_sentence": self.evidence_sentence,
            "confidence": self.confidence,
            "source_method": self.source_method,
        }


class GTPath:
    """A ground truth path derived from graph traversal."""

    __slots__ = ("steps", "disciplines_crossed", "total_evidence_confidence")

    def __init__(
        self,
        steps: List[Dict[str, Any]],
        disciplines_crossed: List[str],
        total_evidence_confidence: float = 1.0,
    ):
        self.steps = steps
        self.disciplines_crossed = disciplines_crossed
        self.total_evidence_confidence = total_evidence_confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.steps,
            "disciplines_crossed": self.disciplines_crossed,
            "total_evidence_confidence": self.total_evidence_confidence,
        }


# ===========================================================================
#  Text utilities
# ===========================================================================

def _split_sentences(text: str) -> List[str]:
    """
    Split Chinese/English mixed text into sentences.
    Handles: 。！？; . ! ? and newlines.
    """
    if not text:
        return []
    # Split on sentence-ending punctuation
    parts = re.split(r'(?<=[。！？；.!?])\s*|\n+', text)
    sentences = []
    for p in parts:
        p = p.strip()
        if len(p) >= 5:  # skip very short fragments
            sentences.append(p)
    return sentences


def _find_terms_in_sentence(
    sentence: str,
    term_set: Dict[str, str],
) -> List[str]:
    """
    Find which terms appear in a sentence.
    term_set: {normalized_term: original_term}
    Returns list of original terms found.
    """
    sentence_lower = sentence.lower()
    found = []
    for norm, orig in term_set.items():
        if norm in sentence_lower or orig.lower() in sentence_lower:
            found.append(orig)
    return found


def _parse_json_response(response: str) -> Dict[str, Any]:
    """Parse JSON from LLM response, handling markdown fences."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("\n", 1)[0] if "\n" in cleaned else cleaned[:-3]
    # Remove json language tag if present
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


# ===========================================================================
#  Stage 1: Constrained Terminology Extraction
# ===========================================================================

def extract_terms(
    title: str,
    abstract: str,
    introduction: str,
    terminology_dict: TerminologyDict,
    llm_fn: Optional[Any] = None,
    grounding_threshold: float = 0.70,
    parsed_concepts: Optional[Dict[str, Any]] = None,
    primary_discipline: str = "",
) -> List[GTTerm]:
    """
    Extract domain-specific terms from paper text.

    Strategy (priority order):
    1. If parsed_concepts is provided: use LLM-extracted concepts from
       the production pipeline (high quality, already validated)
    2. If llm_fn is provided: use LLM with constrained prompt
    3. Fallback: heuristic extraction from text

    All extracted terms are then grounded against the terminology dictionary.
    """
    raw_terms: List[Dict[str, Any]] = []
    has_primary_source = False

    if parsed_concepts:
        raw_terms = _extract_terms_from_parsed(
            parsed_concepts, primary_discipline=primary_discipline
        )
        has_primary_source = True
    elif llm_fn is not None:
        raw_terms = _extract_terms_via_llm(
            title, abstract, introduction, llm_fn
        )
        has_primary_source = True

    # Supplement with heuristic extraction from text
    heuristic_terms = _extract_terms_from_text(
        title, abstract, introduction
    )
    raw_terms.extend(heuristic_terms)

    # Ground each term against dictionary
    gt_terms: List[GTTerm] = []
    seen_normalized: Set[str] = set()

    for raw in raw_terms:
        term = (raw.get("term") or "").strip()
        normalized = (raw.get("normalized") or term).strip()
        if not term:
            continue

        norm_key = normalize_term(normalized)
        if norm_key in seen_normalized:
            continue
        seen_normalized.add(norm_key)

        discipline = (raw.get("discipline") or "").strip()
        evidence = (raw.get("evidence") or "").strip()
        source = (raw.get("source") or "").strip()
        confidence = float(raw.get("confidence", 0.8))
        is_heuristic = source.startswith("heuristic") or source in (
            "acronym", "sci_phrase", "hyphenated", "capitalized", "zh_heuristic",
        )

        # Resolve discipline name (English → Chinese if needed)
        if discipline:
            discipline = terminology_dict.resolve_discipline_name(discipline)

        # Attempt grounding against dictionary
        grounded, grounded_disc, grounding_conf = terminology_dict.ground_term(
            normalized, threshold=grounding_threshold
        )
        # Also try grounding with the original term (may be Chinese)
        if not grounded and term != normalized:
            grounded, grounded_disc, grounding_conf = terminology_dict.ground_term(
                term, threshold=grounding_threshold
            )

        # Use grounded discipline if available and original is vague
        if grounded_disc and (not discipline or discipline == "unknown"):
            discipline = grounded_disc

        # Filter heuristic terms: when we have a primary source (parsed/LLM),
        # only keep heuristic terms that are grounded OR have a discipline
        if is_heuristic and has_primary_source:
            if not grounded and not discipline:
                continue

        gt_term = GTTerm(
            term=term,
            normalized=normalized,
            discipline=discipline,
            evidence=evidence,
            source=source,
            confidence=confidence,
            grounded_to=grounded,
            grounding_confidence=grounding_conf,
        )
        gt_terms.append(gt_term)

    return gt_terms


def _extract_terms_from_parsed(
    parsed_concepts: Dict[str, Any],
    primary_discipline: str = "",
) -> List[Dict[str, Any]]:
    """
    Extract terms from the production pipeline's LLM-parsed concepts.

    The parsed_concepts dict has the structure:
    {
        "主学科": [{"term": "...", "normalized": "...", "evidence": "...", ...}, ...],
        "辅学科": {"学科名": [{"term": "...", ...}, ...], ...}
    }

    These are high-quality terms already validated by the production pipeline,
    with both Chinese and English forms (term=中文, normalized=English).
    """
    terms: List[Dict[str, Any]] = []

    # Primary discipline concepts — assign the paper's primary discipline
    for entry in parsed_concepts.get("主学科", []):
        term = (entry.get("term") or "").strip()
        normalized = (entry.get("normalized") or term).strip()
        if not term and not normalized:
            continue
        terms.append({
            "term": term,
            "normalized": normalized,
            "discipline": primary_discipline,
            "evidence": (entry.get("evidence") or "").strip(),
            "source": "parsed_primary",
            "confidence": float(entry.get("confidence", 0.85)),
        })
        # Also add the other language form as a separate entry
        # so both "癫痫" and "Epilepsy" can be matched
        if term != normalized and normalized:
            terms.append({
                "term": normalized,
                "normalized": normalized,
                "discipline": primary_discipline,
                "evidence": (entry.get("evidence") or "").strip(),
                "source": "parsed_primary",
                "confidence": float(entry.get("confidence", 0.85)),
            })

    # Secondary discipline concepts
    for disc_name, entries in parsed_concepts.get("辅学科", {}).items():
        for entry in (entries or []):
            term = (entry.get("term") or "").strip()
            normalized = (entry.get("normalized") or term).strip()
            if not term and not normalized:
                continue
            terms.append({
                "term": term,
                "normalized": normalized,
                "discipline": disc_name,
                "evidence": (entry.get("evidence") or "").strip(),
                "source": f"parsed_secondary:{disc_name}",
                "confidence": float(entry.get("confidence", 0.80)),
            })
            if term != normalized and normalized:
                terms.append({
                    "term": normalized,
                    "normalized": normalized,
                    "discipline": disc_name,
                    "evidence": (entry.get("evidence") or "").strip(),
                    "source": f"parsed_secondary:{disc_name}",
                    "confidence": float(entry.get("confidence", 0.80)),
                })

    return terms


def _extract_terms_via_llm(
    title: str,
    abstract: str,
    introduction: str,
    llm_fn: Any,
) -> List[Dict[str, Any]]:
    """Use LLM to extract terms with evidence."""
    prompt = PROMPT_TERM_EXTRACTION.format(
        title=title,
        abstract=abstract[:3000],  # Truncate for token limits
        introduction=introduction[:5000],
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        response = llm_fn(messages, temperature=0.0)
        data = _parse_json_response(response)
        return data.get("terms", [])
    except Exception as e:
        logger.error("LLM term extraction failed: %s", e)
        return []


def _extract_terms_from_text(
    title: str,
    abstract: str,
    introduction: str,
) -> List[Dict[str, Any]]:
    """
    Fallback term extraction without LLM.

    Strategies for English text:
    - Scientific noun phrases (multi-word capitalized or known patterns)
    - Abbreviations/acronyms (e.g., EEG, FGFR, MRI)
    - Hyphenated compound terms (e.g., drug-resistant, single-cell)
    - Known scientific term patterns (e.g., "X analysis", "Y method")

    Strategies for Chinese text:
    - Multi-char sequences (2-8 chars) filtered by stopwords
    """
    text = f"{title}. {abstract}. {introduction}"
    terms: List[Dict[str, Any]] = []
    seen_norm: set = set()

    def _add_term(term: str, source: str = "heuristic", confidence: float = 0.5):
        norm = term.strip().lower()
        if not norm or norm in seen_norm:
            return
        seen_norm.add(norm)
        terms.append({
            "term": term.strip(),
            "normalized": norm,
            "discipline": "",
            "evidence": "",
            "source": source,
            "confidence": confidence,
        })

    # ── English extraction ──────────────────────────────────────────

    # 1) Acronyms / abbreviations (2-6 uppercase letters, optionally with digits)
    #    e.g., EEG, FGFR, MRI, PET-CT, CRISPR, RuO2
    acronyms = re.findall(r'\b[A-Z][A-Z0-9]{1,5}(?:-[A-Z0-9]{1,5})?\b', text)
    acro_stopwords = {
        "AND", "THE", "FOR", "BUT", "NOT", "NOR", "YET", "ARE", "WAS",
        "HAS", "HAD", "ITS", "OUR", "ALL", "CAN", "MAY", "DID", "WHO",
        "HOW", "USE", "NEW", "TWO", "ONE", "FIG", "REF", "VOL", "DOI",
    }
    for a in set(acronyms):
        if a not in acro_stopwords and len(a) >= 2:
            _add_term(a, "acronym", 0.6)

    # 2) Scientific multi-word terms: noun phrases ending with scientific suffixes
    sci_suffixes = (
        r"(?:stimulation|analysis|therapy|method|model|system|process|"
        r"mechanism|pathway|receptor|protein|enzyme|gene|cell|tissue|"
        r"material|structure|network|algorithm|technique|assay|imaging|"
        r"spectroscopy|microscopy|diffraction|resonance|scattering|"
        r"engineering|dynamics|kinetics|synthesis|oxidation|reduction|"
        r"polymerization|crystallization|fermentation|signaling|"
        r"expression|regulation|activation|inhibition|modulation|"
        r"resistance|sensitivity|specificity|selectivity|"
        r"disorder|disease|syndrome|infection|injury|"
        r"simulation|optimization|prediction|detection|"
        r"learning|processing|recognition|classification|"
        r"distribution|concentration|composition|configuration)"
    )
    # Match "Adjective/Noun + ... + ScientificNoun" patterns
    sci_phrases = re.findall(
        r'\b[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,4}\s+' + sci_suffixes + r'\b',
        text, re.IGNORECASE,
    )
    for phrase in set(sci_phrases):
        clean = phrase.strip()
        # Filter out phrases starting with common non-term words
        first_word = clean.split()[0].lower()
        if first_word in {
            "the", "a", "an", "this", "that", "these", "those", "our",
            "their", "its", "we", "they", "it", "is", "are", "was",
            "were", "has", "have", "had", "can", "may", "will", "would",
            "should", "could", "each", "every", "both", "all", "some",
            "any", "no", "not", "more", "most", "such", "other",
            "further", "recent", "previous", "current", "present",
            "several", "various", "many", "few", "new", "novel",
        }:
            # Strip the leading article/determiner
            parts = clean.split(None, 1)
            if len(parts) > 1:
                clean = parts[1]
        if len(clean.split()) >= 2:
            _add_term(clean, "sci_phrase", 0.55)

    # 3) Hyphenated compound terms (e.g., drug-resistant, single-cell, high-entropy)
    hyphenated = re.findall(r'\b[a-zA-Z]+-[a-zA-Z]+(?:-[a-zA-Z]+)*\b', text)
    hyph_stopwords = {
        "well-known", "so-called", "state-of-the-art", "up-to-date",
        "non-invasive", "non-linear", "non-trivial", "re-use",
    }
    for h in set(hyphenated):
        if h.lower() not in hyph_stopwords and len(h) >= 5:
            _add_term(h, "hyphenated", 0.45)

    # 4) Capitalized multi-word proper nouns (but filter people/places/journals)
    cap_phrases = re.findall(
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text
    )
    # Build a set of likely person names and institutional words
    person_indicators = {
        "university", "institute", "department", "hospital", "school",
        "college", "center", "centre", "laboratory", "lab", "journal",
        "press", "society", "association", "foundation", "council",
    }
    for phrase in set(cap_phrases):
        words = phrase.lower().split()
        # Skip if any word is a person/institution indicator
        if any(w in person_indicators for w in words):
            continue
        # Skip likely person names (2 words, both short)
        if len(words) == 2 and all(len(w) <= 8 for w in words):
            # Heuristic: person names are usually 2 short capitalized words
            # but scientific terms tend to be longer or have 3+ words
            continue
        if len(words) >= 2:
            _add_term(phrase, "capitalized", 0.4)

    # ── Chinese extraction ──────────────────────────────────────────

    zh_candidates = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
    zh_stopwords = {
        "我们", "他们", "这些", "那些", "可以", "已经", "因此",
        "通过", "研究", "分析", "方法", "结果", "结论", "基于",
        "本文", "目前", "进行", "提出", "表明", "发现", "认为",
        "其中", "以及", "然而", "但是", "此外", "同时", "不同",
        "之间", "一种", "主要", "重要", "显著", "有效", "相关",
    }
    for c in set(zh_candidates):
        if c not in zh_stopwords and len(c) >= 2:
            _add_term(c, "zh_heuristic", 0.5)

    return terms


# ===========================================================================
#  Stage 2: Evidence-Based Relation Construction
# ===========================================================================

def build_relations(
    terms: List[GTTerm],
    abstract: str,
    introduction: str,
    llm_fn: Optional[Any] = None,
    min_confidence: float = 0.5,
) -> List[GTRelation]:
    """
    Build evidence-backed relations between extracted terms.

    Strategy:
    1. Split text into sentences
    2. Find term co-occurrences in each sentence
    3. For co-occurring pairs: use LLM to classify relation (or heuristic)
    4. Each relation carries its evidence sentence

    Args:
        terms: List of GTTerm from Stage 1
        abstract: Paper abstract
        introduction: Paper introduction
        llm_fn: Optional LLM callable for relation classification
        min_confidence: Minimum confidence to keep a relation

    Returns:
        List of GTRelation objects
    """
    # Build term lookup: normalized → GTTerm
    # Include both Chinese and English forms for bilingual matching
    term_lookup: Dict[str, GTTerm] = {}
    term_norm_to_orig: Dict[str, str] = {}
    for t in terms:
        norm = normalize_term(t.normalized)
        term_lookup[norm] = t
        term_norm_to_orig[norm] = t.normalized
        # Also index by original term (may be Chinese while normalized is English)
        if t.term != t.normalized:
            norm_orig = normalize_term(t.term)
            if norm_orig not in term_lookup:
                term_lookup[norm_orig] = t
                term_norm_to_orig[norm_orig] = t.normalized

    # Split text into sentences
    all_text = f"{abstract}\n{introduction}"
    sentences = _split_sentences(all_text)

    # Find co-occurrences
    cooccurrence_evidence: Dict[
        Tuple[str, str], List[str]
    ] = defaultdict(list)

    for sentence in sentences:
        found = _find_terms_in_sentence(sentence, term_norm_to_orig)
        # Deduplicate: Chinese and English forms of the same term
        # both map to the same normalized form
        found = list(dict.fromkeys(found))
        if len(found) >= 2:
            for a, b in combinations(found, 2):
                # Skip self-pairs (same normalized form)
                if normalize_term(a) == normalize_term(b):
                    continue
                pair = tuple(sorted([a, b]))
                cooccurrence_evidence[pair].append(sentence)

    if not cooccurrence_evidence:
        logger.warning("No term co-occurrences found in text")
        return []

    # Classify relations
    relations: List[GTRelation] = []

    if llm_fn is not None:
        relations = _classify_relations_via_llm(
            cooccurrence_evidence, term_lookup, llm_fn, min_confidence
        )
    else:
        relations = _classify_relations_heuristic(
            cooccurrence_evidence, term_lookup, min_confidence
        )

    return relations


def _classify_relations_via_llm(
    cooccurrence_evidence: Dict[Tuple[str, str], List[str]],
    term_lookup: Dict[str, GTTerm],
    llm_fn: Any,
    min_confidence: float,
) -> List[GTRelation]:
    """Use LLM to classify relations for co-occurring term pairs."""
    relations: List[GTRelation] = []

    # Group by sentence to reduce LLM calls
    sentence_terms: Dict[str, List[str]] = defaultdict(list)
    for (a, b), sentences in cooccurrence_evidence.items():
        for sent in sentences[:2]:  # Use at most 2 evidence sentences per pair
            sentence_terms[sent].extend([a, b])

    # Deduplicate terms per sentence
    for sent in sentence_terms:
        sentence_terms[sent] = list(set(sentence_terms[sent]))

    # Batch process by sentence
    all_terms_str = "\n".join(
        f"- {t.normalized} (学科: {t.discipline})"
        for t in term_lookup.values()
    )

    for sentence, terms_in_sent in sentence_terms.items():
        if len(terms_in_sent) < 2:
            continue

        prompt = PROMPT_RELATION_BATCH.format(
            sentence=sentence,
            term_list=all_terms_str,
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            response = llm_fn(messages, temperature=0.0)
            data = _parse_json_response(response)

            for rel in data.get("relations", []):
                head = (rel.get("head") or "").strip()
                tail = (rel.get("tail") or "").strip()
                rel_type = (rel.get("relation_type") or "other").strip()
                rel_detail = (rel.get("relation_detail") or "").strip()
                conf = float(rel.get("confidence", 0.7))

                if conf < min_confidence:
                    continue
                if not head or not tail:
                    continue

                relations.append(GTRelation(
                    head=head,
                    tail=tail,
                    relation_type=rel_type,
                    relation_detail=rel_detail,
                    evidence_sentence=sentence,
                    confidence=conf,
                    source_method="llm_classification",
                ))
        except Exception as e:
            logger.warning("LLM relation classification failed for sentence: %s", e)
            continue

    return relations


def _classify_relations_heuristic(
    cooccurrence_evidence: Dict[Tuple[str, str], List[str]],
    term_lookup: Dict[str, GTTerm],
    min_confidence: float,
) -> List[GTRelation]:
    """
    Heuristic relation classification based on keyword patterns.
    Used when LLM is not available.
    """
    # Keyword → relation_type mapping
    relation_patterns = [
        (r'应用于|用于|采用|使用|applied\s+to|used\s+for', 'method_applied_to'),
        (r'提升|改善|提高|增强|优化|improve|enhance|boost', 'improves_metric'),
        (r'约束|限制|制约|constrain|limit|restrict', 'constrains'),
        (r'依赖|取决于|需要|depend|require|rely', 'depends_on'),
        (r'驱动|导致|引起|driv|caus|lead\s+to', 'driven_by'),
        (r'扩展|延伸|拓展|extend|build\s+on', 'extends'),
        (r'映射|对应|对齐|map|correspond|align', 'maps_to'),
        (r'推断|导出|来源|infer|deriv', 'inferred_from'),
        (r'相关|关联|correlat|associat|relat', 'corresponds_to'),
    ]

    relations: List[GTRelation] = []

    for (term_a, term_b), sentences in cooccurrence_evidence.items():
        best_sentence = sentences[0]  # Use first co-occurrence
        sentence_lower = best_sentence.lower()

        # Try to find relation type from keywords
        matched_type = "corresponds_to"  # default for co-occurrence
        matched_conf = 0.5

        for pattern, rel_type in relation_patterns:
            if re.search(pattern, best_sentence, re.IGNORECASE):
                matched_type = rel_type
                matched_conf = 0.6
                break

        # Determine direction from sentence order
        pos_a = best_sentence.lower().find(term_a.lower())
        pos_b = best_sentence.lower().find(term_b.lower())
        if pos_a < 0:
            pos_a = 999
        if pos_b < 0:
            pos_b = 999

        head = term_a if pos_a <= pos_b else term_b
        tail = term_b if pos_a <= pos_b else term_a

        if matched_conf >= min_confidence:
            relations.append(GTRelation(
                head=head,
                tail=tail,
                relation_type=matched_type,
                relation_detail=f"{head} {matched_type} {tail}",
                evidence_sentence=best_sentence,
                confidence=matched_conf,
                source_method="heuristic",
            ))

    return relations


# ===========================================================================
#  Stage 3: Graph Traversal for Path Construction
# ===========================================================================

def build_gt_paths(
    terms: List[GTTerm],
    relations: List[GTRelation],
    max_path_length: int = 4,
    max_paths: int = 20,
    require_cross_discipline: bool = True,
) -> List[GTPath]:
    """
    Build GT paths by traversing the concept graph.

    Paths are objective properties of the graph, not LLM generations.
    Each path step carries evidence from the original paper.

    Args:
        terms: Grounded terms from Stage 1
        relations: Evidence-backed relations from Stage 2
        max_path_length: Maximum number of edges in a path
        max_paths: Maximum number of paths to return
        require_cross_discipline: If True, only return paths crossing disciplines

    Returns:
        List of GTPath objects, sorted by cross-disciplinary span
    """
    # Build NetworkX graph
    G = nx.DiGraph()

    # Add nodes
    term_discipline: Dict[str, str] = {}
    for t in terms:
        node_id = normalize_term(t.normalized)
        G.add_node(node_id, term=t.normalized, discipline=t.discipline)
        term_discipline[node_id] = t.discipline
        # Also index by original term
        term_discipline[normalize_term(t.term)] = t.discipline

    # Add edges with evidence
    for rel in relations:
        head_id = normalize_term(rel.head)
        tail_id = normalize_term(rel.tail)

        # Ensure nodes exist (may use slightly different normalization)
        if head_id not in G:
            closest = _find_closest_node(head_id, G)
            if closest:
                head_id = closest
            else:
                G.add_node(head_id, term=rel.head, discipline="unknown")
        if tail_id not in G:
            closest = _find_closest_node(tail_id, G)
            if closest:
                tail_id = closest
            else:
                G.add_node(tail_id, term=rel.tail, discipline="unknown")

        G.add_edge(
            head_id, tail_id,
            relation_type=rel.relation_type,
            relation_detail=rel.relation_detail,
            evidence=rel.evidence_sentence,
            confidence=rel.confidence,
        )

    if G.number_of_edges() == 0:
        logger.warning("No edges in concept graph, cannot build paths")
        return []

    # Find cross-disciplinary paths
    gt_paths: List[GTPath] = []

    # Get nodes grouped by discipline
    disc_nodes: Dict[str, List[str]] = defaultdict(list)
    for node, data in G.nodes(data=True):
        disc = data.get("discipline", "unknown")
        if disc and disc != "unknown":
            disc_nodes[disc].append(node)

    disciplines = list(disc_nodes.keys())

    if require_cross_discipline and len(disciplines) >= 2:
        # Find paths between nodes in different disciplines
        for disc_a, disc_b in permutations(disciplines, 2):
            for source in disc_nodes[disc_a]:
                for target in disc_nodes[disc_b]:
                    if source == target:
                        continue
                    try:
                        # Find simple paths (no repeated nodes)
                        paths = list(nx.all_simple_paths(
                            G, source, target,
                            cutoff=max_path_length,
                        ))
                        for node_path in paths[:5]:  # Limit per source-target pair
                            gt_path = _node_path_to_gt_path(
                                node_path, G, term_discipline
                            )
                            if gt_path:
                                gt_paths.append(gt_path)
                    except nx.NetworkXError:
                        continue
    elif require_cross_discipline:
        # Cross-discipline required but only one discipline exists — no paths
        pass
    else:
        # Find all paths regardless of discipline
        for source in G.nodes():
            for target in G.nodes():
                if source == target:
                    continue
                try:
                    paths = list(nx.all_simple_paths(
                        G, source, target, cutoff=max_path_length
                    ))
                    for node_path in paths[:3]:
                        gt_path = _node_path_to_gt_path(
                            node_path, G, term_discipline
                        )
                        if gt_path:
                            gt_paths.append(gt_path)
                except nx.NetworkXError:
                    continue

    # Sort by: number of disciplines crossed (desc), confidence (desc)
    gt_paths.sort(
        key=lambda p: (len(set(p.disciplines_crossed)), p.total_evidence_confidence),
        reverse=True,
    )

    return gt_paths[:max_paths]


def _find_closest_node(target: str, G: nx.DiGraph, threshold: float = 0.75) -> Optional[str]:
    """Find the closest matching node in graph by string similarity."""
    from difflib import SequenceMatcher

    best_match = None
    best_sim = 0.0
    for node in G.nodes():
        sim = SequenceMatcher(None, target, node).ratio()
        if sim > best_sim and sim >= threshold:
            best_sim = sim
            best_match = node
    return best_match


def _node_path_to_gt_path(
    node_path: List[str],
    G: nx.DiGraph,
    term_discipline: Dict[str, str],
) -> Optional[GTPath]:
    """Convert a list of node IDs to a GTPath with evidence."""
    if len(node_path) < 2:
        return None

    steps: List[Dict[str, Any]] = []
    disciplines_seen: List[str] = []
    confidences: List[float] = []

    for i in range(len(node_path) - 1):
        src = node_path[i]
        tgt = node_path[i + 1]

        edge_data = G.edges[src, tgt]
        src_data = G.nodes[src]
        tgt_data = G.nodes[tgt]

        head_term = src_data.get("term", src)
        tail_term = tgt_data.get("term", tgt)
        head_disc = src_data.get("discipline", "unknown")
        tail_disc = tgt_data.get("discipline", "unknown")

        step = {
            "step": i + 1,
            "head": head_term,
            "tail": tail_term,
            "relation_type": edge_data.get("relation_type", "other"),
            "relation": edge_data.get("relation_detail", ""),
            "evidence": edge_data.get("evidence", ""),
            "head_discipline": head_disc,
            "tail_discipline": tail_disc,
        }
        steps.append(step)

        if head_disc and head_disc != "unknown":
            disciplines_seen.append(head_disc)
        if tail_disc and tail_disc != "unknown":
            disciplines_seen.append(tail_disc)
        confidences.append(edge_data.get("confidence", 0.5))

    total_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return GTPath(
        steps=steps,
        disciplines_crossed=list(dict.fromkeys(disciplines_seen)),  # unique, order-preserving
        total_evidence_confidence=round(total_conf, 4),
    )


# ===========================================================================
#  Main entry point: build complete Ground Truth
# ===========================================================================

def build_ground_truth(
    title: str,
    abstract: str,
    introduction: str,
    taxonomy_path: Optional[str] = None,
    llm_fn: Optional[Any] = None,
    grounding_threshold: float = 0.70,
    relation_confidence: float = 0.5,
    max_path_length: int = 4,
    max_paths: int = 20,
    parsed_concepts: Optional[Dict[str, Any]] = None,
    primary_discipline: str = "",
) -> Dict[str, Any]:
    """
    Build complete evidence-grounded Ground Truth for a paper.

    Args:
        parsed_concepts: Optional pre-extracted concepts from the production
            pipeline (item["parsed"]["概念"]). When available, these provide
            high-quality bilingual terms that significantly improve grounding.

    Returns a dict with:
    - "terms": list of grounded term dicts
    - "relations": list of evidence-backed relation dicts
    - "paths": list of graph-traversal path dicts
    - "concept_graph": {nodes, edges} for the concept graph
    - "stats": summary statistics
    """
    # Initialize terminology dictionary
    terminology_dict = TerminologyDict(taxonomy_path)

    # Stage 1: Extract and ground terms
    logger.info("Stage 1: Extracting terms from paper: %s", title[:60])
    terms = extract_terms(
        title, abstract, introduction,
        terminology_dict=terminology_dict,
        llm_fn=llm_fn,
        grounding_threshold=grounding_threshold,
        parsed_concepts=parsed_concepts,
        primary_discipline=primary_discipline,
    )
    logger.info("Extracted %d terms (%d grounded)",
                len(terms),
                sum(1 for t in terms if t.grounded_to is not None))

    if not terms:
        logger.warning("No terms extracted, returning empty GT")
        return _empty_gt()

    # Stage 2: Build evidence-based relations
    logger.info("Stage 2: Building relations from co-occurrence + classification")
    relations = build_relations(
        terms, abstract, introduction,
        llm_fn=llm_fn,
        min_confidence=relation_confidence,
    )
    logger.info("Built %d relations", len(relations))

    if not relations:
        logger.warning("No relations found, returning terms-only GT")
        return {
            "terms": [t.to_dict() for t in terms],
            "relations": [],
            "paths": [],
            "concept_graph": {"nodes": [], "edges": []},
            "stats": _compute_stats(terms, [], []),
        }

    # Stage 3: Build paths via graph traversal
    logger.info("Stage 3: Building GT paths via graph traversal")
    paths = build_gt_paths(
        terms, relations,
        max_path_length=max_path_length,
        max_paths=max_paths,
    )
    logger.info("Built %d GT paths", len(paths))

    # Build concept graph representation
    concept_graph = _build_concept_graph_dict(terms, relations)

    return {
        "terms": [t.to_dict() for t in terms],
        "relations": [r.to_dict() for r in relations],
        "paths": [p.to_dict() for p in paths],
        "concept_graph": concept_graph,
        "stats": _compute_stats(terms, relations, paths),
    }


def _empty_gt() -> Dict[str, Any]:
    return {
        "terms": [],
        "relations": [],
        "paths": [],
        "concept_graph": {"nodes": [], "edges": []},
        "stats": {"n_terms": 0, "n_relations": 0, "n_paths": 0,
                  "n_disciplines": 0, "grounding_rate": 0.0},
    }


def _build_concept_graph_dict(
    terms: List[GTTerm],
    relations: List[GTRelation],
) -> Dict[str, Any]:
    """Build a serializable concept graph dict."""
    nodes = []
    for t in terms:
        nodes.append({
            "id": normalize_term(t.normalized),
            "term": t.normalized,
            "discipline": t.discipline,
            "grounded_to": t.grounded_to,
        })

    edges = []
    for r in relations:
        edges.append({
            "source": normalize_term(r.head),
            "target": normalize_term(r.tail),
            "relation_type": r.relation_type,
            "relation_detail": r.relation_detail,
            "evidence": r.evidence_sentence,
            "confidence": r.confidence,
        })

    return {"nodes": nodes, "edges": edges}


def _compute_stats(
    terms: List[GTTerm],
    relations: List[GTRelation],
    paths: List[GTPath],
) -> Dict[str, Any]:
    """Compute summary statistics for the GT."""
    n_terms = len(terms)
    n_grounded = sum(1 for t in terms if t.grounded_to is not None)
    disciplines = set(t.discipline for t in terms if t.discipline)

    avg_path_len = 0.0
    if paths:
        avg_path_len = sum(len(p.steps) for p in paths) / len(paths)

    cross_disc_paths = sum(
        1 for p in paths
        if len(set(p.disciplines_crossed)) >= 2
    )

    return {
        "n_terms": n_terms,
        "n_grounded": n_grounded,
        "grounding_rate": round(n_grounded / max(n_terms, 1), 4),
        "n_relations": len(relations),
        "n_paths": len(paths),
        "n_cross_disciplinary_paths": cross_disc_paths,
        "n_disciplines": len(disciplines),
        "disciplines": sorted(disciplines),
        "avg_path_length": round(avg_path_len, 2),
    }

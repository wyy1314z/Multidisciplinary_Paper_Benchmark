"""Multidisciplinary classifier subpackage.

Provides hierarchical academic discipline classification using LLMs,
multidisciplinary detection, and main discipline extraction.
"""

from crossdisc_extractor.classifier.result import ClassificationResult
from crossdisc_extractor.classifier.config import LLMConfig, ProjectConfig, load_config
from crossdisc_extractor.classifier.hierarchical import SyncHierarchicalClassifier
from crossdisc_extractor.classifier.hierarchical_async import AsyncHierarchicalClassifier
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy
from crossdisc_extractor.classifier.taxonomy.types import TaxonNode
from crossdisc_extractor.classifier.prompts import DisciplinePromptBuilder, PromptBuilder
from crossdisc_extractor.classifier.llm.base import BaseLLM

__all__ = [
    "ClassificationResult",
    "LLMConfig",
    "ProjectConfig",
    "load_config",
    "SyncHierarchicalClassifier",
    "AsyncHierarchicalClassifier",
    "Taxonomy",
    "TaxonNode",
    "DisciplinePromptBuilder",
    "PromptBuilder",
    "BaseLLM",
]

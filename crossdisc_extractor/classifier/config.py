"""Unified project configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class LLMConfig:
    """LLM connection and behaviour parameters."""

    model_name: str = ""
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.0
    timeout: Optional[float] = 300
    max_retries: int = 3
    max_choices_per_level: int = 3
    term_max_len: int = 128
    crossdisc_confidence_threshold: float = 0.5

    # Output parsing patterns
    strict_list_regex: str = r"^\[(?:[^\[\]\n,]{1,128})(?:,(?:[^\[\]\n,]{1,128}))*\]$"
    bracket_inner_regex: str = r"\[([^\[\]\n]*)\]"

    def __post_init__(self) -> None:
        if not self.model_name:
            raise ValueError("LLMConfig.model_name must not be empty")
        if not self.api_base:
            raise ValueError("LLMConfig.api_base must not be empty")
        if not self.api_key:
            raise ValueError(
                "LLMConfig.api_key must not be empty. "
                "Set OPENAI_API_KEY environment variable or pass it explicitly."
            )
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be in [0.0, 2.0], got {self.temperature}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.max_choices_per_level < 1:
            raise ValueError(f"max_choices_per_level must be >= 1, got {self.max_choices_per_level}")
        if self.term_max_len < 1:
            raise ValueError(f"term_max_len must be >= 1, got {self.term_max_len}")


@dataclass
class ExtractionConfig:
    """PDF download and introduction extraction parameters."""

    download_workers: int = 8
    model_workers: int = 20
    max_pdf_pages: int = 4
    print_preview_chars: int = 1000


@dataclass
class ProjectConfig:
    """Top-level project configuration, assembled from YAML + env vars."""

    llm: LLMConfig = field(default_factory=lambda: LLMConfig.__new__(LLMConfig))
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    taxonomy_path: str = "data/msc_converted.json"
    concurrency: int = 10
    models: Dict[str, str] = field(default_factory=dict)
    api_endpoints: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Factory: build config from YAML file + environment variable overrides
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_path(path: str) -> str:
    """Resolve a relative path against the project root."""
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return str(p)


def load_config(
    config_path: Optional[str] = None,
    *,
    model_name: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ProjectConfig:
    """Load configuration with priority: CLI args > env vars > YAML file > defaults."""

    # 1. Load YAML
    if config_path is None:
        config_path = str(_PROJECT_ROOT / "configs" / "default.yaml")

    raw: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # Support nested "classifier" section in unified config
    if "classifier" in raw and isinstance(raw["classifier"], dict) and "llm" in raw["classifier"]:
        raw = raw["classifier"]

    llm_raw = raw.get("llm", {})
    ext_raw = raw.get("extraction", {})

    # 2. Build LLMConfig: CLI args > env vars > YAML
    resolved_model = model_name or os.environ.get("OPENAI_MODEL") or llm_raw.get("model_name", "deepseek-v3")
    resolved_base = api_base or os.environ.get("OPENAI_BASE_URL") or llm_raw.get("api_base", "")
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY") or llm_raw.get("api_key", "")

    llm_cfg = LLMConfig(
        model_name=resolved_model,
        api_base=resolved_base,
        api_key=resolved_key,
        temperature=float(llm_raw.get("temperature", 0.0)),
        timeout=llm_raw.get("timeout", 300),
        max_retries=int(llm_raw.get("max_retries", 3)),
        max_choices_per_level=int(raw.get("classifier", {}).get("max_choices_per_level", 3)),
        term_max_len=int(raw.get("classifier", {}).get("term_max_len", 128)),
        crossdisc_confidence_threshold=float(
            raw.get("classifier", {}).get("crossdisc_confidence_threshold", 0.5)
        ),
    )

    ext_cfg = ExtractionConfig(
        download_workers=int(ext_raw.get("download_workers", 8)),
        model_workers=int(ext_raw.get("model_workers", 20)),
        max_pdf_pages=int(ext_raw.get("max_pdf_pages", 4)),
        print_preview_chars=int(ext_raw.get("print_preview_chars", 1000)),
    )

    taxo_path = raw.get("taxonomy", {}).get("path", "data/msc_converted.json")

    return ProjectConfig(
        llm=llm_cfg,
        extraction=ext_cfg,
        taxonomy_path=_resolve_path(taxo_path),
        concurrency=int(raw.get("classifier", {}).get("concurrency", 10)),
        models=raw.get("models", {}),
        api_endpoints=raw.get("api_endpoints", {}),
    )

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-03

### Added

- Integrated multidisciplinary classifier as `crossdisc_extractor.classifier` subpackage
  - Hierarchical discipline classification using LLMs (sync + async)
  - Multidisciplinary paper detection and main/secondary discipline extraction
  - MSC-based taxonomy system with configurable classification depth
- Unified pipeline module (`crossdisc_extractor.pipeline`) with three CLI subcommands:
  - `crossdisc-pipeline classify` — classify papers and filter multidisciplinary ones
  - `crossdisc-pipeline extract` — run knowledge extraction on pre-classified data
  - `crossdisc-pipeline full` — full pipeline: classify → filter → extract
- Unified configuration file (`configs/default.yaml`) supporting both classifier and extractor settings
- New CLI entry points: `crossdisc-pipeline`, `mdc-classify`, `mdc-demo`
- 44 additional unit tests for the classifier module (total: 114 tests)
- Classification scripts: `classify.py`, `run_demo.py`, `extract_paper.py`, `extract_introduction.py`, `evaluate_classification.py`, `sample_dataset.py`, `merge_data.py`

### Changed

- Project version bumped to 0.2.0
- Added classifier dependencies: `langchain-openai`, `langchain-core`, `beautifulsoup4`, `pdfplumber`, `requests`
- Updated README with classifier module documentation and unified pipeline usage

## [0.1.0] - 2025-01-01

### Added

- Three-stage knowledge extraction pipeline (structure, query, hypothesis)
- Pydantic v2 data models with semantic chain validation
- Cross-disciplinary knowledge graph builder (NetworkX)
- Automated benchmark evaluation with LLM-as-a-judge scoring
- Multi-threaded batch processing with checkpoint/resume support
- Comprehensive unit test suite (70 tests)
- YAML-based experiment configuration for reproducibility
- CLI entry point via `run.py`

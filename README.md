# CrossDisc NMI v1

This branch is the compact NMI-oriented codebase for CrossDisc: a benchmark
and evaluation toolkit for cross-disciplinary scientific hypothesis generation.

The repository intentionally keeps only the maintainable core:

- `crossdisc_extractor/`: classification, extraction, benchmark construction,
  evidence-grounded GT building, and X+5 evaluation metrics.
- `baseline/`: lightweight controlled baseline adapters and evaluation helpers.
- `scripts/`: dataset preparation, sampling, temporal validation, and reporting utilities.
- `tests/`: regression tests for schemas, metrics, GT construction, prompts, and adapters.
- `data/`: lightweight taxonomy and discipline mapping files required by the code.
- `docs/`: metric definitions and NMI-v1 scope notes.

Large generated outputs, third-party baseline source trees, historical logs, and
paper drafts are deliberately excluded from this branch.

## Install

```bash
cd /ssd/wangyuyang/git/nmi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

For LLM-backed runs, configure an OpenAI-compatible endpoint:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://your-endpoint/v1"
export OPENAI_MODEL="deepseek-v3"
```

## Quick Checks

```bash
make ci
python -m compileall -q crossdisc_extractor baseline scripts tests
```

The shared system used to create this branch did not have `pytest`, `ruff`, or
`mypy` installed globally; install `.[all]` before running CI.

## Minimal Workflows

Single-paper extraction:

```bash
python run.py one \
  --title "Deep Learning for Protein Structure Prediction" \
  --abstract "We present a graph neural network approach for protein structures." \
  --primary "Computer Science" \
  --secondary "Biology"
```

Query-centric hypothesis generation:

```bash
python run_query_benchmark.py \
  --input examples/query_eval_sample.json \
  --output-dir outputs/query_sample \
  --models "$OPENAI_MODEL" \
  --prompt-level L1 \
  --hypothesis-format l1_single
```

Multi-agent controlled adapters:

```bash
python run_multiagent_query_benchmark.py \
  --input examples/query_eval_sample.json \
  --output-dir outputs/multiagent_sample \
  --frameworks sciagents,moose_chem,infal,virsci \
  --model "$OPENAI_MODEL" \
  --prompt-level L1
```

Generate X+5 radar charts from a multimodel summary:

```bash
python generate_x5_radar.py \
  --input outputs/.../multimodel_16metrics_summary.json \
  --output-dir outputs/.../radar \
  --level L1
```

## NMI v1 Acceptance Bar

This branch is meant to become a reproducible manuscript artifact. Before NMI
submission, the branch should satisfy:

1. `make ci` passes in a fresh environment.
2. One command reproduces each main table and figure from frozen inputs.
3. X+5 scores are calibrated against expert annotations.
4. Temporal validation uses pre-registered train/test years.
5. Baseline adapters are clearly separated from original upstream baselines.
6. Data, prompts, model versions, seeds, and failure handling are documented.

See `docs/NMI_REPO_SCOPE.md` for the current pruning and scope decisions.

# NMI v1 Repository Scope

This branch is a compact, reproducible codebase derived from
`/ssd/wangyuyang/git/benchmark`.

## Included

- Core extraction package: `crossdisc_extractor/`
- Controlled baseline adapters: `baseline/`
- Reusable data/evaluation scripts: `scripts/`
- Tests: `tests/`
- Lightweight taxonomy files: `data/msc_converted.json`,
  `data/discipline_mapping_en_zh.json`
- Metric documentation: `docs/evaluation_metrics_integrated.md`,
  `docs/evaluation_metrics_complete.md`

## Excluded

- Historical `outputs/` and logs
- Full third-party baseline repositories under `benchmark_baseline/`
- Generated figures, PPT/Word reports, and old NeurIPS draft files
- One-off dated shell runners
- Large Nature/Springer CSV snapshots

## Rationale

The NMI artifact should make the scientific claim auditable rather than preserve
every exploratory run. Large outputs should be archived separately with checksums
and linked from the manuscript. This branch should contain only the code and
small reference data required to regenerate frozen results.

## Next Milestones

1. Add a locked environment file or Dockerfile.
2. Add a frozen manifest for the NMI train/test splits.
3. Add expert annotation schema and reliability scripts.
4. Add one-command reproduction scripts for main tables and figures.
5. Replace exploratory metric docs with final manuscript-ready metric definitions.

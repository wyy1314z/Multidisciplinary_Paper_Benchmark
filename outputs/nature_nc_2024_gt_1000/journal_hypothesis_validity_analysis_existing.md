# Existing 2024 Hypothesis Validity Proxy Analysis

## Scope
- 使用 `benchmark_extractions_2024_nature_nc_1000.jsonl` 中已经存在的 hypothesis/graph 指标。
- 不新增 LLM 调用，因此这不是正式 `benchmark_validity` 的 LLM-as-judge 结果。
- `journal_tier_binary`: Nature=2, Nature Communications=1。

## Counts
- ok records: 381
- failed records: 2
- Nature Communications: 316
- Nature: 65

## Main Composite Scores by Journal
### hypothesis_quality_composite
- Nature: n=65, mean=0.456167, median=0.463902, p25=0.423451, p75=0.492208
- Nature Communications: n=316, mean=0.446999, median=0.452916, p25=0.414594, p75=0.484049
### hypothesis_coherence_score
- Nature: n=65, mean=0.46516, median=0.459987, p25=0.424994, p75=0.499074
- Nature Communications: n=316, mean=0.460582, median=0.45477, p25=0.419806, p75=0.499578
### crossdisciplinary_breadth_score
- Nature: n=65, mean=0.449421, median=0.458521, p25=0.410825, p75=0.50541
- Nature Communications: n=316, mean=0.436812, median=0.44907, p25=0.385552, p75=0.495083

## Spearman Correlation: Journal/Impact Signals vs Scores
- cited_by_count vs hypothesis_quality_composite: rho=0.093541, n=381
- cited_by_count vs crossdisciplinary_breadth_score: rho=0.073457, n=381
- cited_by_count vs hypothesis_coherence_score: rho=0.067697, n=381
- cited_by_count vs chain_coherence: rho=0.061424, n=381
- cited_by_count vs atypical_combination: rho=0.057907, n=381
- cited_by_count vs rao_stirling_diversity: rho=0.055236, n=381
- cited_by_count vs coverage: rho=-0.03345, n=381
- fwci vs chain_coherence: rho=0.201429, n=381
- fwci vs hypothesis_coherence_score: rho=0.15059, n=381
- fwci vs hypothesis_quality_composite: rho=0.089123, n=381
- fwci vs crossdisciplinary_breadth_score: rho=0.054549, n=381
- fwci vs coverage: rho=0.028756, n=381
- fwci vs rao_stirling_diversity: rho=-0.020986, n=381
- fwci vs atypical_combination: rho=-0.00903, n=381
- journal_tier_binary vs atypical_combination: rho=0.078244, n=381
- journal_tier_binary vs chain_coherence: rho=0.074892, n=381
- journal_tier_binary vs rao_stirling_diversity: rho=-0.061383, n=381
- journal_tier_binary vs crossdisciplinary_breadth_score: rho=0.060839, n=381
- journal_tier_binary vs hypothesis_quality_composite: rho=0.052846, n=381
- journal_tier_binary vs coverage: rho=-0.026902, n=381
- journal_tier_binary vs hypothesis_coherence_score: rho=0.024678, n=381

## Nature vs Nature Communications: Largest Mean Differences
- atypical_combination: Nature mean=0.532134, NC mean=0.497287, diff=0.034847, Cliff's delta=0.118549
- embedding_bridging: Nature mean=0.686398, NC mean=0.66129, diff=0.025108, Cliff's delta=0.084761
- crossdisciplinary_breadth_score: Nature mean=0.449421, NC mean=0.436812, diff=0.01261, Cliff's delta=0.093379
- path_consistency: Nature mean=0.156851, NC mean=0.144681, diff=0.01217, Cliff's delta=0.067575
- hypothesis_quality_composite: Nature mean=0.456167, NC mean=0.446999, diff=0.009167, Cliff's delta=0.08111
- chain_coherence: Nature mean=0.787408, NC mean=0.778964, diff=0.008443, Cliff's delta=0.114946
- coverage: Nature mean=0.451222, NC mean=0.458102, diff=-0.00688, Cliff's delta=-0.041285
- rao_stirling_diversity: Nature mean=0.151594, NC mean=0.158402, diff=-0.006808, Cliff's delta=-0.094206
- hypothesis_coherence_score: Nature mean=0.46516, NC mean=0.460582, diff=0.004578, Cliff's delta=0.037877
- bridging_score: Nature mean=0.427559, NC mean=0.430267, diff=-0.002708, Cliff's delta=-0.010565
- consistency_f1: Nature mean=0.0, NC mean=0.0, diff=0.0, Cliff's delta=0.0
- concept_f1: Nature mean=0.0, NC mean=0.0, diff=0.0, Cliff's delta=0.0

## Interpretation
- 两个期刊之间的综合 hypothesis proxy 差异非常小，不足以说明该 proxy 能区分 Nature 与 Nature Communications 档次。
- 与 `fwci` / `cited_by_count` 的相关性也整体偏弱，说明这版结构指标更多反映抽取图结构/跨学科连接，不直接等同于论文影响力。
- 正式版本建议使用 2025 holdout 的 `benchmark_validity_2025` 分数，并纳入更多期刊档次。

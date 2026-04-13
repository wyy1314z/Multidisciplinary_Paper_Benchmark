# 2025 多期刊 Query 样本: Hypothesis 评分与期刊档次相关性分析

## 数据与口径
- 来源目录: `/ssd/wangyuyang/git/benchmark/outputs/querycentric_2025_multijournal_300_v1`
- 有效性评分文件: `/ssd/wangyuyang/git/benchmark/outputs/querycentric_2025_multijournal_300_v1/hypothesis_validity_2025_query_existing.json`
- 样本量: 10 篇; 唯一期刊: 8 个
- 期刊档次是本地代理映射: T5=Nature, T4=Nature 专业刊, T3=Communications/Scientific Data, T2=npj/Scientific Reports, T1=其他 Springer Nature。不是外部 JCR/CiteScore 官方分区。
- 由于当前环境没有 `OPENAI_API_KEY`，评估器日志显示 LLM 主观项为 mock/random；因此本报告剔除 `innovation/scientificity/legacy_feasibility` 等主观项，仅使用客观路径指标构造 `objective_hypothesis_score`。
- 复合分数组件: score_chain_coherence, score_concept_f1, score_concept_recall, score_remote_association_index, score_embedding_bridging, score_bridging, score_factual_precision

## 核心结论
- `journal_tier` vs `objective_hypothesis_score`: Spearman=0.158, Pearson=0.373, n=10.
- `fwci` vs `objective_hypothesis_score`: Spearman=0.442, Pearson=0.308, n=10.
- `cited_by_count` vs `objective_hypothesis_score`: Spearman=0.657, Pearson=0.625, n=10.
- 按当前 10 篇小样本看，期刊档次与客观 hypothesis 评分呈 几乎没有稳定单调相关；这个结论只适合作为 sanity check，不适合做正式统计判断。

## 按期刊档次汇总
| tier | label | papers | journals | objective_mean | fwci_mean | cited_mean | chain_coherence | concept_f1 | remote_assoc |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | T5 flagship Nature | 3 | 1 | 0.617 | 738.022 | 165.000 | 0.585 | 0.258 | 0.947 |
| 4 | T4 Nature subject journal | 5 | 5 | 0.625 | 586.449 | 136.800 | 0.584 | 0.319 | 0.934 |
| 3 | T3 Communications / Scientific Data | 2 | 2 | 0.438 | 258.672 | 105.500 | 0.548 | 0.292 | 0.945 |

## 按期刊汇总
| journal | tier | papers | objective_mean | fwci_mean | cited_mean | chain_coherence | concept_f1 | remote_assoc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Nature | 5 | 3 | 0.617 | 738.022 | 165.000 | 0.585 | 0.258 | 0.947 |
| Nature Energy | 4 | 1 | 0.808 | 335.036 | 205.000 | 0.593 | 0.326 | 0.959 |
| Nature Human Behaviour | 4 | 1 | 0.698 | 1638.859 | 158.000 | 0.600 | 0.333 | 0.925 |
| Nature Medicine | 4 | 1 | 0.698 | 380.462 | 102.000 | 0.577 | 0.309 | 0.939 |
| Nature Methods | 4 | 1 | 0.510 | 420.927 | 120.000 | 0.603 | 0.301 | 0.924 |
| Nature Machine Intelligence | 4 | 1 | 0.412 | 156.960 | 99.000 | 0.545 | 0.327 | 0.922 |
| Communications Earth & Environment | 3 | 1 | 0.609 | 315.242 | 112.000 | 0.537 | 0.344 | 0.972 |
| Scientific Data | 3 | 1 | 0.267 | 202.102 | 99.000 | 0.559 | 0.240 | 0.917 |

## 逐论文表
| journal | tier | objective | fwci | cited | chain_coherence | concept_f1 | title |
|---|---:|---:|---:|---:|---:|---:|---|
| Nature | 5 | 0.691 | 378.924 | 239 | 0.582 | 0.276 | A generative model for inorganic materials design |
| Nature | 5 | 0.595 | 1499.280 | 109 | 0.593 | 0.231 | Impacts of climate change on global agriculture accounting for adaptation |
| Nature | 5 | 0.567 | 335.862 | 147 | 0.579 | 0.268 | Towards conversational diagnostic artificial intelligence |
| Nature Energy | 4 | 0.808 | 335.036 | 205 | 0.593 | 0.326 | The green hydrogen ambition and implementation gap |
| Nature Human Behaviour | 4 | 0.698 | 1638.859 | 158 | 0.600 | 0.333 | Trust in scientists and their role in society across 68 countries |
| Nature Medicine | 4 | 0.698 | 380.462 | 102 | 0.577 | 0.309 | Integrating the environmental and genetic architectures of aging and mortality |
| Nature Methods | 4 | 0.510 | 420.927 | 120 | 0.603 | 0.301 | Segment Anything for Microscopy |
| Nature Machine Intelligence | 4 | 0.412 | 156.960 | 99 | 0.545 | 0.327 | The design space of E(3)-equivariant atom-centred interatomic potentials |
| Communications Earth & Environment | 3 | 0.609 | 315.242 | 112 | 0.537 | 0.344 | Complexities of the global plastics supply chain revealed in a trade-linked material flow  |
| Scientific Data | 3 | 0.267 | 202.102 | 99 | 0.559 | 0.240 | GLEAM4: global land evaporation and soil moisture dataset at 0.1° resolution from 1980 to  |

## 建议
- 当前 query 样本只有 10 篇，且期刊档次集中在 T3-T5；如果要做正式相关性分析，建议用 balanced 2025 validity 流程扩大到 100 篇，并保证每个期刊至少 5 篇。
- 如果要纳入 LLM 主观评分，需要在设置有效 `OPENAI_API_KEY` 后重跑有效性评分，否则 `innovation/scientificity` 等字段不能解释。

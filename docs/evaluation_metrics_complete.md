# CrossDisc Benchmark 评估指标完整汇总表

> 共计 **61 个独立指标**（不含 L1/L2/L3 层级变体），涵盖 10 大类别。
> 其中 19 个指标存在 L1/L2/L3 层级变体，实际评估维度达 **90+**。

---

## 一、文本相似度指标（Text Similarity）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 1 | `bertscore_p` | BERTScore 精确率 | DeBERTa-xlarge-mnli 上下文嵌入 token 级 Precision | [0, 1] | Zhang et al. (2020), ICLR | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 2 | `bertscore_r` | BERTScore 召回率 | DeBERTa-xlarge-mnli 上下文嵌入 token 级 Recall | [0, 1] | Zhang et al. (2020), ICLR | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 3 | `bertscore_f1` | BERTScore F1 | P 和 R 的调和平均；降级时用 sentence-transformers cosine sim | [0, 1] | Zhang et al. (2020), ICLR | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 4 | `rouge1` | ROUGE-1 | 候选文本与参考文本的 unigram 重叠 F1 | [0, 1] | Lin (2004), ACL Workshop | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 5 | `rouge2` | ROUGE-2 | 候选文本与参考文本的 bigram 重叠 F1 | [0, 1] | Lin (2004), ACL Workshop | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 6 | `rougeL` | ROUGE-L | 基于最长公共子序列 (LCS) 的 F1 | [0, 1] | Lin (2004), ACL Workshop | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |
| 7 | `bleu` | BLEU | 修正 n-gram 精确率 + 简短惩罚 (brevity penalty) | [0, 1] | Papineni et al. (2002), ACL | `compute_text_similarity_metrics()` | baseline/evaluate_all.py |

---

## 二、LLM-as-Judge 评分 — Baseline 层（5 维度）

| # | 指标名 | 中文名 | 评分标准 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 8 | `novelty` | 新颖性 | 假设是否超越了原论文的结论？ | [1, 10] | G-Eval, Liu et al. (2023), EMNLP | `llm_judge_hypothesis()` | baseline/evaluate_all.py |
| 9 | `specificity` | 具体性 | 变量、机制是否具体可操作？ | [1, 10] | G-Eval, Liu et al. (2023), EMNLP | `llm_judge_hypothesis()` | baseline/evaluate_all.py |
| 10 | `feasibility` | 可行性 | 在现有技术/资源下能否验证？ | [1, 10] | G-Eval, Liu et al. (2023), EMNLP | `llm_judge_hypothesis()` | baseline/evaluate_all.py |
| 11 | `relevance` | 相关性 | 与原始研究方向的关联度 | [1, 10] | G-Eval, Liu et al. (2023), EMNLP | `llm_judge_hypothesis()` | baseline/evaluate_all.py |
| 12 | `cross_disciplinary` | 跨学科性 | 是否真正整合了多学科视角？ | [1, 10] | G-Eval, Liu et al. (2023), EMNLP | `llm_judge_hypothesis()` | baseline/evaluate_all.py |

---

## 三、LLM-as-Judge 评分 — KG 层（3 维度，含 L1/L2/L3 变体）

| # | 指标名 | 中文名 | 评分标准 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 13 | `{L}_innovation` | 创新性 | 是否发现了 GT 未覆盖的新颖跨学科连接？推理桥梁是否合理？ | [0, 10] | G-Eval 范式 | `evaluate_single_path()` | benchmark/evaluate_benchmark.py |
| 14 | `{L}_feasibility` | 可行性 | 推理链 Step1→2→3 是否逻辑严密？是否存在不可能跳跃？ | [0, 10] | G-Eval 范式 | `evaluate_single_path()` | benchmark/evaluate_benchmark.py |
| 15 | `{L}_scientificity` | 科学性 | 术语是否准确专业？与已知科学事实是否一致？ | [0, 10] | G-Eval 范式 | `evaluate_single_path()` | benchmark/evaluate_benchmark.py |

> 注：`{L}` = `L1` / `L2` / `L3`，每个层级独立评分

---

## 四、可检验性评分（Testability，4 子维度）

| # | 指标名 | 中文名 | 评分标准 | 取值范围 | 参考文献 | 所在 Prompt | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 16 | `{L}_testability` | 可检验性（综合） | 下列 4 项的算术平均 | [0, 10] | Popper (1959) + Si et al. (2024), ICLR 2025 | `PROMPT_TESTABILITY` | benchmark/eval_prompts.py |
| 17 | `specificity` (子维度) | 具体性 | 能否形成精确的研究问题？能否设计控制实验？ | [0, 10] | Si et al. (2024) | `PROMPT_TESTABILITY` | benchmark/eval_prompts.py |
| 18 | `measurability` (子维度) | 可测量性 | 变量能否用现有技术测量？ | [0, 10] | Si et al. (2024) | `PROMPT_TESTABILITY` | benchmark/eval_prompts.py |
| 19 | `falsifiability` (子维度) | 可证伪性 | 是否存在可以推翻该假设的实验结果？ | [0, 10] | Popper (1959) | `PROMPT_TESTABILITY` | benchmark/eval_prompts.py |
| 20 | `resource_feasibility` (子维度) | 资源可行性 | 标准实验室即可？还是需要专业/未知技术设备？ | [0, 10] | Si et al. (2024) | `PROMPT_TESTABILITY` | benchmark/eval_prompts.py |

---

## 五、路径一致性指标（Path Consistency）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 21 | `consistency` | 一致性（遗留版） | matched_steps / num_gen_steps（仅 head-tail 匹配） | [0, 1] | — | `calculate_path_consistency()` | benchmark/evaluate_benchmark.py |
| 22 | `consistency_precision` | 一致性精确率 | 关系感知评分 (1.0/0.8/0.5/0.3/0.1 五级) / 生成步数 | [0, 1] | — | `enhanced_path_consistency()` | benchmark/metrics.py |
| 23 | `consistency_recall` | 一致性召回率 | GT 中被覆盖的关系对 / GT 关系对总数 | [0, 1] | — | `enhanced_path_consistency()` | benchmark/metrics.py |
| 24 | `consistency_f1` | 一致性 F1 | 2 × precision × recall / (precision + recall) | [0, 1] | — | `enhanced_path_consistency()` | benchmark/metrics.py |

> 关系感知评分层级：1.0 = 精确匹配 (head, rel_type, tail)；0.8 = 同簇匹配；0.5 = 实体匹配；0.3 = 对称反向；0.1 = 非对称反向

---

## 六、跨越性与连贯性指标（Bridging & Coherence）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 25 | `bridging` | 桥接分数（遗留版） | 1 - Jaccard(起点 tokens, 终点 tokens) | [0, 1] | — | `calculate_bridging_score()` | benchmark/evaluate_benchmark.py |
| 26 | `embedding_bridging` | 嵌入桥接距离 | 1 - cosine_sim(emb(起点 head), emb(终点 tail)) | [0, 1] | — | `embedding_bridging_score()` | benchmark/metrics.py |
| 27 | `overall_coherence` | 总体连贯性 | mean(hop_scores)；hop = 0.6×claim_coh + 0.4×bridge_nat | [0, 1] | — | `reasoning_chain_coherence()` | benchmark/metrics.py |
| 28 | `claim_coherence` (per-hop) | 声明连贯性 | cosine_sim(emb(当前 claim), emb(下一步 claim)) | [0, 1] | — | `reasoning_chain_coherence()` | benchmark/metrics.py |
| 29 | `bridge_naturalness` (per-hop) | 桥接自然性 | cosine_sim(emb(当前 tail), emb(下一步 head)) | [0, 1] | — | `reasoning_chain_coherence()` | benchmark/metrics.py |
| 30 | `weakest_hop_score` | 最弱跳分数 | min(所有 hop 的 combined_score) | [0, 1] | — | `reasoning_chain_coherence()` | benchmark/metrics.py |
| 31 | `chain_coherence` (baseline) | 链式连贯性 | coherent_hops / total_hops (step_i.tail == step_{i+1}.head) | [0, 1] | — | `compute_structural_metrics()` | baseline/evaluate_all.py |

---

## 七、新颖性与多样性指标（Novelty & Diversity）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 32 | `mean_surprisal` | 平均惊异度 | mean(-log₂ P(triple_i \| KG))，Laplace 平滑 | [0, +∞) | Shannon (1948) | `information_theoretic_novelty()` | benchmark/metrics.py |
| 33 | `normalized_novelty` | 标准化新颖性 | mean_surprisal / max_surprisal | [0, 1] | — | `information_theoretic_novelty()` | benchmark/metrics.py |
| 34 | `atypical_combination_index` | 非典型组合指数 | sigmoid(z_score)；z = (median_freq - μ) / σ | [0, 1] | Uzzi et al. (2013), Science | `atypical_combination_index()` | benchmark/metrics.py |
| 35 | `rao_stirling` | Rao-Stirling 多样性 | Δ = Σ_{i≠j} d_ij × p_i × p_j（学科分类树距离） | [0, 1] | Stirling (2007), J. R. Soc. Interface | `rao_stirling_diversity()` | benchmark/metrics.py |

---

## 八、结构多样性指标（Structural Diversity，Torrance 启发）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 36 | `{L}_fluency` | 流畅性 | 该层级的路径数量 | [0, +∞) | Torrance (1966) TTCT | `structural_diversity()` | benchmark/metrics.py |
| 37 | `{L}_flexibility` | 灵活性 | 唯一关系类型数 / 路径数 | [0, 1] | Torrance (1966) TTCT | `structural_diversity()` | benchmark/metrics.py |
| 38 | `{L}_pairwise_diversity` | 成对多样性 | mean(1 - cosine_sim) across 所有路径对 | [0, 1] | Torrance (1966) TTCT | `structural_diversity()` | benchmark/metrics.py |
| 39 | `{L}_entity_coverage` | 实体覆盖率 | 唯一实体数 / (路径数 × 4) | [0, 1] | Torrance (1966) TTCT | `structural_diversity()` | benchmark/metrics.py |

---

## 九、层级深度递进指标（Hierarchical Depth Progression）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 40 | `depth_l2_concept_expansion` | L2 概念扩展率 | len(L2 实体 - L1 实体) / len(L2 实体) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 41 | `depth_l3_concept_expansion` | L3 概念扩展率 | len(L3 实体 - L2 实体) / len(L3 实体) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 42 | `depth_span_progression_l1_l2` | L1→L2 跨度增量 | max(avg_span_L2 - avg_span_L1, 0) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 43 | `depth_span_progression_l2_l3` | L2→L3 跨度增量 | max(avg_span_L3 - avg_span_L2, 0) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 44 | `depth_l2_anchoring` | L2 锚定率 | len(L2 实体 ∩ L1 实体) / len(L1 实体) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 45 | `depth_l3_anchoring` | L3 锚定率 | len(L3 实体 ∩ L2 实体) / len(L2 实体) | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |
| 46 | `depth_depth_quality` | 深度质量综合 | (l2_exp + l3_exp + span_12 + span_23) / 4 | [0, 1] | — | `hierarchical_depth_progression()` | benchmark/metrics.py |

---

## 十、GT 对齐指标（Ground Truth Coverage & Alignment）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 47 | `concept_recall` | 概念召回率 | GT 概念被覆盖数 / GT 概念总数（软匹配阈值 0.75） | [0, 1] | — | `concept_coverage()` | benchmark/metrics.py |
| 48 | `concept_precision` | 概念精确率 | 生成实体匹配 GT 数 / 生成实体总数 | [0, 1] | — | `concept_coverage()` | benchmark/metrics.py |
| 49 | `concept_f1` | 概念 F1 | 2 × P × R / (P + R) | [0, 1] | — | `concept_coverage()` | benchmark/metrics.py |
| 50 | `relation_precision` | 关系精确率 | 有 GT 证据支撑的生成关系 / 生成关系总数 | [0, 1] | — | `relation_precision()` | benchmark/metrics.py |
| 51 | `relation_type_accuracy` | 关系类型准确率 | 类型匹配数 / 有支撑的关系数 | [0, 1] | — | `relation_precision()` | benchmark/metrics.py |
| 52 | `evidence_coverage` | 证据覆盖率 | GT 关系被覆盖数 / GT 关系总数 | [0, 1] | — | `relation_precision()` | benchmark/metrics.py |
| 53 | `best_alignment` | 最佳路径对齐度 | max(cosine_sim(emb(gen_path), emb(gt_paths))) | [0, 1] | — | `path_semantic_alignment()` | benchmark/metrics.py |
| 54 | `mean_alignment` | 平均路径对齐度 | mean(cosine_sim(emb(gen_path), all gt_paths)) | [0, 1] | — | `path_semantic_alignment()` | benchmark/metrics.py |

---

## 十一、知识图谱拓扑指标（KG Topology）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 55 | `n_nodes` | 节点数 | G.number_of_nodes() | [0, +∞) | — | `kg_topology_metrics()` | benchmark/metrics.py |
| 56 | `n_edges` | 边数 | G.number_of_edges() | [0, +∞) | — | `kg_topology_metrics()` | benchmark/metrics.py |
| 57 | `density` | 图密度 | nx.density(G) = 2E / (N(N-1)) | [0, 1] | — | `kg_topology_metrics()` | benchmark/metrics.py |
| 58 | `avg_betweenness` | 平均介数中心性 | mean(betweenness_centrality(G)) | [0, 1] | Freeman (1977) | `kg_topology_metrics()` | benchmark/metrics.py |
| 59 | `inverse_modularity` | 逆模块性 | 1 - modularity(G)；越高 → 跨学科整合越好 | [0, 1] | Newman (2006), PNAS | `kg_topology_metrics()` | benchmark/metrics.py |
| 60 | `largest_cc_ratio` | 最大连通分量比例 | 最大连通分量节点数 / 总节点数 | [0, 1] | — | `kg_topology_metrics()` | benchmark/metrics.py |
| 61 | `avg_path_length` (KG) | 平均最短路径 | nx.average_shortest_path_length(最大连通分量) | [0, +∞) | Watts & Strogatz (1998), Nature | `kg_topology_metrics()` | benchmark/metrics.py |
| 62 | `clustering_coefficient` | 聚类系数 | nx.average_clustering(G_undirected) | [0, 1] | Watts & Strogatz (1998), Nature | `kg_topology_metrics()` | benchmark/metrics.py |

---

## 十二、Baseline 结构化指标（Structural Metrics）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 63 | `has_L1` | L1 存在标志 | L1 路径存在则 1.0，否则 0.0 | {0, 1} | — | `compute_structural_metrics()` | baseline/evaluate_all.py |
| 64 | `has_L2` | L2 存在标志 | L2 路径存在则 1.0，否则 0.0 | {0, 1} | — | `compute_structural_metrics()` | baseline/evaluate_all.py |
| 65 | `has_L3` | L3 存在标志 | L3 路径存在则 1.0，否则 0.0 | {0, 1} | — | `compute_structural_metrics()` | baseline/evaluate_all.py |
| 66 | `avg_path_length` (baseline) | 平均路径长度 | mean(len(steps) for all paths) | [0, +∞) | — | `compute_structural_metrics()` | baseline/evaluate_all.py |
| 67 | `entity_grounding_rate` | 实体锚定率 | 非通用实体数 / 总实体数（排除"前提""结论"等泛词） | [0, 1] | — | `compute_structural_metrics()` | baseline/evaluate_all.py |
| 68 | `relation_diversity` | 关系多样性 | 唯一关系类型数 / 路径总数 | [0, 1] | — | `compute_structural_metrics()` | baseline/evaluate_all.py |

---

## 十三、元数据指标（Meta）

| # | 指标名 | 中文名 | 计算方法 | 取值范围 | 参考文献 | 所在函数 | 所在文件 |
|---|--------|--------|---------|---------|---------|---------|---------|
| 69 | `elapsed_seconds` | 耗时 | 方法执行时间（秒） | [0, +∞) | — | `evaluate_single_output()` | baseline/evaluate_all.py |
| 70 | `num_hypotheses` | 假设数量 | 有效假设输出数 | [0, +∞) | — | `evaluate_single_output()` | baseline/evaluate_all.py |
| 71 | `avg_hypothesis_length` | 平均假设长度 | 生成假设的平均字符数 | [0, +∞) | — | `evaluate_single_output()` | baseline/evaluate_all.py |

---

## 层级变体说明

以下 19 个指标存在 L1/L2/L3 三个独立层级变体（如 `L1_consistency`, `L2_consistency`, `L3_consistency`）：

| 基础指标名 | 层级变体前缀 | 实际变体数 |
|-----------|------------|----------|
| `consistency` | L1/L2/L3 | 3 |
| `consistency_precision` | L1/L2/L3 | 3 |
| `consistency_recall` | L1/L2/L3 | 3 |
| `consistency_f1` | L1/L2/L3 | 3 |
| `bridging` | L1/L2/L3 | 3 |
| `embedding_bridging` | L1/L2/L3 | 3 |
| `chain_coherence` (KG) | L1/L2/L3 | 3 |
| `info_novelty` | L1/L2/L3 | 3 |
| `atypical_combination` | L1/L2/L3 | 3 |
| `rao_stirling` | L1/L2/L3 | 3 |
| `concept_recall` | L1/L2/L3 | 3 |
| `concept_precision` | L1/L2/L3 | 3 |
| `concept_f1` | L1/L2/L3 | 3 |
| `relation_precision` | L1/L2/L3 | 3 |
| `relation_type_accuracy` | L1/L2/L3 | 3 |
| `evidence_coverage` | L1/L2/L3 | 3 |
| `path_alignment_best` | L1/L2/L3 | 3 |
| `path_alignment_mean` | L1/L2/L3 | 3 |
| `innovation` / `feasibility` / `scientificity` / `testability` | L1/L2/L3 | 12 |
| `fluency` / `flexibility` / `pairwise_diversity` / `entity_coverage` | L1/L2/L3 | 12 |

**总计层级变体**: 19 × 3 = 57 个额外变体

---

## 参考文献索引

| 简称 | 完整引用 |
|------|---------|
| Zhang et al. (2020) | Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q., & Artzi, Y. (2020). BERTScore: Evaluating Text Generation with BERT. ICLR 2020. arXiv:1904.09675 |
| Lin (2004) | Lin, C.-Y. (2004). ROUGE: A Package for Automatic Evaluation of Summaries. ACL-04 Workshop, pp. 74-81 |
| Papineni et al. (2002) | Papineni, K., Roukos, S., Ward, T., & Zhu, W.-J. (2002). BLEU: a Method for Automatic Evaluation of Machine Translation. ACL 2002, pp. 311-318 |
| Liu et al. (2023) | Liu, Y., Iter, D., Xu, Y., Wang, S., Xu, R., & Zhu, C. (2023). G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment. EMNLP 2023. arXiv:2303.16634 |
| Popper (1959) | Popper, K. R. (1959). The Logic of Scientific Discovery. London: Hutchinson |
| Si et al. (2024) | Si, C., Yang, D., & Hashimoto, T. (2024). Can LLMs Generate Novel Research Ideas? ICLR 2025. arXiv:2409.04109 |
| Stirling (2007) | Stirling, A. (2007). A General Framework for Analysing Diversity in Science, Technology and Society. J. R. Soc. Interface, 4(15), 707-719 |
| Uzzi et al. (2013) | Uzzi, B., Mukherjee, S., Stringer, M., & Jones, B. F. (2013). Atypical Combinations and Scientific Impact. Science, 342(6157), 468-472 |
| Torrance (1966) | Torrance, E. P. (1966). Torrance Tests of Creative Thinking. Princeton, NJ: Personnel Press |
| Shannon (1948) | Shannon, C. E. (1948). A Mathematical Theory of Communication. Bell System Technical Journal, 27(3), 379-423 |
| Freeman (1977) | Freeman, L. C. (1977). A Set of Measures of Centrality Based on Betweenness. Sociometry, 40(1), 35-41 |
| Newman (2006) | Newman, M. E. J. (2006). Modularity and Community Structure in Networks. PNAS, 103(23), 8577-8582 |
| Watts & Strogatz (1998) | Watts, D. J. & Strogatz, S. H. (1998). Collective Dynamics of Small-World Networks. Nature, 393, 440-442 |

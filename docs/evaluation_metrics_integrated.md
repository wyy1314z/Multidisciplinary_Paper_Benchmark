# CrossDisc Benchmark 评估指标统一体系

> 将现有 71 个已实现指标与 23 个建议补充指标进行整合归纳，
> 形成 **10 大评估维度、94 个独立指标** 的统一框架。
>
> - 标记 ✅ = 已实现（代码已有）
> - 标记 🔲 = 建议补充（待实现）
> - 带 `{L}` 前缀的指标存在 L1/L2/L3 三个层级变体

---

## 评估维度总览

| 维度编号 | 维度名称 | 核心问题 | 已实现 | 待补充 | 合计 |
|---------|---------|---------|-------|-------|------|
| D1 | 科学本体质量 | 假设作为科学命题，逻辑结构是否合格？ | 8 | 5 | 13 |
| D2 | 可检验性与可操作性 | 假设能否被实验验证或证伪？ | 5 | 1 | 6 |
| D3 | 推理链结构质量 | 路径的逻辑连贯性、方向性、简约性如何？ | 11 | 3 | 14 |
| D4 | 跨学科性 | 是否真正整合了多学科知识？ | 3 | 4 | 7 |
| D5 | 新颖性与创造力 | 假设是否提出了意料之外的新颖连接？ | 8 | 5 | 13 |
| D6 | GT 对齐与知识覆盖 | 假设在多大程度上覆盖了已验证知识？ | 8 | 1 | 9 |
| D7 | 知识图谱拓扑 | 生成的知识图谱结构是否合理？ | 8 | 2 | 10 |
| D8 | 可靠性与鲁棒性 | 生成结果是否稳定、无幻觉、事实准确？ | 0 | 3 | 3 |
| D9 | 文本质量 | 文本层面与参考的相似度如何？ | 7 | 0 | 7 |
| D10 | 层级递进与元数据 | L1→L2→L3 递进质量 + 效率指标 | 10 | 0 | 10 |
|  | **合计** |  | **71** | **23** | **94** |

---

## D1. 科学本体质量 (Scientific Ontological Quality)

> **核心问题**：假设作为一个科学命题，其逻辑结构、解释力和科学规范性是否合格？
> **理论根基**：Popper (1959) 可证伪性、Kuhn (1962) 五大标准、Simon (1983) 解释深度、Laudan (1986) 一致性

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 1 | ✅ | `novelty` | 新颖性 | LLM 评分：假设是否超越原论文结论 | [1, 10] | Liu et al. (2023) G-Eval | LLM Judge |
| 2 | ✅ | `specificity` | 具体性 | LLM 评分：变量、机制是否具体可操作 | [1, 10] | Liu et al. (2023) G-Eval | LLM Judge |
| 3 | ✅ | `feasibility` | 可行性 | LLM 评分：在现有技术下能否验证 | [1, 10] | Liu et al. (2023) G-Eval | LLM Judge |
| 4 | ✅ | `relevance` | 相关性 | LLM 评分：与原始研究方向的关联度 | [1, 10] | Liu et al. (2023) G-Eval | LLM Judge |
| 5 | ✅ | `{L}_innovation` | 创新性 (KG 层) | LLM 评分：是否发现 GT 未覆盖的新颖跨学科连接 | [0, 10] | G-Eval 范式 | LLM Judge |
| 6 | ✅ | `{L}_feasibility` | 可行性 (KG 层) | LLM 评分：推理链是否逻辑严密 | [0, 10] | G-Eval 范式 | LLM Judge |
| 7 | ✅ | `{L}_scientificity` | 科学性 (KG 层) | LLM 评分：术语是否准确、是否符合科学事实 | [0, 10] | G-Eval 范式 | LLM Judge |
| 8 | ✅ | `cross_disciplinary` | 跨学科性 (Baseline) | LLM 评分：是否真正整合了多学科视角 | [1, 10] | Liu et al. (2023) G-Eval | LLM Judge |
| 9 | 🔲 | `internal_consistency` | 内部一致性 | 1 - \|{(i,j): NLI(claim_i, claim_j)=contradiction}\| / C(n,2) | [0, 1] | Kuhn (1962); Laudan (1986) | NLI 模型 |
| 10 | 🔲 | `explanatory_depth` | 解释深度 | mean(mechanism_score)；0=相关, 0.5=因果, 1.0=机制 | [0, 1] | Simon (1983); Machamer (2000) | LLM 三级分类 |
| 11 | 🔲 | `empirical_content` | 经验内容 | n_prediction / (n_prediction + n_retrodiction) | [0, 1] | Popper (1959); Lakatos (1978) | LLM 分类 |
| 12 | 🔲 | `parsimony` | 简约性 | 1 - (U_ent + U_rel) / (steps × 3) | [0, 1] | Kuhn (1962); Simon (1983) | 确定性计算 |
| 13 | 🔲 | `problem_solving_coverage` | 问题解决覆盖率 | answered_queries / total_queries | [0, 1] | Laudan (1977); Kuhn (1962) | LLM 判断 |

---

## D2. 可检验性与可操作性 (Testability & Operationalizability)

> **核心问题**：假设能否转化为具体的实验设计并被证伪？
> **理论根基**：Popper (1959) 可证伪性、Si et al. (2024) Expected Effectiveness

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 14 | ✅ | `{L}_testability` | 可检验性（综合） | 下列 4 项的算术平均 | [0, 10] | Popper (1959); Si et al. (2024) | LLM Judge |
| 15 | ✅ | `specificity` (子维度) | 具体性 | 能否形成精确研究问题？能否设计控制实验？ | [0, 10] | Si et al. (2024) | LLM Judge |
| 16 | ✅ | `measurability` | 可测量性 | 变量能否用现有技术测量？数据可获取？ | [0, 10] | Si et al. (2024) | LLM Judge |
| 17 | ✅ | `falsifiability` | 可证伪性 | 是否存在可以推翻该假设的实验结果？ | [0, 10] | Popper (1959) | LLM Judge |
| 18 | ✅ | `resource_feasibility` | 资源可行性 | 标准实验室即可？还是需非现有技术？ | [0, 10] | Si et al. (2024) | LLM Judge |
| 19 | 🔲 | `falsifiability_scope` | 可证伪域宽度 | \|O_refute(H)\| / \|O_all\| | [0, 1] | Popper (1959, 1963) | LLM + 枚举 |

---

## D3. 推理链结构质量 (Reasoning Chain Structural Quality)

> **核心问题**：路径的逻辑连贯性、实体衔接、方向性、结构经济性如何？
> **理论根基**：推理链一致性 + 因果方向性 (Pearl 2009) + 图匹配理论

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 20 | ✅ | `consistency` | 一致性（遗留版） | matched_steps / num_gen_steps | [0, 1] | — | 确定性 |
| 21 | ✅ | `consistency_precision` | 一致性精确率 | 关系感知评分 (五级) / 生成步数 | [0, 1] | — | 确定性 |
| 22 | ✅ | `consistency_recall` | 一致性召回率 | GT 中被覆盖的关系对 / GT 关系对总数 | [0, 1] | — | 确定性 |
| 23 | ✅ | `consistency_f1` | 一致性 F1 | 2 × P × R / (P + R) | [0, 1] | — | 确定性 |
| 24 | ✅ | `overall_coherence` | 总体连贯性 | mean(0.6×claim_coh + 0.4×bridge_nat) | [0, 1] | — | 嵌入相似度 |
| 25 | ✅ | `claim_coherence` | 声明连贯性 | cosine_sim(emb(claim_i), emb(claim_{i+1})) | [0, 1] | — | 嵌入相似度 |
| 26 | ✅ | `bridge_naturalness` | 桥接自然性 | cosine_sim(emb(tail_i), emb(head_{i+1})) | [0, 1] | — | 嵌入相似度 |
| 27 | ✅ | `weakest_hop_score` | 最弱跳分数 | min(所有 hop combined_score) | [0, 1] | — | 嵌入相似度 |
| 28 | ✅ | `chain_coherence` (baseline) | 链式连贯性 | coherent_hops / total_hops (tail==next_head) | [0, 1] | — | 确定性 |
| 29 | ✅ | `entity_grounding_rate` | 实体锚定率 | 非通用实体数 / 总实体数 | [0, 1] | — | 确定性 |
| 30 | ✅ | `avg_path_length` | 平均路径长度 | mean(len(steps)) | [0, +∞) | — | 确定性 |
| 31 | 🔲 | `causal_direction_accuracy` | 因果方向准确率 | forward_match / any_match | [0, 1] | Simon (1983); Pearl (2009) | 确定性 |
| 32 | 🔲 | `graph_edit_distance` | 归一化图编辑距离 | min GED(G_H, G_gt) / normalization | [0, 1] | Gao (2010); Bunke (1983) | 图算法 |
| 33 | 🔲 | `parsimony` | 简约性 | 1 - (U_ent + U_rel) / (steps × 3) | [0, 1] | Kuhn (1962); Simon (1983) | 确定性 |

> 注：`parsimony` 同时归属 D1（科学本体质量）和 D3（结构质量），在指标计数中只算一次。

---

## D4. 跨学科性 (Interdisciplinarity)

> **核心问题**：假设是否真正整合了多学科知识？跨越程度、平衡度、桥梁节点如何？
> **理论根基**：Stirling (2007) 三维多样性 (variety + balance + disparity)、Burt (2004) 结构洞、Coccia (2022) 发现概率

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 34 | ✅ | `rao_stirling` | Rao-Stirling 多样性 | Δ = 2Σ_{i<j} d_ij × p_i × p_j | [0, 1] | Stirling (2007) | 确定性 |
| 35 | ✅ | `inverse_modularity` | 逆模块性 | 1 - modularity(G) | [0, 1] | Newman (2006) | 图算法 |
| 36 | ✅ | `cross_disciplinary` | 跨学科性 (Baseline) | LLM 评分：是否整合多学科视角 | [1, 10] | Liu et al. (2023) | LLM Judge |
| 37 | 🔲 | `disciplinary_leap_index` | 学科跨越系数 | max_(s∈steps) d_tax(disc(head_s), disc(tail_s)) | [0, 1] | Fortunato (2018); Coccia (2022) | 确定性 |
| 38 | 🔲 | `discipline_balance` | 学科分布平衡度 | 1 - Gini({p_1, ..., p_k}) | [0, 1] | Stirling (2007); Gini (1912) | 确定性 |
| 39 | 🔲 | `boundary_spanner_score` | 边界跨越者比例 | multi-disc entities / all entities | [0, 1] | Bettencourt (2009); Burt (2004) | 确定性 |
| 40 | 🔲 | `discovery_probability` | 发现概率估计 | Π_(s∈steps) Prd(disc_h, disc_t) | [0, 1] | Coccia (2022) | 概率模型 |

---

## D5. 新颖性与创造力 (Novelty & Creativity)

> **核心问题**：假设是否提出了意料之外的知识连接？创造力的多维表现如何？
> **理论根基**：Shannon (1948) 信息论、Uzzi et al. (2013) 非典型组合、Torrance (1966) TTCT 四维度、Mednick (1962) 远程联想

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 41 | ✅ | `mean_surprisal` | 平均惊异度 | mean(-log₂ P(triple \| KG))，Laplace 平滑 | [0, +∞) | Shannon (1948) | 确定性 |
| 42 | ✅ | `normalized_novelty` | 标准化新颖性 | mean_surprisal / max_surprisal | [0, 1] | Shannon (1948) | 确定性 |
| 43 | ✅ | `atypical_combination` | 非典型组合指数 | sigmoid(z_score)；z=(median_freq-μ)/σ | [0, 1] | Uzzi et al. (2013) | 确定性 |
| 44 | ✅ | `bridging` | 桥接分数（遗留版） | 1 - Jaccard(起点 tokens, 终点 tokens) | [0, 1] | — | 确定性 |
| 45 | ✅ | `embedding_bridging` | 嵌入桥接距离 | 1 - cosine_sim(emb(首 head), emb(末 tail)) | [0, 1] | — | 嵌入相似度 |
| 46 | ✅ | `{L}_fluency` | 流畅性 (Torrance) | 该层级路径数量 | [0, +∞) | Torrance (1966) | 确定性 |
| 47 | ✅ | `{L}_flexibility` | 灵活性 (Torrance) | 唯一关系类型数 / 路径数 | [0, 1] | Torrance (1966) | 确定性 |
| 48 | ✅ | `{L}_pairwise_diversity` | 成对多样性 (Torrance) | mean(1 - cosine_sim) across 路径对 | [0, 1] | Torrance (1966) | 嵌入相似度 |
| 49 | 🔲 | `{L}_elaboration` | 精进性 (Torrance) | mean(claim_len / median_claim_len) | [0, +∞) | Torrance (1966); Kim (2006) | 确定性 |
| 50 | 🔲 | `originality_score` | 独创性 | 1 - max(sim to all other paths) | [0, 1] | Torrance (1966); Si (2024) | 嵌入相似度 |
| 51 | 🔲 | `remote_association_index` | 远程联想指数 | mean_(s∈steps) (1 - cos(emb(head_s), emb(tail_s))) | [0, 1] | Mednick (1962) | 嵌入相似度 |
| 52 | 🔲 | `novelty_convention_balance` | 新颖-常规平衡 | min(r_novel, r_conv) / max(r_novel, r_conv) | [0, 1] | Uzzi et al. (2013); Fortunato (2018) | 确定性 |
| 53 | 🔲 | `link_prediction_surprisal` | 链接预测惊异度 | -mean(log₂ P_KGE(tail\|head, rel)) | [0, +∞) | Ding (2025); Bordes (2013) | KGE 模型 |

---

## D6. GT 对齐与知识覆盖 (GT Alignment & Knowledge Coverage)

> **核心问题**：假设在多大程度上覆盖了经过验证的 GT 知识？概念和关系的匹配度如何？
> **理论根基**：信息检索 P/R/F1 范式 + 语义软匹配

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 54 | ✅ | `concept_recall` | 概念召回率 | GT 概念被覆盖数 / GT 总数（软匹配 ≥0.75） | [0, 1] | — | 嵌入相似度 |
| 55 | ✅ | `concept_precision` | 概念精确率 | 生成实体匹配 GT 数 / 生成实体总数 | [0, 1] | — | 嵌入相似度 |
| 56 | ✅ | `concept_f1` | 概念 F1 | 2 × P × R / (P + R) | [0, 1] | — | 确定性 |
| 57 | ✅ | `relation_precision` | 关系精确率 | 有 GT 证据支撑的生成关系 / 生成关系总数 | [0, 1] | — | 嵌入相似度 |
| 58 | ✅ | `relation_type_accuracy` | 关系类型准确率 | 类型匹配数 / 有支撑的关系数 | [0, 1] | — | 确定性 |
| 59 | ✅ | `evidence_coverage` | 证据覆盖率 | GT 关系被覆盖数 / GT 关系总数 | [0, 1] | — | 确定性 |
| 60 | ✅ | `best_alignment` | 最佳路径对齐度 | max(cosine_sim(emb(gen), emb(gt))) | [0, 1] | — | 嵌入相似度 |
| 61 | ✅ | `mean_alignment` | 平均路径对齐度 | mean(cosine_sim(emb(gen), all gt)) | [0, 1] | — | 嵌入相似度 |
| 62 | 🔲 | `paradigm_compatibility` | 范式兼容性 | mean_(s) max_(gt_claim) sim(claim_s, gt_claim) | [0, 1] | Kuhn (1962); Laudan (1986) | 嵌入相似度 |

---

## D7. 知识图谱拓扑与推理 (KG Topology & Reasoning)

> **核心问题**：生成的知识图谱结构是否合理？路径实体在知识全景中的结构位置如何？
> **理论根基**：小世界网络 (Watts & Strogatz 1998)、社区结构 (Newman 2006)、结构洞 (Burt 2004)、Chen (2009) σ²

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 63 | ✅ | `n_nodes` | 节点数 | G.number_of_nodes() | [0, +∞) | — | 确定性 |
| 64 | ✅ | `n_edges` | 边数 | G.number_of_edges() | [0, +∞) | — | 确定性 |
| 65 | ✅ | `density` | 图密度 | 2E / (N(N-1)) | [0, 1] | — | 确定性 |
| 66 | ✅ | `avg_betweenness` | 平均介数中心性 (生成图) | mean(BC(G_gen)) | [0, 1] | Freeman (1977) | 图算法 |
| 67 | ✅ | `largest_cc_ratio` | 最大连通分量比例 | 最大 CC 节点数 / 总节点数 | [0, 1] | — | 图算法 |
| 68 | ✅ | `avg_path_length` (KG) | 平均最短路径 | avg_shortest_path(最大 CC) | [0, +∞) | Watts & Strogatz (1998) | 图算法 |
| 69 | ✅ | `clustering_coefficient` | 聚类系数 | avg_clustering(G_undirected) | [0, 1] | Watts & Strogatz (1998) | 图算法 |
| 70 | ✅ | `{L}_entity_coverage` | 实体覆盖率 (Torrance) | 唯一实体数 / (路径数 × 4) | [0, 1] | Torrance (1966) | 确定性 |
| 71 | 🔲 | `structural_hole_bridging` | 结构洞桥接度 (GT 图) | mean_(e∈path) BC(e, G_GT) | [0, 1] | Chen (2009); Burt (2004) | 图算法 |
| 72 | 🔲 | `sigma2_transformativeness` | σ² 变革性指数 | burst(H) × SHB(H) | [0, 1] | Chen (2009); Kleinberg (2003) | 图算法×统计 |

---

## D8. 可靠性与鲁棒性 (Reliability & Robustness)

> **核心问题**：生成结果是否稳定可信？是否存在幻觉或事实矛盾？
> **理论根基**：FActScore (Min et al. 2023)、Self-Consistency (Wang et al. 2023)、HaluEval (Li et al. 2023)
>
> **注：此维度为全新补充，现有体系完全缺失。**

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 73 | 🔲 | `hallucination_rate` | 幻觉率 | (不在 GT KG 且不在 abstract 中的实体数) / 总实体数 | [0, 1] | Min (2023) FActScore; Li (2023) HaluEval | 字符串+嵌入 |
| 74 | 🔲 | `self_consistency` | 自一致性 | mean pairwise sim across K independent runs | [0, 1] | Wang et al. (2023); Zhang (2025) | 多次采样 |
| 75 | 🔲 | `factual_precision` | 事实精度 | (NLI 不矛盾的 claim 数) / 总 claim 数 | [0, 1] | Min (2023) FActScore; He (2021) DeBERTa | NLI 模型 |

---

## D9. 文本质量 (Text Quality)

> **核心问题**：生成文本在表层语言学维度上与参考文本的相似度如何？
> **理论根基**：机器翻译/文本摘要评估标准 (BLEU, ROUGE, BERTScore)

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 76 | ✅ | `bertscore_p` | BERTScore 精确率 | DeBERTa token 级 Precision | [0, 1] | Zhang et al. (2020) | 嵌入相似度 |
| 77 | ✅ | `bertscore_r` | BERTScore 召回率 | DeBERTa token 级 Recall | [0, 1] | Zhang et al. (2020) | 嵌入相似度 |
| 78 | ✅ | `bertscore_f1` | BERTScore F1 | P 和 R 的调和平均 | [0, 1] | Zhang et al. (2020) | 嵌入相似度 |
| 79 | ✅ | `rouge1` | ROUGE-1 | unigram 重叠 F1 | [0, 1] | Lin (2004) | 确定性 |
| 80 | ✅ | `rouge2` | ROUGE-2 | bigram 重叠 F1 | [0, 1] | Lin (2004) | 确定性 |
| 81 | ✅ | `rougeL` | ROUGE-L | LCS F1 | [0, 1] | Lin (2004) | 确定性 |
| 82 | ✅ | `bleu` | BLEU | 修正 n-gram 精确率 + brevity penalty | [0, 1] | Papineni et al. (2002) | 确定性 |

---

## D10. 层级递进与元数据 (Hierarchical Progression & Meta)

> **核心问题**：L1→L2→L3 三层假设是否呈现出概念扩展和深度递进？基础效率指标。

| # | 状态 | 指标名 | 中文名 | 计算方法 | 取值范围 | 核心参考文献 | 实现方式 |
|---|------|--------|--------|---------|---------|------------|---------|
| 83 | ✅ | `depth_l2_concept_expansion` | L2 概念扩展率 | \|L2_ent - L1_ent\| / \|L2_ent\| | [0, 1] | — | 确定性 |
| 84 | ✅ | `depth_l3_concept_expansion` | L3 概念扩展率 | \|L3_ent - L2_ent\| / \|L3_ent\| | [0, 1] | — | 确定性 |
| 85 | ✅ | `depth_span_progression_l1_l2` | L1→L2 跨度增量 | max(span_L2 - span_L1, 0) | [0, 1] | — | 嵌入相似度 |
| 86 | ✅ | `depth_span_progression_l2_l3` | L2→L3 跨度增量 | max(span_L3 - span_L2, 0) | [0, 1] | — | 嵌入相似度 |
| 87 | ✅ | `depth_l2_anchoring` | L2 锚定率 | \|L2_ent ∩ L1_ent\| / \|L1_ent\| | [0, 1] | — | 确定性 |
| 88 | ✅ | `depth_l3_anchoring` | L3 锚定率 | \|L3_ent ∩ L2_ent\| / \|L2_ent\| | [0, 1] | — | 确定性 |
| 89 | ✅ | `depth_depth_quality` | 深度质量综合 | (l2_exp + l3_exp + span_12 + span_23) / 4 | [0, 1] | — | 确定性 |
| 90 | ✅ | `has_L1` / `has_L2` / `has_L3` | 层级存在标志 | 路径存在则 1.0 | {0, 1} | — | 确定性 |
| 91 | ✅ | `relation_diversity` | 关系多样性 | 唯一关系类型数 / 路径总数 | [0, 1] | — | 确定性 |
| 92 | ✅ | `elapsed_seconds` | 耗时 | 方法执行时间 (秒) | [0, +∞) | — | 确定性 |
| 93 | ✅ | `num_hypotheses` | 假设数量 | 有效假设输出数 | [0, +∞) | — | 确定性 |
| 94 | ✅ | `avg_hypothesis_length` | 平均假设长度 | 生成假设的平均字符数 | [0, +∞) | — | 确定性 |

---

## 指标体系架构图

```
CrossDisc Benchmark 评估指标体系 (10 维度 × 94 指标)
│
├── D1. 科学本体质量 (13 指标) ─────── "假设是否是一个好的科学命题？"
│   ├── LLM Judge 评分 (8 ✅)
│   └── 逻辑/哲学形式化 (5 🔲): 一致性、解释深度、经验内容、简约性、问题覆盖
│
├── D2. 可检验性 (6 指标) ──────────── "假设能否被实验证伪？"
│   ├── LLM Judge 四维度 (5 ✅)
│   └── 可证伪域量化 (1 🔲)
│
├── D3. 推理链结构 (14 指标) ────────── "推理路径逻辑上是否成立？"
│   ├── 路径一致性 P/R/F1 (4 ✅)
│   ├── 连贯性 + 衔接 (6 ✅)
│   ├── 结构元指标 (1 ✅)
│   └── 方向性 + 编辑距离 + 简约性 (3 🔲)
│
├── D4. 跨学科性 (7 指标) ──────────── "跨学科整合是否真实有效？"
│   ├── 整体多样性 (3 ✅): Rao-Stirling, 逆模块性, LLM Judge
│   └── 细粒度跨越 (4 🔲): 最大跳跃、平衡度、桥梁节点、发现概率
│
├── D5. 新颖性与创造力 (13 指标) ───── "假设是否提出了意外的知识连接？"
│   ├── 信息论新颖性 (3 ✅)
│   ├── 语义跨越距离 (2 ✅)
│   ├── Torrance TTCT (3 ✅) + 补全第4维 (1 🔲)
│   └── 独创性 + 远程联想 + 新颖常规平衡 + KGE惊异度 (4 🔲)
│
├── D6. GT 对齐 (9 指标) ──────────── "假设覆盖了多少已验证知识？"
│   ├── 概念级 P/R/F1 (3 ✅)
│   ├── 关系级 P/R/覆盖 (3 ✅)
│   ├── 路径级对齐 (2 ✅)
│   └── 逐步范式兼容 (1 🔲)
│
├── D7. KG 拓扑与推理 (10 指标) ───── "知识图谱结构和位置是否合理？"
│   ├── 图统计量 (8 ✅)
│   └── GT 图结构位置 (2 🔲): 结构洞桥接 + σ²变革性
│
├── D8. 可靠性与鲁棒性 (3 指标) ───── "结果是否可信、稳定、无幻觉？"  ⬅ 全新维度
│   └── 幻觉率 + 自一致性 + 事实精度 (3 🔲)
│
├── D9. 文本质量 (7 指标) ──────────── "文本与参考的表层相似度？"
│   └── BERTScore / ROUGE / BLEU (7 ✅)
│
└── D10. 层级递进与元数据 (12 指标) ── "L1→L3 是否逐层深化？效率如何？"
    └── 深度递进 + 结构元 + 效率 (12 ✅)
```

---

## 实现方式分布

| 实现方式 | 已实现 | 待补充 | 合计 | 说明 |
|---------|-------|-------|------|------|
| 确定性计算 | 32 | 9 | 41 | 无需外部模型，纯数值/集合运算 |
| 嵌入相似度 (SBERT) | 13 | 4 | 17 | 复用已有 SBERT 模型 |
| LLM Judge | 13 | 5 | 18 | 需 LLM API 调用 |
| NLI 模型 | 0 | 2 | 2 | 可复用已有 DeBERTa-xlarge-mnli |
| 图算法 (NetworkX) | 8 | 2 | 10 | 确定性，无需训练 |
| 多次采样 | 0 | 1 | 1 | 需多次独立生成 |
| KGE 模型 | 0 | 1 | 1 | 需在 GT KG 上训练 |
| 概率模型 | 0 | 1 | 1 | 基于 GT KG 统计预构建 |
| **合计** | **71** | **23** | **94** | |

---

## 层级变体说明

以下指标存在 L1/L2/L3 三个独立层级变体（如 `L1_consistency`, `L2_consistency`, `L3_consistency`）：

| 维度 | 基础指标 | 变体数 |
|------|---------|-------|
| D1 | innovation, feasibility, scientificity | 9 |
| D2 | testability | 3 |
| D3 | consistency, consistency_precision/recall/f1, coherence | 18 |
| D4 | rao_stirling | 3 |
| D5 | info_novelty, atypical_combination, bridging, embedding_bridging, fluency, flexibility, pairwise_diversity, elaboration 🔲 | 24 |
| D6 | concept_recall/precision/f1, relation_precision, relation_type_accuracy, evidence_coverage, path_alignment_best/mean | 24 |
| D7 | entity_coverage | 3 |

**总计层级变体**：约 84 个额外变体，加上 94 个基础指标，实际评估维度达 **170+**。

---

## 优先实现建议

### 第一优先级（实现成本低 + 理论价值高，纯确定性计算）

| 编号 | 指标 | 所属维度 | 理由 |
|------|------|---------|------|
| N3 | `parsimony` | D1/D3 | 无需任何模型，直接统计符号数 |
| N6 | `disciplinary_leap_index` | D4 | 复用已有 taxonomy_distance |
| N7 | `discipline_balance` | D4 | 标准 Gini 系数 |
| N13 | `causal_direction_accuracy` | D3 | 在已有 consistency 基础上增加方向统计 |
| N22 | `novelty_convention_balance` | D5 | 在已有 GT 匹配逻辑上增加比例统计 |

### 第二优先级（复用已有模型基础设施）

| 编号 | 指标 | 所属维度 | 理由 |
|------|------|---------|------|
| N4 | `internal_consistency` | D1 | 复用已有 DeBERTa-xlarge-mnli |
| N17 | `hallucination_rate` | D8 | 复用已有 SBERT + 字符串匹配 |
| N19 | `factual_precision` | D8 | 复用已有 DeBERTa-xlarge-mnli |
| N16 | `remote_association_index` | D5 | 复用已有 SBERT |
| N15 | `originality_score` | D5 | 复用已有 SBERT |

### 第三优先级（需额外 LLM 调用）

| 编号 | 指标 | 所属维度 | 理由 |
|------|------|---------|------|
| N5 | `explanatory_depth` | D1 | 需逐步 LLM 分类 |
| N2 | `empirical_content` | D1 | 需逐步 LLM 分类 |
| N23 | `problem_solving_coverage` | D1 | 需 LLM 判断 |
| N1 | `falsifiability_scope` | D2 | 需 LLM 枚举 |

### 第四优先级（需额外基础设施）

| 编号 | 指标 | 所属维度 | 理由 |
|------|------|---------|------|
| N18 | `self_consistency` | D8 | 需多次采样运行 |
| N11 | `link_prediction_surprisal` | D5 | 需训练 KGE 模型 |
| N10/N20 | `structural_hole_bridging` / `sigma2` | D7 | 需在全量 GT KG 上计算 BC |

---

## 完整参考文献

| # | 完整引用 |
|---|---------|
| 1 | Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q., & Artzi, Y. (2020). BERTScore: Evaluating Text Generation with BERT. *ICLR 2020*. |
| 2 | Lin, C.-Y. (2004). ROUGE: A Package for Automatic Evaluation of Summaries. *ACL-04 Workshop*, 74-81. |
| 3 | Papineni, K., Roukos, S., Ward, T., & Zhu, W.-J. (2002). BLEU: a Method for Automatic Evaluation of Machine Translation. *ACL 2002*, 311-318. |
| 4 | Liu, Y., Iter, D., Xu, Y., et al. (2023). G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment. *EMNLP 2023*. |
| 5 | Popper, K. R. (1959). *The Logic of Scientific Discovery*. London: Hutchinson. |
| 6 | Popper, K. R. (1963). *Conjectures and Refutations*. London: Routledge. |
| 7 | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions* (2nd ed.). University of Chicago Press. |
| 8 | Lakatos, I. (1978). *The Methodology of Scientific Research Programmes*. Cambridge University Press. |
| 9 | Laudan, L. (1977). *Progress and Its Problems: Toward a Theory of Scientific Growth*. University of California Press. |
| 10 | Laudan, L., Donovan, A., Laudan, R., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. |
| 11 | Si, C., Yang, D., & Hashimoto, T. (2024). Can LLMs Generate Novel Research Ideas? *ICLR 2025*. arXiv:2409.04109. |
| 12 | Torrance, E. P. (1966). *Torrance Tests of Creative Thinking*. Princeton, NJ: Personnel Press. |
| 13 | Kim, K. H. (2006). Can We Trust Creativity Tests? A Review of the TTCT. *Creativity Research Journal*, 18(1), 3-14. |
| 14 | Mednick, S. A. (1962). The Associative Basis of the Creative Process. *Psychological Review*, 69(3), 220-232. |
| 15 | Simon, H. A., Langley, P., & Bradshaw, G. (1983). Scientific Discovery as Problem Solving. *Synthese*, 47, 1-27. |
| 16 | Machamer, P., Darden, L., & Craver, C. F. (2000). Thinking About Mechanisms. *Philosophy of Science*, 67(1), 1-25. |
| 17 | Woodward, J. (2003). *Making Things Happen: A Theory of Causal Explanation*. Oxford University Press. |
| 18 | Pearl, J. (2009). *Causality* (2nd ed.). Cambridge University Press. |
| 19 | Sober, E. (2015). *Ockham's Razors: A User's Manual*. Cambridge University Press. |
| 20 | Shannon, C. E. (1948). A Mathematical Theory of Communication. *Bell System Technical Journal*, 27(3), 379-423. |
| 21 | Stirling, A. (2007). A General Framework for Analysing Diversity in Science, Technology and Society. *J. R. Soc. Interface*, 4(15), 707-719. |
| 22 | Gini, C. (1912). Variabilità e Mutabilità. *Studi Economico-Giuridici*, 3, 3-159. |
| 23 | Uzzi, B., Mukherjee, S., Stringer, M., & Jones, B. F. (2013). Atypical Combinations and Scientific Impact. *Science*, 342(6157), 468-472. |
| 24 | Fortunato, S., Bergstrom, C. T., Börner, K., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. |
| 25 | Coccia, M. (2022). Probability of Discoveries Between Research Fields. *Technology in Society*, 68, 101874. |
| 26 | Bettencourt, L. M. A., Kaiser, D. I., & Kaur, J. (2009). Scientific Discovery and Topological Transitions in Collaboration Networks. *J. Informetrics*, 3(3), 210-221. |
| 27 | Chen, C., Chen, Y., Horowitz, M., et al. (2009). Towards an Explanatory and Computational Theory of Scientific Discovery. *J. Informetrics*, 3(3), 191-209. |
| 28 | Burt, R. S. (2004). Structural Holes and Good Ideas. *American Journal of Sociology*, 110(2), 349-399. |
| 29 | Freeman, L. C. (1977). A Set of Measures of Centrality Based on Betweenness. *Sociometry*, 40(1), 35-41. |
| 30 | Newman, M. E. J. (2006). Modularity and Community Structure in Networks. *PNAS*, 103(23), 8577-8582. |
| 31 | Watts, D. J. & Strogatz, S. H. (1998). Collective Dynamics of Small-World Networks. *Nature*, 393, 440-442. |
| 32 | Kleinberg, J. (2003). Bursty and Hierarchical Structure in Streams. *Data Mining and Knowledge Discovery*, 7(4), 373-397. |
| 33 | Bordes, A., Usunier, N., Garcia-Duran, A., et al. (2013). Translating Embeddings for Modeling Multi-relational Data. *NeurIPS 2013*. |
| 34 | Sun, Z., Deng, Z.-H., Nie, J.-Y., & Tang, J. (2019). RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space. *ICLR 2019*. |
| 35 | Gao, X., Xiao, B., Tao, D., & Li, X. (2010). A Survey of Graph Edit Distance. *Pattern Analysis and Applications*, 13(1), 113-129. |
| 36 | Bunke, H. & Allermann, G. (1983). Inexact Graph Matching for Structural Pattern Recognition. *Pattern Recognition Letters*, 1(4), 245-253. |
| 37 | Wang, X., Wei, J., Schuurmans, D., et al. (2023). Self-Consistency Improves Chain of Thought Reasoning. *ICLR 2023*. |
| 38 | Min, S., Krishna, K., Lyu, X., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision. *EMNLP 2023*. |
| 39 | He, P., Liu, X., Gao, J., & Chen, W. (2021). DeBERTa: Decoding-enhanced BERT with Disentangled Attention. *ICLR 2021*. |
| 40 | Li, J., Cheng, X., Zhao, W. X., et al. (2023). HaluEval: A Large-Scale Hallucination Evaluation Benchmark. *EMNLP 2023*. |
| 41 | Williams, A., Nangia, N., & Bowman, S. R. (2018). A Broad-Coverage Challenge Corpus for Sentence Understanding through Inference. *NAACL-HLT 2018*. |
| 42 | Ding, K., Feng, Y., Wang, X., et al. (2025). Bridging Data and Discovery: A Survey on Knowledge Graphs in AI for Science. |
| 43 | Zhang, J., et al. (2025). Exploring the Role of Large Language Models in the Scientific Method. *npj AI*. |
| 44 | Gridach, M., et al. (2025). Agentic AI for Scientific Discovery: A Survey. *ICLR 2025*. |
| 45 | Ruan, Y., et al. (2025). LiveIdeaBench: Evaluating LLMs' Divergent Thinking for Scientific Idea Generation. |
| 46 | Kenett, Y. N. & Faust, M. (2019). A Semantic Network Cartography of the Creative Mind. *Trends in Cognitive Sciences*, 23(4), 271-274. |
| 47 | Wang, D., Song, C., & Barabási, A.-L. (2013). Quantifying Long-term Scientific Impact. *Science*, 342(6154), 127-132. |
| 48 | Leydesdorff, L., Wagner, C. S., & Bornmann, L. (2018). Betweenness and Diversity in Journal Citation Networks. *Scientometrics*, 114(2), 567-592. |
| 49 | Dunbar, K. (1993). Concept Discovery in a Scientific Domain. *Cognitive Science*, 17(3), 397-434. |
| 50 | Lu, C., Lu, C., Lange, R. T., et al. (2024). The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery. *arXiv:2408.06292*. |

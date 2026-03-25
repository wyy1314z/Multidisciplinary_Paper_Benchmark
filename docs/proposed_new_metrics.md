# CrossDisc Benchmark 建议补充指标详细表

> 共 **23 个新指标**，分属 6 大维度，与现有 71 个指标无重叠。
> 每个指标包含：定义、计算公式、伪代码、输入/输出规格、理论依据及完整参考文献。

---

## 一、科学哲学层 — 假设本体质量（5 个指标）

### N1. 可证伪域宽度 (Falsifiability Scope, FS)

| 字段 | 内容 |
|------|------|
| **指标编号** | N1 |
| **英文名** | Falsifiability Scope |
| **中文名** | 可证伪域宽度 |
| **定义** | 衡量一个假设所"禁止"的可观测结果在总可观测结果空间中的比例。一个好的科学假设应当排除尽可能多的可能观测，从而具有更大的经验内容和更强的可证伪性。 |
| **计算公式** | FS(H) = \|O_refute(H)\| / \|O_all\| |
| **变量说明** | O_refute(H) = 能推翻假设 H 的可观测实验结果集合；O_all = 该研究领域内所有合理的可观测实验结果集合 |
| **伪代码** | (1) 给定假设 H 及其所属学科领域 D；(2) 使用 LLM 枚举该领域在当前技术条件下可设计的标准实验结果类型 O_all（如"正相关/负相关/无关/U型曲线/阈值效应"等 N 类）；(3) 使用 LLM 判断哪些结果类型会推翻 H，得到 O_refute；(4) FS = len(O_refute) / len(O_all) |
| **取值范围** | [0, 1]，越高表示假设越具可证伪性 |
| **计算类型** | LLM + 枚举 |
| **与现有指标差异** | 现有 `falsifiability`（eval_prompts.py）为 LLM 主观打分 [0,10]，依赖评审者对"可证伪"概念的理解；本指标将其转化为可计算的集合比例，结果更客观、可复现 |
| **理论依据** | Popper 认为科学理论的价值与其"经验内容"成正比，即理论所禁止的可能观测越多，理论越有信息量。一个不排除任何观测结果的"假设"不构成科学命题。FS 直接量化了这一核心原则。 |
| **参考文献 1** | Popper, K. R. (1959). *The Logic of Scientific Discovery*. London: Hutchinson. [原版德文: Logik der Forschung, 1934]. — 第 6 章"可证伪性的程度"：提出以"禁止的基本陈述类"的大小衡量理论的经验内容。 |
| **参考文献 2** | Popper, K. R. (1963). *Conjectures and Refutations: The Growth of Scientific Knowledge*. London: Routledge. — "大胆的理论（bold conjectures）比谨慎的理论更有科学价值，因为它们更容易被证伪。" |
| **参考文献 3** | Si, C., Yang, D., & Hashimoto, T. (2024). Can LLMs Generate Novel Research Ideas? A Large-Scale Human Study with 100+ NLP Researchers. *ICLR 2025*. arXiv:2409.04109. — 将 testability 作为假设评估维度之一，但仅用 1-10 整数评分。 |

---

### N2. 经验内容 (Empirical Content, EC)

| 字段 | 内容 |
|------|------|
| **指标编号** | N2 |
| **英文名** | Empirical Content |
| **中文名** | 经验内容（预测-追溯比） |
| **定义** | 衡量假设推理链中"前瞻性可独立验证的预测"（prediction）与"对已知事实的事后解释"（retrodiction）之间的比率。高质量假设应产生超越输入信息的新预测，而非仅重新包装已知结论。 |
| **计算公式** | EC(H) = n_prediction / (n_prediction + n_retrodiction) |
| **变量说明** | n_prediction = 路径中属于 prediction（新的可验证预期）的 claim 数；n_retrodiction = 属于 retrodiction（对摘要/已知事实的重述或重新解释）的 claim 数 |
| **伪代码** | (1) 对路径中每步 claim_s；(2) 使用 LLM 判断 claim_s 属于 prediction（该声明提出了原论文中未明确陈述的新预期，可通过独立实验验证）还是 retrodiction（该声明本质上是对原论文摘要或已知事实的重新表述）；(3) EC = n_prediction / (n_prediction + n_retrodiction)；若全为 prediction 则 EC = 1.0 |
| **取值范围** | [0, 1]，越高表示假设的前瞻性越强 |
| **计算类型** | LLM 分类 |
| **与现有指标差异** | 现有 `novelty` 评分衡量假设是否"超越原论文"，但不区分具体 claim 是预测还是追溯；本指标在 claim 粒度做分类 |
| **理论依据** | Popper 强调"真正的预测"远比"事后解释"有价值：能解释一切的理论实际上什么也没说。Lakatos 将此区别形式化为 progressive（产生新预测）vs degenerating（仅做事后修补）研究纲领的核心判据。 |
| **参考文献 1** | Popper, K. R. (1959). *The Logic of Scientific Discovery*. London: Hutchinson. — 第 10 章"确证或者一个理论如何经受住检验"：prediction 比 retrodiction 具有更高的确证价值。 |
| **参考文献 2** | Lakatos, I. (1978). *The Methodology of Scientific Research Programmes*. Cambridge University Press. — progressive research programme 必须产生 novel predictions，否则为 degenerating。 |
| **参考文献 3** | Laudan, L., Donovan, A., Laudan, R., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. — Thesis 10-11: 研究纲领的进步性标准在于是否预测了前任理论未预测的新现象。 |

---

### N3. 简约性 (Parsimony)

| 字段 | 内容 |
|------|------|
| **指标编号** | N3 |
| **英文名** | Parsimony |
| **中文名** | 简约性 |
| **定义** | 衡量假设推理链在表达同等推理深度时使用的概念和关系符号的经济程度。好的假设应以最少的概念元素承载最丰富的推理内容，避免冗余的中间实体和关系。 |
| **计算公式** | Parsimony(H) = 1 - (U_ent + U_rel) / (num_steps × 2 + num_steps) |
| **变量说明** | U_ent = 路径中唯一实体数（head ∪ tail 去重）；U_rel = 唯一关系类型数；num_steps = 路径步数；分母 = 理论上限（每步 2 个新实体 + 1 个新关系） |
| **伪代码** | (1) entities = set(); rels = set(); (2) for step in path: entities.add(head), entities.add(tail), rels.add(relation); (3) max_symbols = num_steps * 3; (4) Parsimony = 1.0 - (len(entities) + len(rels)) / max_symbols; (5) return max(Parsimony, 0.0) |
| **取值范围** | [0, 1]，越高表示越简约（符号复用率越高） |
| **计算类型** | 确定性计算（无需 LLM 或嵌入模型） |
| **与现有指标差异** | 现有 `avg_path_length` 仅统计步数，不衡量符号效率；现有 `entity_coverage` 在 Torrance 框架下鼓励实体多样性（与简约性方向相反）；本指标提供互补视角 |
| **理论依据** | Kuhn 将 simplicity 列为科学理论五大评价标准之一。Simon 在 BACON 系统中将简约性作为核心启发式：描述性概括应使用最少数量的自由参数。Occam's razor 是科学方法论的基本原则。 |
| **参考文献 1** | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions* (2nd ed.). Chicago: University of Chicago Press. — Postscript, p.185: simplicity 作为理论选择的五个标准值之一。 |
| **参考文献 2** | Simon, H. A., Langley, P., & Bradshaw, G. (1983). Scientific Discovery as Problem Solving. *Synthese*, 47, 1-27. — BACON.4 系统：简约性启发式（fewer free parameters = better law）。 |
| **参考文献 3** | Sober, E. (2015). *Ockham's Razors: A User's Manual*. Cambridge University Press. — 简约性原则在科学推理中的系统论证。 |

---

### N4. 内部一致性 (Internal Consistency, IC)

| 字段 | 内容 |
|------|------|
| **指标编号** | N4 |
| **英文名** | Internal Consistency |
| **中文名** | 内部一致性 |
| **定义** | 检测假设推理链中是否存在逻辑矛盾。如果路径中的某步 claim 与另一步 claim 构成语义蕴含矛盾（entailment contradiction），则该假设的内部一致性受损。 |
| **计算公式** | IC(H) = 1 - \|{(i,j) : NLI(claim_i, claim_j) = contradiction}\| / C(n, 2) |
| **变量说明** | NLI(a, b) = 自然语言推理模型对语句对 (a, b) 的判定结果（entailment / neutral / contradiction）；C(n, 2) = n 步 claim 的所有两两组合数 |
| **伪代码** | (1) claims = [step.claim for step in path]; (2) n = len(claims); (3) contradictions = 0; (4) for i in range(n): for j in range(i+1, n): if nli_model(claims[i], claims[j]) == 'contradiction': contradictions += 1; (5) IC = 1.0 - contradictions / (n*(n-1)/2) |
| **取值范围** | [0, 1]，1.0 = 完全一致，0.0 = 所有 claim 对均矛盾 |
| **计算类型** | NLI 模型（可复用已有 DeBERTa-xlarge-mnli） |
| **与现有指标差异** | 现有 `chain_coherence` 度量的是相邻步骤之间的 **语义连续性**（通过嵌入余弦相似度），高相似度不等于无矛盾；本指标直接检测 **逻辑矛盾** |
| **理论依据** | Kuhn 将 consistency 列为五大标准之一，包含内部自洽和外部兼容两层含义。Laudan 进一步强调"概念连贯性与清晰性"是理论评价的首要条件。一个内部矛盾的假设在逻辑上无法同时为真，因此不构成有效科学命题。 |
| **参考文献 1** | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions*. — Postscript: consistency 既指内部自洽也指与其他理论的兼容。 |
| **参考文献 2** | Laudan, L., Donovan, A., Laudan, R., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. — Thesis 22: 概念连贯性和清晰性是理论评价核心。 |
| **参考文献 3** | Williams, A., Nangia, N., & Bowman, S. R. (2018). A Broad-Coverage Challenge Corpus for Sentence Understanding through Inference. *NAACL-HLT 2018*. — MultiNLI 数据集及 NLI 模型方法论。 |

---

### N5. 解释深度 (Explanatory Depth, ED)

| 字段 | 内容 |
|------|------|
| **指标编号** | N5 |
| **英文名** | Explanatory Depth |
| **中文名** | 解释深度 |
| **定义** | 衡量假设推理链中每一步关系所达到的解释层次：纯相关（两个现象共同出现）、因果方向（A 导致 B）、还是机制解释（A 通过具体的物理/化学/生物过程 M 导致 B）。机制解释被认为是科学解释的最高层次。 |
| **计算公式** | ED(H) = sum_(s in steps) w(s) / num_steps |
| **变量说明** | w(s) 为每步的解释层次权重：correlation = 0.0, causal_direction = 0.5, mechanistic = 1.0 |
| **伪代码** | (1) for each step s in path: (2) 使用 LLM 判断 relation + claim 属于三个层次之一：a) correlation（仅描述共现/统计关联），b) causal_direction（指明因果方向但不解释中间过程），c) mechanistic（说明具体的分子/物理/信息传递机制）；(3) ED = sum(weights) / num_steps |
| **取值范围** | [0, 1]，越高表示机制解释比例越大 |
| **计算类型** | LLM 三级分类 |
| **与现有指标差异** | 现有 `scientificity` 是整体打分，不区分各步的解释层次；本指标逐步骤评估，暴露推理链中的"弱解释环节" |
| **理论依据** | Simon 在 BACON 系统分析中区分了"描述性定律"（descriptive laws，如 Ohm's law 的数值关系）与"解释性定律"（explanatory laws，引入内在属性如"电阻"来解释为何关系成立）。解释性定律具有更强的科学价值，因为它们揭示了因果机制而非表面相关。 |
| **参考文献 1** | Simon, H. A., Langley, P., & Bradshaw, G. (1983). Scientific Discovery as Problem Solving. *Synthese*, 47, 1-27. — 描述性 vs 解释性定律的形式化区分：解释性定律引入"intrinsic properties"。 |
| **参考文献 2** | Machamer, P., Darden, L., & Craver, C. F. (2000). Thinking About Mechanisms. *Philosophy of Science*, 67(1), 1-25. — 机制解释的哲学基础：entities + activities + organization。 |
| **参考文献 3** | Woodward, J. (2003). *Making Things Happen: A Theory of Causal Explanation*. Oxford University Press. — interventionist 因果理论：因果 vs 相关的形式化标准。 |

---

## 二、跨学科发现层 — 学科桥接质量（4 个指标）

### N6. 学科跨越系数 (Disciplinary Leap Index, DLI)

| 字段 | 内容 |
|------|------|
| **指标编号** | N6 |
| **英文名** | Disciplinary Leap Index |
| **中文名** | 学科跨越系数（单步最大跳跃） |
| **定义** | 路径中所有步骤中，单步实现的最大学科间距离。与 Rao-Stirling 度量整体多样性不同，DLI 捕捉假设中最"大胆"的那一跳——往往是跨学科突破的关键点。 |
| **计算公式** | DLI(H) = max_(s in steps) d_tax(disc(head_s), disc(tail_s)) |
| **变量说明** | d_tax(A, B) = 学科分类树中 A 与 B 之间的归一化 LCA 距离（复用已有 taxonomy_distance 函数）；disc(entity) = 该实体所属学科 |
| **伪代码** | (1) max_leap = 0.0; (2) for step in path: disc_h = node_disciplines[step.head]; disc_t = node_disciplines[step.tail]; leap = taxonomy_distance(disc_h, disc_t, disc_paths, max_depth); max_leap = max(max_leap, leap); (3) return max_leap |
| **取值范围** | [0, 1]，0 = 同一学科内，1 = 分类树中最远的两个学科 |
| **计算类型** | 确定性计算（复用已有 taxonomy_distance） |
| **与现有指标差异** | 现有 `rao_stirling` 是加权求和反映整体多样性分布；DLI 只取极值，专门捕捉"最大胆的一跳"。两者互补：Rao-Stirling 高但 DLI 低说明多学科均匀分布但无深度跳跃；DLI 高但 Rao-Stirling 低说明有单次跨越但整体学科单一。 |
| **理论依据** | Fortunato et al. (2018) 在 Science of Science 综述中提出"intellectual distance"——知识组合中最远距离跨越与高影响力正相关。Coccia (2022) 的跨领域发现概率模型也表明，跨越距离越大的领域对之间的发现越稀有也越有潜在价值。 |
| **参考文献 1** | Fortunato, S., Bergstrom, C. T., Börner, K., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. — "atypical combinations" 和 "intellectual distance" 章节：高影响力论文的特征之一是结合了远距离知识。 |
| **参考文献 2** | Coccia, M. (2022). Probability of Discoveries Between Research Fields to Explain Scientific and Technological Change. *Technology in Society*, 68, 101874. — 跨领域发现的 Poisson 模型：跨越距离越远，发现概率越低但价值越高。 |
| **参考文献 3** | Stirling, A. (2007). A General Framework for Analysing Diversity in Science, Technology and Society. *Journal of the Royal Society Interface*, 4(15), 707-719. — 多样性 = variety + balance + disparity，DLI 是 disparity 维度的极值度量。 |

---

### N7. 学科分布平衡度 (Discipline Balance)

| 字段 | 内容 |
|------|------|
| **指标编号** | N7 |
| **英文名** | Discipline Balance |
| **中文名** | 学科分布平衡度 |
| **定义** | 衡量假设路径中各学科实体的分布均匀程度。理想的跨学科假设应当在涉及的各学科之间实现相对均衡的覆盖，而非某一学科主导、其他学科仅点缀出现。 |
| **计算公式** | Balance(H) = 1 - Gini({p_1, p_2, ..., p_k}) |
| **变量说明** | p_i = 第 i 个学科的实体频率（出现次数 / 总实体数）；k = 路径涉及的学科数；Gini 系数 = (2 * sum_(i=1 to k) i * sorted_p_i) / (k * sum(p)) - (k+1)/k |
| **伪代码** | (1) disc_counts = Counter(); (2) for step in path: for field in (head, tail): disc = node_disciplines[entity]; disc_counts[disc] += 1; (3) freqs = sorted(disc_counts.values()); k = len(freqs); total = sum(freqs); (4) gini = sum((2*i - k - 1) * freqs[i-1] for i in range(1, k+1)) / (k * total); (5) return 1.0 - gini |
| **取值范围** | [0, 1]，1.0 = 完全均匀分布，0.0 = 完全被单一学科主导 |
| **计算类型** | 确定性计算 |
| **与现有指标差异** | Rao-Stirling 综合了 variety + balance + disparity 三个维度；本指标单独抽出 balance 分量。当 Rao-Stirling 分数低时，可通过 Balance 诊断是"学科种类太少"（variety 低）还是"分布不均"（balance 低）。 |
| **理论依据** | Stirling (2007) 明确指出多样性包含三个不可约维度：variety（类别数）、balance（分布均匀度）、disparity（类别间差异度），三者不可相互替代。现有 Rao-Stirling 将三者压缩为一个数值，丢失了诊断信息。 |
| **参考文献 1** | Stirling, A. (2007). A General Framework for Analysing Diversity in Science, Technology and Society. *Journal of the Royal Society Interface*, 4(15), 707-719. — 三维多样性框架的原始论文。 |
| **参考文献 2** | Gini, C. (1912). Variabilità e Mutabilità. *Studi Economico-Giuridici della Regia Università di Cagliari*, 3, 3-159. — Gini 系数的原始定义。 |
| **参考文献 3** | Leydesdorff, L., Wagner, C. S., & Bornmann, L. (2018). Betweenness and Diversity in Journal Citation Networks as Measures of Interdisciplinarity. *Scientometrics*, 114(2), 567-592. — 将 Stirling 三维分解应用于科学计量学的实证研究。 |

---

### N8. 边界跨越者比例 (Boundary Spanner Score, BSS)

| 字段 | 内容 |
|------|------|
| **指标编号** | N8 |
| **英文名** | Boundary Spanner Score |
| **中文名** | 边界跨越者比例 |
| **定义** | 路径中"边界跨越者"（boundary spanner）实体的比例——即在 GT 知识图谱中同时连接两个或以上不同学科实体的概念节点。这些实体是跨学科桥梁的承载者。 |
| **计算公式** | BSS(H) = \|{e in entities(H) : \|discs_neighbors(e, G_GT)\| >= 2}\| / \|entities(H)\| |
| **变量说明** | entities(H) = 路径中所有唯一实体；discs_neighbors(e, G_GT) = 实体 e 在 GT KG 中所有邻居节点所属的学科集合 |
| **伪代码** | (1) 构建 GT KG 的邻接表 adj_list; (2) entities = unique(all heads + tails in path); (3) spanners = 0; (4) for e in entities: neighbors = adj_list.get(e, []); neighbor_discs = set(node_disciplines[n] for n in neighbors); if len(neighbor_discs) >= 2: spanners += 1; (5) return spanners / len(entities) |
| **取值范围** | [0, 1]，越高表示路径中跨学科桥梁实体越多 |
| **计算类型** | 确定性计算（基于 GT KG 图结构） |
| **与现有指标差异** | 现有指标均以"路径"或"学科分布"为分析单位；本指标以 **单个实体** 为分析单位，识别哪些概念是跨学科连接的"枢纽" |
| **理论依据** | Bettencourt et al. (2009) 发现科学领域的拓扑转变（giant component 形成）依赖于关键的桥梁节点。Chen et al. (2009) 使用 betweenness centrality 识别变革性发现，本质上也是在识别"结构洞"中的桥梁。社会网络理论中 Burt 的 structural hole 概念直接适用。 |
| **参考文献 1** | Bettencourt, L. M. A., Kaiser, D. I., & Kaur, J. (2009). Scientific Discovery and Topological Transitions in Collaboration Networks. *Journal of Informetrics*, 3(3), 210-221. — 协作网络中 giant component 的形成标志着科学发现的结晶。 |
| **参考文献 2** | Burt, R. S. (2004). Structural Holes and Good Ideas. *American Journal of Sociology*, 110(2), 349-399. — 结构洞理论：连接不同群体的桥梁节点拥有信息优势和创新优势。 |
| **参考文献 3** | Chen, C., Chen, Y., Horowitz, M., et al. (2009). Towards an Explanatory and Computational Theory of Scientific Discovery. *Journal of Informetrics*, 3(3), 191-209. — σ² 指标使用 betweenness centrality 识别变革性发现。 |

---

### N9. 发现概率估计 (Discovery Probability, DP)

| 字段 | 内容 |
|------|------|
| **指标编号** | N9 |
| **英文名** | Discovery Probability |
| **中文名** | 发现概率估计 |
| **定义** | 基于学科对之间的历史发现概率，估计假设路径中所有跨学科连接同时被发现的联合概率。概率越低说明假设越"稀有"，但需与其他质量指标联合解读（低概率可能意味着高价值的突破，也可能意味着不合理的臆想）。 |
| **计算公式** | DP(H) = prod_(s in steps) Prd(disc(head_s), disc(tail_s)) |
| **变量说明** | Prd(A, B) = 学科 A 和 B 之间的发现概率（预构建的学科对→概率映射表）；disc(entity) = 实体所属学科 |
| **伪代码** | (1) 预构建学科对发现概率表 Prd（可基于 GT KG 中各学科对之间的关系密度估计：Prd(A,B) = edges(A,B) / (nodes(A) * nodes(B))）；(2) prob = 1.0; (3) for step in path: d_h = disc(step.head); d_t = disc(step.tail); if d_h != d_t: prob *= Prd.get((d_h, d_t), default_low_prob); (4) return prob |
| **取值范围** | [0, 1]，越低表示假设中的跨学科连接越稀有 |
| **计算类型** | 概率模型（基于 GT KG 统计） |
| **与现有指标差异** | 现有 `atypical_combination` 基于三元组共现频率做 z-score；本指标从学科对粒度出发，使用 Poisson 概率模型框架 |
| **理论依据** | Coccia (2022) 提出跨领域发现遵循 Poisson 过程，各学科对之间的发现概率 Prd 可从历史数据估计。物理学和医学的 Prd 约为 0.0118，意味着在一个 10 年窗口内，某学科对产生发现的概率约 11%。将此概率链式组合可估计多步跨学科路径的联合发现概率。 |
| **参考文献 1** | Coccia, M. (2022). Probability of Discoveries Between Research Fields to Explain Scientific and Technological Change. *Technology in Society*, 68, 101874. — 跨领域发现的 Poisson 模型和概率量化框架。 |
| **参考文献 2** | Fortunato, S., Bergstrom, C. T., Börner, K., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. — 讨论了跨领域合作和发现的统计规律。 |
| **参考文献 3** | Uzzi, B., Mukherjee, S., Stringer, M., & Jones, B. F. (2013). Atypical Combinations and Scientific Impact. *Science*, 342(6157), 468-472. — 非典型组合的频率统计方法论。 |

---

## 三、知识图谱推理层 — 图结构分析（4 个指标）

### N10. 结构洞桥接 (Structural Hole Bridging, SHB)

| 字段 | 内容 |
|------|------|
| **指标编号** | N10 |
| **英文名** | Structural Hole Bridging |
| **中文名** | 结构洞桥接度 |
| **定义** | 路径中实体在 GT 知识图谱中的平均介数中心性。高介数中心性意味着实体位于不同知识社区之间的"桥梁"位置，连接了原本不相通的知识区域。如果假设选用了高介数实体构建推理链，说明假设正在"穿越"知识的结构洞。 |
| **计算公式** | SHB(H) = mean_(e in entities(H)) BC(e, G_GT) |
| **变量说明** | BC(e, G_GT) = 实体 e 在 GT 知识图谱 G_GT 中的归一化介数中心性（范围 [0,1]）；entities(H) = 路径中所有唯一实体 |
| **伪代码** | (1) G_GT = 从 benchmark_dataset 构建完整 GT 知识图谱; (2) bc = nx.betweenness_centrality(G_GT, normalized=True); (3) entities = unique(all heads + tails in path); (4) scores = [bc.get(e, 0.0) for e in entities]; (5) return mean(scores) |
| **取值范围** | [0, 1]，越高表示路径实体在 GT KG 中越处于"桥梁"位置 |
| **计算类型** | 图算法（NetworkX betweenness_centrality） |
| **与现有指标差异** | 现有 `avg_betweenness` 在 **生成图** 上计算；本指标在 **GT 图** 上计算——衡量的是路径实体在已有知识全景中的结构位置，而非生成子图的内部结构 |
| **理论依据** | Chen et al. (2009) 验证了 betweenness centrality 可以识别诺奖级发现：Marshall-1988 在 H. pylori 引用网络中的介数中心性远高于该领域平均水平。结构洞理论（Burt 2004）表明，占据结构洞位置的行动者具有信息优势。 |
| **参考文献 1** | Chen, C., Chen, Y., Horowitz, M., et al. (2009). Towards an Explanatory and Computational Theory of Scientific Discovery. *Journal of Informetrics*, 3(3), 191-209. — σ² = burstness × centrality 用于识别变革性发现。 |
| **参考文献 2** | Freeman, L. C. (1977). A Set of Measures of Centrality Based on Betweenness. *Sociometry*, 40(1), 35-41. — 介数中心性的原始定义。 |
| **参考文献 3** | Burt, R. S. (2004). Structural Holes and Good Ideas. *American Journal of Sociology*, 110(2), 349-399. — 结构洞与创新优势的关系。 |

---

### N11. 链接预测惊异度 (Link Prediction Surprisal, LPS)

| 字段 | 内容 |
|------|------|
| **指标编号** | N11 |
| **英文名** | Link Prediction Surprisal |
| **中文名** | 链接预测惊异度 |
| **定义** | 使用在 GT 知识图谱上训练的知识图谱嵌入（KGE）模型，计算假设路径中各步三元组的负对数预测概率。惊异度越高说明该关系在已有知识图谱的语义空间中越"意外"，即越具有新颖性。 |
| **计算公式** | LPS(H) = -mean_(s in steps) log_2 P_KGE(tail_s \| head_s, rel_s) |
| **变量说明** | P_KGE(t\|h,r) = KGE 模型（如 TransE, RotatE, ComplEx）对三元组 (h, r, t) 的归一化预测概率 |
| **伪代码** | (1) 在 GT KG 全量三元组上训练 KGE 模型（TransE/RotatE）; (2) for step in path: score = kge_model.score(head, rel, tail); prob = softmax_normalize(score); surprisal = -log2(prob); (3) return mean(surprisals) |
| **取值范围** | [0, +inf)，越高越"惊异"/新颖 |
| **计算类型** | KGE 模型（需训练，可用 PyKEEN/DGL-KE 库） |
| **与现有指标差异** | 现有 `info_novelty` 使用简单的频率统计 + Laplace 平滑；LPS 使用 **学习到的嵌入空间** 中的语义概率，能捕捉更复杂的结构模式（如传递性、对称性、组合性） |
| **理论依据** | Ding et al. (2025) 在 KG4Science 综述中将 MRR 和 Hits@K 列为 KG 推理评估的标准范式。KGE 将实体和关系编码到连续向量空间中，能学习到频率统计无法捕捉的隐式模式（如 A→B 和 B→C 暗示 A→C）。 |
| **参考文献 1** | Ding, K., Feng, Y., Wang, X., et al. (2025). Bridging Data and Discovery: A Survey on Knowledge Graphs in AI for Science. *arXiv preprint*. — KG 嵌入用于科学发现的综述。 |
| **参考文献 2** | Bordes, A., Usunier, N., Garcia-Duran, A., Weston, J., & Yakhnenko, O. (2013). Translating Embeddings for Modeling Multi-relational Data. *NeurIPS 2013*. — TransE 模型原始论文。 |
| **参考文献 3** | Sun, Z., Deng, Z.-H., Nie, J.-Y., & Tang, J. (2019). RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space. *ICLR 2019*. arXiv:1902.10197. — RotatE 模型，能建模对称/反对称/逆/组合关系。 |

---

### N12. 图编辑距离 (Graph Edit Distance, GED)

| 字段 | 内容 |
|------|------|
| **指标编号** | N12 |
| **英文名** | Normalized Graph Edit Distance |
| **中文名** | 归一化图编辑距离 |
| **定义** | 将生成路径和最接近的 GT 路径分别转换为有向子图后，计算将生成子图转换为 GT 子图所需的最少编辑操作数（节点插入/删除/替换 + 边插入/删除/替换），除以两图总操作空间进行归一化。 |
| **计算公式** | GED(H, GT) = min_(gt in GT_paths) edit_dist(G_H, G_gt) / max(\|G_H\| + \|G_gt\|, 1) |
| **变量说明** | G_H = 生成路径对应的有向子图（节点=实体，边=关系）；G_gt = GT 路径对应的子图；edit_dist = 节点级 + 边级编辑操作总数；\|G\| = 图的节点数 + 边数 |
| **伪代码** | (1) 将 path 转为 DiGraph: for step in path: G.add_edge(head, tail, rel=relation); (2) 对每条 GT 路径同样构建 DiGraph; (3) 使用近似 GED 算法（如 nx.optimize_graph_edit_distance 或贪心匹配）; (4) 取最小 GED / 归一化因子 |
| **取值范围** | [0, 1]，0 = 与某条 GT 路径完全相同，1 = 完全不同 |
| **计算类型** | 确定性计算（图匹配算法） |
| **与现有指标差异** | 现有 `path_alignment` 将路径线性化为文本后用嵌入余弦相似度；GED 在图结构层面直接比较拓扑差异，对节点/边的增删替换有精确量化 |
| **理论依据** | 图编辑距离是图匹配理论中的经典度量，广泛应用于分子图比较、化学信息学和生物网络对齐。与基于嵌入的"软"比较相比，GED 提供"硬"结构距离，能精确区分"增加了一个节点"和"替换了一条边"。 |
| **参考文献 1** | Gao, X., Xiao, B., Tao, D., & Li, X. (2010). A Survey of Graph Edit Distance. *Pattern Analysis and Applications*, 13(1), 113-129. — 图编辑距离的综合综述。 |
| **参考文献 2** | Bunke, H. & Allermann, G. (1983). Inexact Graph Matching for Structural Pattern Recognition. *Pattern Recognition Letters*, 1(4), 245-253. — GED 的原始定义论文。 |
| **参考文献 3** | Abu-Aisheh, Z., Raveaux, R., Ramel, J.-Y., & Martineau, P. (2015). An Exact Graph Edit Distance Algorithm for Solving Pattern Recognition Problems. *ICPRAM 2015*. — GED 精确算法及近似加速方法。 |

---

### N13. 因果方向准确率 (Causal Direction Accuracy, CDA)

| 字段 | 内容 |
|------|------|
| **指标编号** | N13 |
| **英文名** | Causal Direction Accuracy |
| **中文名** | 因果方向准确率 |
| **定义** | 在生成路径与 GT 匹配成功的三元组中，head→tail 的因果方向与 GT 一致的比例。现有 consistency 指标为了提高召回率允许反向匹配（给 0.1-0.3 分），但这掩盖了一个重要信息：方向是否正确。 |
| **计算公式** | CDA(H) = \|{(h,r,t) in H : (h,t) in GT_index and dir_match}\| / \|{(h,r,t) in H : (h,t) in GT_index or (t,h) in GT_index}\| |
| **变量说明** | GT_index = GT 三元组索引；dir_match = 生成的 (h,t) 与 GT 中的 (h,t) 方向一致（而非 (t,h) 反向匹配）；分母 = 所有与 GT 有匹配关系（正向或反向）的步骤数 |
| **伪代码** | (1) forward_match = 0; any_match = 0; (2) for step in gen_path: h, t = step.head.lower(), step.tail.lower(); if (h,t) in gt_index: forward_match += 1; any_match += 1; elif (t,h) in gt_index: any_match += 1; (3) return forward_match / any_match if any_match > 0 else 0.0 |
| **取值范围** | [0, 1]，1.0 = 所有匹配到的三元组方向完全一致 |
| **计算类型** | 确定性计算 |
| **与现有指标差异** | 现有 `consistency_precision` 将反向匹配按 0.1-0.3 折算但不单独报告方向；本指标专门衡量"方向对不对" |
| **理论依据** | Simon (1983) 强调因果不对称性（causal asymmetry）是解释性定律区别于描述性定律的关键特征。在科学假设中，"A 导致 B"和"B 导致 A"往往是完全不同的命题，方向错误的假设即便实体匹配也可能完全无效。 |
| **参考文献 1** | Simon, H. A., Langley, P., & Bradshaw, G. (1983). Scientific Discovery as Problem Solving. *Synthese*, 47, 1-27. — 因果不对称性在科学解释中的核心地位。 |
| **参考文献 2** | Pearl, J. (2009). *Causality: Models, Reasoning, and Inference* (2nd ed.). Cambridge University Press. — 因果方向的形式化理论：do-calculus 和因果图。 |
| **参考文献 3** | Woodward, J. (2003). *Making Things Happen: A Theory of Causal Explanation*. Oxford University Press. — 干预主义因果理论：因果关系的方向性不可互换。 |

---

## 四、认知创造力层 — 发散思维（3 个指标）

### N14. 精进性 (Elaboration)

| 字段 | 内容 |
|------|------|
| **指标编号** | N14 |
| **英文名** | Elaboration |
| **中文名** | 精进性 |
| **定义** | Torrance 创造力测验 (TTCT) 的第四维度。衡量假设推理链中每步 claim 的详尽程度——是否提供了充分的细节、条件限定和机制描述，而非仅给出笼统的结论。 |
| **计算公式** | Elaboration(H) = mean_(s in steps) len_tokens(claim_s) / median_(all_paths) len_tokens(claim) |
| **变量说明** | len_tokens(claim_s) = 第 s 步 claim 的 token 数（中文用字符数或 jieba 分词数）；median 取自同批次所有路径所有 claim 的 token 数中位数 |
| **伪代码** | (1) all_claim_lengths = [len(tokenize(claim)) for all claims in all paths of same paper]; (2) median_len = median(all_claim_lengths); (3) path_claim_lengths = [len(tokenize(step.claim)) for step in path]; (4) return mean(l / median_len for l in path_claim_lengths) |
| **取值范围** | [0, +inf)，>1 表示比中位数更详尽，<1 表示更简略 |
| **计算类型** | 确定性计算 |
| **与现有指标差异** | 现有 Torrance 框架只实现了 fluency、flexibility、pairwise_diversity（≈originality 近似）、entity_coverage，缺少第四维度 elaboration |
| **理论依据** | Torrance (1966) TTCT 包含四个核心维度：fluency（数量）、flexibility（类别多样性）、originality（独特性）、elaboration（精进性）。Elaboration 衡量的是创意的"深度开发"程度——同样的跨学科连接，描述机制细节越丰富，越体现研究者对该连接的深入思考。 |
| **参考文献 1** | Torrance, E. P. (1966). *Torrance Tests of Creative Thinking: Norms-Technical Manual*. Princeton, NJ: Personnel Press. — TTCT 四维度的原始定义。 |
| **参考文献 2** | Kim, K. H. (2006). Can We Trust Creativity Tests? A Review of the Torrance Tests of Creative Thinking (TTCT). *Creativity Research Journal*, 18(1), 3-14. — TTCT 信度效度综述，elaboration 维度的独立贡献。 |
| **参考文献 3** | Ruan, Y., et al. (2025). LiveIdeaBench: Evaluating LLMs' Divergent Thinking for Scientific Idea Generation. — 将 Torrance 维度应用于 LLM 创意评估。 |

---

### N15. 独创性 (Originality Score)

| 字段 | 内容 |
|------|------|
| **指标编号** | N15 |
| **英文名** | Originality Score |
| **中文名** | 独创性 |
| **定义** | 当前假设路径与同一篇论文上所有其他生成假设路径之间的最小语义距离。Torrance 原始定义中，originality = 在所有受试者中出现频率最低的回答。此处类比为：在同一论文的所有生成路径（P1-P5，L1-L3）中，与其他路径最不相似的路径最具独创性。 |
| **计算公式** | Originality(H) = 1 - max_(H' in AllOtherPaths) sim(emb(H), emb(H')) |
| **变量说明** | AllOtherPaths = 同一篇论文同一层级下所有其他假设路径；sim = SBERT 嵌入余弦相似度；emb(H) = 路径文本化后的嵌入 |
| **伪代码** | (1) path_text = " → ".join(f"{s.head} [{s.relation}] {s.tail}" for s in path); (2) all_texts = [同一论文同层级其他路径的文本化]; (3) embs = sbert.encode([path_text] + all_texts); (4) sims = [cosine_sim(embs[0], embs[i]) for i in range(1, len(embs))]; (5) return 1.0 - max(sims) if sims else 1.0 |
| **取值范围** | [0, 1]，越高越独创（与其他所有假设越不相似） |
| **计算类型** | 嵌入相似度（复用已有 SBERT） |
| **与现有指标差异** | 现有 `pairwise_diversity` 计算的是同层级所有路径两两之间的 **平均** 距离，反映群体多样性；Originality 标记的是 **单条路径** 在群体中的独特程度 |
| **理论依据** | Torrance (1966) 将 originality 定义为"统计上最不常见的回答"——需要参照群体分布。Ruan et al. (2025, LiveIdeaBench) 将此概念应用于 LLM 创意评估，以生成想法在同批次中的罕见度衡量独创性。 |
| **参考文献 1** | Torrance, E. P. (1966). *Torrance Tests of Creative Thinking*. Princeton, NJ: Personnel Press. — Originality = 统计罕见度。 |
| **参考文献 2** | Ruan, Y., et al. (2025). LiveIdeaBench: Evaluating LLMs' Divergent Thinking for Scientific Idea Generation. — 将 TTCT originality 量化方法应用于 LLM 创意评估。 |
| **参考文献 3** | Si, C., Yang, D., & Hashimoto, T. (2024). Can LLMs Generate Novel Research Ideas? *ICLR 2025*. arXiv:2409.04109. — 通过 Semantic Scholar 检索判断想法是否已有类似工作。 |

---

### N16. 远程联想指数 (Remote Association Index, RAI)

| 字段 | 内容 |
|------|------|
| **指标编号** | N16 |
| **英文名** | Remote Association Index |
| **中文名** | 远程联想指数 |
| **定义** | 路径中每一步 head 与 tail 之间的平均语义距离。创造力心理学认为，将语义上距离遥远的概念关联起来是创造性思维的核心能力。与 embedding_bridging（仅看首尾两端）不同，RAI 衡量路径每一步的"联想跳跃距离"。 |
| **计算公式** | RAI(H) = mean_(s in steps) (1 - cos(emb(head_s), emb(tail_s))) |
| **变量说明** | emb(x) = SBERT 嵌入向量；cos = 余弦相似度 |
| **伪代码** | (1) distances = []; (2) for step in path: emb_h = sbert.encode(step.head); emb_t = sbert.encode(step.tail); dist = 1.0 - cosine_similarity(emb_h, emb_t); distances.append(dist); (3) return mean(distances) |
| **取值范围** | [0, 1]，越高表示每步平均跳跃距离越大 |
| **计算类型** | 嵌入相似度（复用已有 SBERT） |
| **与现有指标差异** | 现有 `embedding_bridging` 仅计算路径 **首尾两端** 的语义距离；RAI 计算 **每一步** 的跳跃距离均值。前者衡量路径的"总跨度"，后者衡量路径的"逐步跳跃强度"。一条路径可以有高 bridging 但低 RAI（首尾距离大但中间步骤渐进），也可以有高 RAI 但低 bridging（每步跳跃大但最终回到起点附近）。 |
| **理论依据** | Mednick (1962) 提出远程联想测验 (RAT)：创造力 = 将语义距离遥远的元素关联起来的能力。在跨学科假设中，每步的 head→tail 是否跨越了较大的语义距离，直接反映了假设的"联想跨度"。 |
| **参考文献 1** | Mednick, S. A. (1962). The Associative Basis of the Creative Process. *Psychological Review*, 69(3), 220-232. — 远程联想理论的原始论文。 |
| **参考文献 2** | Kenett, Y. N. & Faust, M. (2019). A Semantic Network Cartography of the Creative Mind. *Trends in Cognitive Sciences*, 23(4), 271-274. — 语义网络距离与创造力的关系。 |
| **参考文献 3** | Beketayev, K. & Runger, G. (2014). Measuring Semantic Similarity of Words Using Concept Networks. *ICDM 2014 Workshop*. — 概念网络中的语义距离度量方法。 |

---

## 五、可靠性与鲁棒性层（3 个指标）

### N17. 幻觉率 (Hallucination Rate, HR)

| 字段 | 内容 |
|------|------|
| **指标编号** | N17 |
| **英文名** | Hallucination Rate |
| **中文名** | 幻觉率 |
| **定义** | 路径中既不在 GT 知识图谱概念表中也不在原论文摘要中出现的实体比例。这些实体是模型"凭空捏造"的概念，无法溯源到任何输入信息。 |
| **计算公式** | HR(H) = \|{e in entities(H) : e not_in KG_GT and e not_in abstract}\| / \|entities(H)\| |
| **变量说明** | entities(H) = 路径中所有唯一实体；KG_GT = GT 概念词表中所有 normalized term（模糊匹配阈值 0.75）；abstract = 原论文摘要文本（子串匹配） |
| **伪代码** | (1) entities = unique(heads + tails in path); (2) gt_terms = [t.normalized for t in GT.terms]; (3) abstract_text = paper.abstract.lower(); (4) hallucinated = 0; (5) for e in entities: in_gt = any(sim(e, t) >= 0.75 for t in gt_terms); in_abstract = e.lower() in abstract_text; if not in_gt and not in_abstract: hallucinated += 1; (6) return hallucinated / len(entities) |
| **取值范围** | [0, 1]，越低越好（0 = 无幻觉） |
| **计算类型** | 字符串匹配 + 嵌入软匹配 |
| **与现有指标差异** | 现有 `concept_precision` 只检查实体是否匹配 GT 概念；本指标增加 abstract 作为第二验证源——即便实体不在 GT 概念表中，只要在原论文摘要中有根据，也不算幻觉 |
| **理论依据** | Zhang et al. (2025, npj AI) 将 hallucination detection 列为 LLM 可靠性评估的核心维度。Min et al. (2023) 的 FActScore 方法将文本拆分为原子事实逐一验证。在假设生成场景中，使用了原始文本中不存在且 GT KG 也未收录的概念，即为"概念幻觉"。 |
| **参考文献 1** | Min, S., Krishna, K., Lyu, X., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. *EMNLP 2023*. arXiv:2305.14251. — 原子级事实精度评估框架。 |
| **参考文献 2** | Zhang, J., et al. (2025). Exploring the Role of Large Language Models in the Scientific Method: From Hypothesis to Discovery. *npj AI*. — LLM 在科学发现中的幻觉检测和可靠性评估。 |
| **参考文献 3** | Li, J., Cheng, X., Zhao, W. X., Nie, J.-Y., & Wen, J.-R. (2023). HaluEval: A Large-Scale Hallucination Evaluation Benchmark for Large Language Models. *EMNLP 2023*. arXiv:2305.11747. — LLM 幻觉评估基准。 |

---

### N18. 自一致性 (Self-Consistency, SC)

| 字段 | 内容 |
|------|------|
| **指标编号** | N18 |
| **英文名** | Self-Consistency |
| **中文名** | 自一致性 |
| **定义** | 对同一论文、同一 Prompt 级别多次独立生成假设后，生成结果之间的语义一致性。高自一致性意味着模型对该输入有稳定的"理解"，低自一致性暗示输出高度依赖随机采样。 |
| **计算公式** | SC(H, K) = mean_(i<j) sim(emb(H_i), emb(H_j)) |
| **变量说明** | H_1, H_2, ..., H_K = 同一输入、同一 Prompt 级别的 K 次独立生成结果（K >= 3）；sim = SBERT 嵌入余弦相似度 |
| **伪代码** | (1) 对同一篇论文同一 Prompt 级别，设 temperature=0.7，独立生成 K=3 次; (2) texts = [路径文本化 for each generation]; (3) embs = sbert.encode(texts); (4) sims = [cosine_sim(embs[i], embs[j]) for i<j]; (5) return mean(sims) |
| **取值范围** | [0, 1]，越高表示生成越稳定 |
| **计算类型** | 多次采样 + 嵌入相似度 |
| **与现有指标差异** | 现有体系所有指标均基于单次生成评估；SC 是唯一评估生成 **稳定性** 的指标 |
| **理论依据** | Wang et al. (2023) 提出 Self-Consistency 作为 LLM 输出可靠性的代理指标：如果模型在多次采样中给出一致答案，该答案更可能正确。在假设生成中，高一致性意味着假设不是采样噪声的产物而是输入信息的合理推导。 |
| **参考文献 1** | Wang, X., Wei, J., Schuurmans, D., et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. *ICLR 2023*. arXiv:2203.11171. — 自一致性方法的原始论文。 |
| **参考文献 2** | Zhang, J., et al. (2025). Exploring the Role of Large Language Models in the Scientific Method: From Hypothesis to Discovery. *npj AI*. — Self-consistency 作为 LLM 科学推理可靠性度量。 |
| **参考文献 3** | Gridach, M., et al. (2025). Agentic AI for Scientific Discovery: A Survey of Progress, Challenges, and Future Directions. *ICLR 2025*. — Reliability（任务失败率、恢复率）和 Trustworthiness 评估维度。 |

---

### N19. 事实精度 (Factual Precision, FP)

| 字段 | 内容 |
|------|------|
| **指标编号** | N19 |
| **英文名** | Factual Precision |
| **中文名** | 事实精度 |
| **定义** | 路径中各步 claim 与原论文摘要之间不存在事实性矛盾的比例。使用 NLI 模型逐步验证每条声明是否与已知事实（摘要）一致或至少不矛盾。 |
| **计算公式** | FP(H) = \|{s in steps : NLI(claim_s, abstract) != contradiction}\| / num_steps |
| **变量说明** | NLI(a, b) = NLI 模型对 (premise=abstract, hypothesis=claim_s) 的判定；contradiction 表示 claim 与摘要事实矛盾 |
| **伪代码** | (1) non_contradicted = 0; (2) for step in path: result = nli_model(premise=abstract, hypothesis=step.claim); if result != 'contradiction': non_contradicted += 1; (3) return non_contradicted / len(path) |
| **取值范围** | [0, 1]，1.0 = 所有 claim 均不与摘要矛盾 |
| **计算类型** | NLI 模型（可复用 DeBERTa-xlarge-mnli） |
| **与现有指标差异** | 现有 `scientificity` 是 LLM 对整体科学性的主观打分；本指标逐步骤做形式化 NLI 验证，结果可解释、可复现 |
| **理论依据** | Min et al. (2023) 的 FActScore 方法证明了原子级事实验证比整体评分更能捕捉细粒度的事实性错误。在假设生成场景中，即便假设整体"听起来科学"，个别步骤也可能与已知事实矛盾。 |
| **参考文献 1** | Min, S., Krishna, K., Lyu, X., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. *EMNLP 2023*. arXiv:2305.14251. — 原子级事实验证方法论。 |
| **参考文献 2** | He, P., Liu, X., Gao, J., & Chen, W. (2021). DeBERTa: Decoding-enhanced BERT with Disentangled Attention. *ICLR 2021*. arXiv:2006.03654. — DeBERTa-xlarge-mnli 模型用于 NLI 任务。 |
| **参考文献 3** | Gridach, M., et al. (2025). Agentic AI for Scientific Discovery: A Survey. *ICLR 2025*. — Accuracy 和 Soundness 作为 Agent 评估的核心维度。 |

---

## 六、科学影响力预测层（4 个指标）

### N20. σ² 变革性 (Sigma-squared Transformativeness)

| 字段 | 内容 |
|------|------|
| **指标编号** | N20 |
| **英文名** | σ² Transformativeness |
| **中文名** | σ² 变革性指数 |
| **定义** | 结合"突发性关注度"（burstness）和"结构洞桥接度"（betweenness centrality）的乘积。Chen et al. (2009) 验证此复合指标能在引用网络中识别诺奖级变革性发现。在本 benchmark 中，将其改编为路径实体在 GT KG 中的结构位置和知识更新速率的组合。 |
| **计算公式** | sigma2(H) = burst(H) × SHB(H) |
| **变量说明** | burst(H) = 路径实体在 GT KG 中的平均"新颖度"（该实体首次出现的文献与数据集中位时间的差值，归一化到 [0,1]，越新越高）；SHB(H) = 结构洞桥接度（指标 N10） |
| **伪代码** | (1) 对 GT KG 中每个实体计算 first_appearance_year（近似：在多少篇 GT 论文中出现，出现越少越"新"）; (2) burst_e = 1.0 - freq(e) / max_freq（归一化稀有度）; (3) burst_H = mean(burst_e for e in path_entities); (4) sigma2 = burst_H × SHB(H) |
| **取值范围** | [0, 1]，越高表示路径同时具有新颖性和结构位置优势 |
| **计算类型** | 图算法 × 统计 |
| **与现有指标差异** | 现有指标分别度量新颖性（info_novelty, atypical_combination）和结构位置（avg_betweenness），但未交叉组合；σ² 的价值在于捕捉"新颖 × 桥接"的交互效应——仅新颖但无结构位置 or 仅有位置但不新颖，都不会获得高分 |
| **理论依据** | Chen et al. (2009) 在 8 个科学领域验证了 σ² = burstness × centrality 可以识别变革性发现。例如 Marshall-1988（幽门螺杆菌致溃疡）在 σ² 指标上排名第一，尽管其原始引用量并非最高。这一指标的核心洞见是：变革性发现 = 知识更新（burst）+ 知识桥接（centrality）。 |
| **参考文献 1** | Chen, C., Chen, Y., Horowitz, M., Hou, H., Liu, Z., & Pellegrino, D. (2009). Towards an Explanatory and Computational Theory of Scientific Discovery. *Journal of Informetrics*, 3(3), 191-209. — σ² 指标的原始论文，验证于 8 个科学领域。 |
| **参考文献 2** | Kleinberg, J. (2003). Bursty and Hierarchical Structure in Streams. *Data Mining and Knowledge Discovery*, 7(4), 373-397. — Burstness 检测的算法基础。 |
| **参考文献 3** | Freeman, L. C. (1977). A Set of Measures of Centrality Based on Betweenness. *Sociometry*, 40(1), 35-41. — Betweenness centrality 的原始定义。 |

---

### N21. 范式兼容性 (Paradigm Compatibility, PC)

| 字段 | 内容 |
|------|------|
| **指标编号** | N21 |
| **英文名** | Paradigm Compatibility |
| **中文名** | 范式兼容性 |
| **定义** | 假设各步声明与 GT 已有路径声明的逐步最大语义对齐度均值。衡量假设在多大程度上与已建立的知识范式兼容（而非完全脱离或完全复制）。 |
| **计算公式** | PC(H) = mean_(s in steps) max_(gt_claim in all_GT_claims) sim(emb(claim_s), emb(gt_claim)) |
| **变量说明** | claim_s = 路径第 s 步的 claim 文本；all_GT_claims = GT 数据集中所有路径所有步骤的 claim 集合；sim = SBERT 余弦相似度 |
| **伪代码** | (1) gt_claims = [step.claim for item in GT_dataset for path in item.paths for step in path]; (2) gt_embs = sbert.encode(gt_claims); (3) step_scores = []; (4) for step in path: step_emb = sbert.encode(step.claim); sims = cosine_sim(step_emb, gt_embs); step_scores.append(max(sims)); (5) return mean(step_scores) |
| **取值范围** | [0, 1]，适中值最优（过高=照搬，过低=脱离范式） |
| **计算类型** | 嵌入相似度 |
| **与现有指标差异** | 现有 `path_alignment` 将整条路径线性化为一个向量做对齐；PC 在 **逐步 claim 粒度** 做匹配，能区分"哪些步骤兼容、哪些步骤偏离" |
| **理论依据** | Kuhn (1962) 将"外部一致性——与当前接受的其他理论的兼容性"列为理论评价标准之一。完全不兼容的假设难以被科学共同体接受；但 Kuhn 同时指出范式转变恰恰始于对已有范式的适度偏离。因此 PC 应与 novelty/innovation 联合解读。 |
| **参考文献 1** | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions*. Chicago: University of Chicago Press. — 外部一致性标准 + 范式转变理论。 |
| **参考文献 2** | Laudan, L., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. — Thesis 22: 与其他领域理论的兼容性是评价标准之一。 |
| **参考文献 3** | Fortunato, S., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. — 高影响力论文在常规与新颖之间取得平衡。 |

---

### N22. 新颖-常规平衡 (Novelty-Convention Balance, NCB)

| 字段 | 内容 |
|------|------|
| **指标编号** | N22 |
| **英文名** | Novelty-Convention Balance |
| **中文名** | 新颖-常规平衡 |
| **定义** | 衡量假设路径中"新颖三元组"（不在 GT KG 中的连接）与"常规三元组"（在 GT KG 中有先例的连接）之间的平衡程度。Uzzi et al. (2013) 发现最高影响力的论文在常规基础上嵌入非典型组合——纯新颖或纯常规都不是最优的。 |
| **计算公式** | NCB(H) = min(r_novel, r_conv) / max(r_novel, r_conv) |
| **变量说明** | r_novel = 路径中不在 GT KG 索引中的三元组比例；r_conv = 路径中在 GT KG 索引中有匹配的三元组比例；r_novel + r_conv = 1.0 |
| **伪代码** | (1) novel = 0; conv = 0; (2) for step in path: h, t = step.head.lower(), step.tail.lower(); if (h,t) in gt_index or (t,h) in gt_index: conv += 1; else: novel += 1; (3) r_novel = novel / len(path); r_conv = conv / len(path); (4) return min(r_novel, r_conv) / max(r_novel, r_conv) if max > 0 else 0.0 |
| **取值范围** | [0, 1]，1.0 = 新颖与常规完全均衡（如 50:50），0.0 = 完全由一方主导 |
| **计算类型** | 确定性计算 |
| **与现有指标差异** | 现有 `atypical_combination` 仅衡量非典型性的高低，不衡量典型与非典型之间的 **平衡**。一条全由新颖三元组组成的路径在 atypical_combination 上得高分，但在 NCB 上得低分——因为它缺乏常规基础 |
| **理论依据** | Uzzi et al. (2013, Science) 分析了 1790 万篇论文，发现引用最高的论文的参考文献组合呈现"高常规性中嵌入少量非典型组合"的特征。纯常规 = 影响力平庸；纯非典型 = 难以被社区理解和引用；最优 = 两者平衡。 |
| **参考文献 1** | Uzzi, B., Mukherjee, S., Stringer, M., & Jones, B. F. (2013). Atypical Combinations and Scientific Impact. *Science*, 342(6157), 468-472. — "高影响力研究 = 常规基础 + 非典型嵌入"的核心发现。 |
| **参考文献 2** | Fortunato, S., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. — 引用 Uzzi 的发现，讨论"balanced novelty-convention ratio"。 |
| **参考文献 3** | Wang, D., Song, C., & Barabási, A.-L. (2013). Quantifying Long-term Scientific Impact. *Science*, 342(6154), 127-132. — Q-model: 论文的内在"适应度"参数与其知识组合特征相关。 |

---

### N23. 问题解决覆盖率 (Problem-Solving Coverage, PSC)

| 字段 | 内容 |
|------|------|
| **指标编号** | N23 |
| **英文名** | Problem-Solving Coverage |
| **中文名** | 问题解决覆盖率 |
| **定义** | 假设是否回答了论文抽取阶段产生的各层级查询（L1/L2/L3 query）。一个高质量假设不仅应在形式上合理，还应实质性地回应其所针对的科学问题。 |
| **计算公式** | PSC(H) = \|{q in queries : LLM_judge(H answers q) = True}\| / \|queries\| |
| **变量说明** | queries = 论文抽取阶段产生的 L1 一级查询 + L2 二级查询列表 + L3 三级查询列表；LLM_judge = LLM 判断假设路径是否实质性回答了该查询 |
| **伪代码** | (1) queries = [l1_query] + l2_queries + l3_queries; (2) path_text = 路径所有 claim 拼接; (3) answered = 0; (4) for q in queries: prompt = f"判断以下假设是否实质性回答了该科学问题:\n问题: {q}\n假设: {path_text}\n输出 True/False"; result = llm(prompt, temperature=0.0); if result == True: answered += 1; (5) return answered / len(queries) |
| **取值范围** | [0, 1]，越高表示假设覆盖了越多的科学问题 |
| **计算类型** | LLM 判断 |
| **与现有指标差异** | 现有 `relevance` 评分衡量假设与"原始研究方向"的关联度；PSC 更精确地检查假设是否 **回答** 了具体的层级查询问题 |
| **理论依据** | Laudan (1986) 将"问题解决的速率"作为理论评价的核心标准——理论（假设）的价值在于它能解决多少科学问题。Kuhn (1962) 的 puzzle-solving capacity 概念同义。一个"科学上正确、新颖、可验证"但实际上不回答任何具体科学问题的假设，实用价值有限。 |
| **参考文献 1** | Laudan, L. (1977). *Progress and Its Problems: Toward a Theory of Scientific Growth*. Berkeley: University of California Press. — 问题解决有效性作为理论评价的首要标准。 |
| **参考文献 2** | Laudan, L., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. — Thesis 21.8: 高问题解决率 justifies 理论接受。 |
| **参考文献 3** | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions*. — Puzzle-solving 作为范式的核心功能。 |

---

## 总览表

| 维度 | 编号 | 英文名 | 中文名 | 公式 | 取值范围 | 计算类型 | 核心参考文献 |
|------|------|--------|--------|------|---------|---------|------------|
| 科学哲学 | N1 | Falsifiability Scope | 可证伪域宽度 | \|O_refute\| / \|O_all\| | [0,1] | LLM+枚举 | Popper (1959) |
| 科学哲学 | N2 | Empirical Content | 经验内容 | n_pred / (n_pred + n_retro) | [0,1] | LLM分类 | Popper (1959); Lakatos (1978) |
| 科学哲学 | N3 | Parsimony | 简约性 | 1 - (U_ent+U_rel)/(steps×3) | [0,1] | 确定性 | Kuhn (1962); Simon (1983) |
| 科学哲学 | N4 | Internal Consistency | 内部一致性 | 1 - contradictions/C(n,2) | [0,1] | NLI模型 | Kuhn (1962); Laudan (1986) |
| 科学哲学 | N5 | Explanatory Depth | 解释深度 | mean(mechanism_score) | [0,1] | LLM三级分类 | Simon (1983); Machamer (2000) |
| 跨学科发现 | N6 | Disciplinary Leap Index | 学科跨越系数 | max(d_tax per step) | [0,1] | 确定性 | Fortunato (2018); Coccia (2022) |
| 跨学科发现 | N7 | Discipline Balance | 学科分布平衡度 | 1 - Gini(p_1..p_k) | [0,1] | 确定性 | Stirling (2007); Gini (1912) |
| 跨学科发现 | N8 | Boundary Spanner Score | 边界跨越者比例 | multi-disc entities / all | [0,1] | 确定性 | Bettencourt (2009); Burt (2004) |
| 跨学科发现 | N9 | Discovery Probability | 发现概率估计 | prod(Prd per step) | [0,1] | 概率模型 | Coccia (2022); Uzzi (2013) |
| KG推理 | N10 | Structural Hole Bridging | 结构洞桥接度 | mean(BC(e, G_GT)) | [0,1] | 图算法 | Chen (2009); Freeman (1977) |
| KG推理 | N11 | Link Prediction Surprisal | 链接预测惊异度 | -mean(log P_KGE) | [0,+inf) | KGE模型 | Ding (2025); Bordes (2013) |
| KG推理 | N12 | Graph Edit Distance | 归一化图编辑距离 | min GED / normalization | [0,1] | 确定性 | Gao (2010); Bunke (1983) |
| KG推理 | N13 | Causal Direction Accuracy | 因果方向准确率 | forward_match / any_match | [0,1] | 确定性 | Simon (1983); Pearl (2009) |
| 认知创造力 | N14 | Elaboration | 精进性 | mean(claim_len / median_len) | [0,+inf) | 确定性 | Torrance (1966); Kim (2006) |
| 认知创造力 | N15 | Originality Score | 独创性 | 1 - max(sim to others) | [0,1] | 嵌入相似度 | Torrance (1966); Si (2024) |
| 认知创造力 | N16 | Remote Association Index | 远程联想指数 | mean(1-cos per step) | [0,1] | 嵌入相似度 | Mednick (1962) |
| 可靠性 | N17 | Hallucination Rate | 幻觉率 | ungrounded / total entities | [0,1] | 字符串+嵌入 | Min (2023); Li (2023) |
| 可靠性 | N18 | Self-Consistency | 自一致性 | mean pairwise sim (K runs) | [0,1] | 多次采样 | Wang (2023) |
| 可靠性 | N19 | Factual Precision | 事实精度 | non-contradicted / steps | [0,1] | NLI模型 | Min (2023); He (2021) |
| 影响力预测 | N20 | σ² Transformativeness | σ²变革性指数 | burst × SHB | [0,1] | 图算法×统计 | Chen (2009); Kleinberg (2003) |
| 影响力预测 | N21 | Paradigm Compatibility | 范式兼容性 | mean(max sim to GT claims) | [0,1] | 嵌入相似度 | Kuhn (1962); Laudan (1986) |
| 影响力预测 | N22 | Novelty-Convention Balance | 新颖-常规平衡 | min(r_novel,r_conv)/max(...) | [0,1] | 确定性 | Uzzi (2013); Fortunato (2018) |
| 影响力预测 | N23 | Problem-Solving Coverage | 问题解决覆盖率 | answered_queries / total | [0,1] | LLM判断 | Laudan (1977); Kuhn (1962) |

---

## 完整参考文献

| # | 完整引用 |
|---|---------|
| 1 | Popper, K. R. (1959). *The Logic of Scientific Discovery*. London: Hutchinson. |
| 2 | Popper, K. R. (1963). *Conjectures and Refutations: The Growth of Scientific Knowledge*. London: Routledge. |
| 3 | Kuhn, T. S. (1962/1970). *The Structure of Scientific Revolutions* (2nd ed.). Chicago: University of Chicago Press. |
| 4 | Lakatos, I. (1978). *The Methodology of Scientific Research Programmes*. Cambridge University Press. |
| 5 | Laudan, L. (1977). *Progress and Its Problems: Toward a Theory of Scientific Growth*. Berkeley: University of California Press. |
| 6 | Laudan, L., Donovan, A., Laudan, R., et al. (1986). Scientific Change: Philosophical Models and Historical Research. *Synthese*, 69(2), 141-223. |
| 7 | Torrance, E. P. (1966). *Torrance Tests of Creative Thinking: Norms-Technical Manual*. Princeton, NJ: Personnel Press. |
| 8 | Mednick, S. A. (1962). The Associative Basis of the Creative Process. *Psychological Review*, 69(3), 220-232. |
| 9 | Simon, H. A., Langley, P., & Bradshaw, G. (1983). Scientific Discovery as Problem Solving. *Synthese*, 47, 1-27. |
| 10 | Machamer, P., Darden, L., & Craver, C. F. (2000). Thinking About Mechanisms. *Philosophy of Science*, 67(1), 1-25. |
| 11 | Woodward, J. (2003). *Making Things Happen: A Theory of Causal Explanation*. Oxford University Press. |
| 12 | Pearl, J. (2009). *Causality: Models, Reasoning, and Inference* (2nd ed.). Cambridge University Press. |
| 13 | Sober, E. (2015). *Ockham's Razors: A User's Manual*. Cambridge University Press. |
| 14 | Stirling, A. (2007). A General Framework for Analysing Diversity in Science, Technology and Society. *J. R. Soc. Interface*, 4(15), 707-719. |
| 15 | Gini, C. (1912). Variabilità e Mutabilità. *Studi Economico-Giuridici della Regia Università di Cagliari*, 3, 3-159. |
| 16 | Uzzi, B., Mukherjee, S., Stringer, M., & Jones, B. F. (2013). Atypical Combinations and Scientific Impact. *Science*, 342(6157), 468-472. |
| 17 | Fortunato, S., Bergstrom, C. T., Börner, K., et al. (2018). Science of Science. *Science*, 359(6379), eaao0185. |
| 18 | Coccia, M. (2022). Probability of Discoveries Between Research Fields to Explain Scientific and Technological Change. *Technology in Society*, 68, 101874. |
| 19 | Bettencourt, L. M. A., Kaiser, D. I., & Kaur, J. (2009). Scientific Discovery and Topological Transitions in Collaboration Networks. *J. Informetrics*, 3(3), 210-221. |
| 20 | Chen, C., Chen, Y., Horowitz, M., et al. (2009). Towards an Explanatory and Computational Theory of Scientific Discovery. *J. Informetrics*, 3(3), 191-209. |
| 21 | Burt, R. S. (2004). Structural Holes and Good Ideas. *American Journal of Sociology*, 110(2), 349-399. |
| 22 | Freeman, L. C. (1977). A Set of Measures of Centrality Based on Betweenness. *Sociometry*, 40(1), 35-41. |
| 23 | Kleinberg, J. (2003). Bursty and Hierarchical Structure in Streams. *Data Mining and Knowledge Discovery*, 7(4), 373-397. |
| 24 | Bordes, A., Usunier, N., Garcia-Duran, A., et al. (2013). Translating Embeddings for Modeling Multi-relational Data. *NeurIPS 2013*. |
| 25 | Sun, Z., Deng, Z.-H., Nie, J.-Y., & Tang, J. (2019). RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space. *ICLR 2019*. |
| 26 | Gao, X., Xiao, B., Tao, D., & Li, X. (2010). A Survey of Graph Edit Distance. *Pattern Analysis and Applications*, 13(1), 113-129. |
| 27 | Bunke, H. & Allermann, G. (1983). Inexact Graph Matching for Structural Pattern Recognition. *Pattern Recognition Letters*, 1(4), 245-253. |
| 28 | Wang, X., Wei, J., Schuurmans, D., et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. *ICLR 2023*. |
| 29 | Min, S., Krishna, K., Lyu, X., et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision. *EMNLP 2023*. |
| 30 | He, P., Liu, X., Gao, J., & Chen, W. (2021). DeBERTa: Decoding-enhanced BERT with Disentangled Attention. *ICLR 2021*. |
| 31 | Li, J., Cheng, X., Zhao, W. X., et al. (2023). HaluEval: A Large-Scale Hallucination Evaluation Benchmark. *EMNLP 2023*. |
| 32 | Williams, A., Nangia, N., & Bowman, S. R. (2018). A Broad-Coverage Challenge Corpus for Sentence Understanding through Inference. *NAACL-HLT 2018*. |
| 33 | Si, C., Yang, D., & Hashimoto, T. (2024). Can LLMs Generate Novel Research Ideas? *ICLR 2025*. arXiv:2409.04109. |
| 34 | Ding, K., Feng, Y., Wang, X., et al. (2025). Bridging Data and Discovery: A Survey on Knowledge Graphs in AI for Science. |
| 35 | Zhang, J., et al. (2025). Exploring the Role of Large Language Models in the Scientific Method. *npj AI*. |
| 36 | Gridach, M., et al. (2025). Agentic AI for Scientific Discovery: A Survey. *ICLR 2025*. |
| 37 | Ruan, Y., et al. (2025). LiveIdeaBench: Evaluating LLMs' Divergent Thinking for Scientific Idea Generation. |
| 38 | Kim, K. H. (2006). Can We Trust Creativity Tests? A Review of the TTCT. *Creativity Research Journal*, 18(1), 3-14. |
| 39 | Kenett, Y. N. & Faust, M. (2019). A Semantic Network Cartography of the Creative Mind. *Trends in Cognitive Sciences*, 23(4), 271-274. |
| 40 | Wang, D., Song, C., & Barabási, A.-L. (2013). Quantifying Long-term Scientific Impact. *Science*, 342(6154), 127-132. |
| 41 | Leydesdorff, L., Wagner, C. S., & Bornmann, L. (2018). Betweenness and Diversity in Journal Citation Networks. *Scientometrics*, 114(2), 567-592. |
| 42 | Dunbar, K. (1993). Concept Discovery in a Scientific Domain. *Cognitive Science*, 17(3), 397-434. |

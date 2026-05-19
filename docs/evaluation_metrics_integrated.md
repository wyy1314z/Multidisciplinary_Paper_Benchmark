# CrossDisc Benchmark X+5 Evaluation Metrics

本项目的主评估体系收敛为 **X+5**：

- **X = Interdisciplinary Integration**：CrossDisc 的特色指标，衡量跨学科整合能力。
- **5 个通用核心指标**：Structural Validity、Evidence Groundedness、Novelty、Testability、Feasibility。

细粒度指标仍保留在代码中，用于诊断、消融和误差分析；论文和主图表默认报告 X+5 聚合指标。

---

## 总览

| 角色 | 主指标 | 核心问题 | 主分 | 辅助指标 |
|---|---|---|---|---|
| X | Interdisciplinary Integration | 假设是否真实桥接多个学科，并且学科之间具有实质性认知距离？ | `rao_stirling` | `disciplinary_leap_index`, `embedding_bridging` |
| +1 | Structural Validity | 假设是否形成结构完整、方向合理、语义连贯的推理链？ | `consistency_f1` | `consistency_precision`, `consistency_recall`, `chain_coherence`, `causal_direction_accuracy` |
| +2 | Evidence Groundedness | 假设的 claim、概念、关系是否有摘要、GT、web search 或证据路径支撑？ | `factual_precision` | `concept_f1`, `relation_precision`, `evidence_coverage`, `hallucination_rate`, `path_alignment_best` |
| +3 | Novelty | 假设是否提出少见且有信息增量的知识重组？ | `info_novelty` | `atypical_combination`, `remote_association_index`, `novelty_convention_balance` |
| +4 | Testability | 假设是否可观测、可测量、可证伪？ | `testability` | `specificity`, `measurability`, `falsifiability`, `resource_feasibility` 当前作为 `validation_design_clarity` 代理 |
| +5 | Feasibility | 假设在当前数据、方法、资源和时间约束下是否现实可执行？ | `feasibility` | `feasibility_data`, `feasibility_method`, `feasibility_resource`, `feasibility_validation` |

聚合实现位于：

- `crossdisc_extractor/benchmark/x5_metrics.py`
- `generate_x5_radar.py`
- `run_multimodel_eval_16metrics.py`
- `crossdisc_extractor/benchmark/evaluate_benchmark.py`
- `crossdisc_extractor/benchmark/evaluate_benchmark_validity.py`

实现上，各子指标先统一归一化到 `[0, 1]` 参与加权；当前报告层通过
`crossdisc_extractor/benchmark/x5_metrics.py` 映射到 `[1, 5]` 五分制。

评估证据源可独立配置：

- `--use-benchmark-gt` / `--no-benchmark-gt`：是否使用 Benchmark GT 参考路径、GT terms、GT relations、GT evidence paths，以及 Benchmark KG 背景统计。
- `--web-search` / `--no-web-search`：是否调用 web search 检索相似论文并抽取 reference paths。
- `--web-provider openalex|semantic_scholar|auto`：选择 web search 来源；默认使用 `openalex`，`auto` 会先查 OpenAlex，若无结果再回退到 Semantic Scholar。
- 当 `--web-search` 开启时，web reference paths 会同时进入 reference paths、terms、relations、evidence paths，使 Structural Validity、Evidence Groundedness、Novelty 等依赖参考证据的子维度都可以使用 web evidence。
- Web reference paths 也会补充当前 item 的运行时 KG 上下文：其实体-学科映射可用于 Interdisciplinary Integration，web 三元组/共现可用于 Novelty 的背景统计。
- 两个开关相互独立：可以只用 Benchmark GT、只用 web search、两者都用，或两者都关闭。

---

## 1. Structural Validity

| 项目 | 内容 |
|---|---|
| 主指标 | Structural Validity |
| 定义 | 衡量生成假设是否形成一条结构完整、方向合理、语义连贯的科学推理链。 |
| 子维度 1 | `path_alignment`：与 GT 路径在实体-关系结构上的对齐程度。 |
| 子维度 2 | `chain_coherence`：相邻步骤之间是否语义连贯。 |
| 子维度 3 | `causal_direction`：关系或因果方向是否正确。 |
| 子维度 4 | `step_completeness`：关键推理步骤是否完整覆盖。 |
| 评估方法 | 以 `consistency_f1` 为主分，结合 `chain_coherence`、`causal_direction_accuracy`、`consistency_recall` 进行辅助评估。 |
| 项目实现 | `consistency_f1`, `consistency_precision`, `consistency_recall`, `chain_coherence`, `causal_direction_accuracy` |

默认聚合：

```text
Structural Validity =
  0.55 * consistency_f1
+ 0.20 * chain_coherence
+ 0.15 * causal_direction_accuracy
+ 0.10 * consistency_recall
```

解释：`consistency_f1` 是主分，因为它同时覆盖生成路径与 GT 的精确率和召回；`chain_coherence` 检查语义连贯性；`causal_direction_accuracy` 检查方向；`consistency_recall` 作为 `step_completeness` 的可计算代理。

---

## 2. Evidence Groundedness

| 项目 | 内容 |
|---|---|
| 主指标 | Evidence Groundedness |
| 定义 | 衡量假设中的 claim、概念和关系是否被摘要、GT terms + web search terms、GT 关系或证据路径支撑。 |
| 子维度 1 | `claim_support`：step claim 是否与证据一致。 |
| 子维度 2 | `concept_grounding`：核心实体是否能在 GT terms + web search terms 中找到支撑。 |
| 子维度 3 | `relation_grounding`：关系是否能在 GT relations 或 web search reference paths 中找到支撑。 |
| 子维度 4 | `evidence_path_support`：整条路径是否被 GT evidence paths 或 web search reference paths 覆盖。 |
| 评估方法 | 以 `factual_precision` 为主分；有摘要时做 NLI 检查，无摘要时退回到 GT relations / GT terms + web search terms 支撑；辅以 `concept_f1`、`relation_precision`、`evidence_coverage`、`hallucination_rate`。 |
| 项目实现 | `factual_precision`, `concept_f1`, `relation_precision`, `evidence_coverage`, `hallucination_rate`, `path_alignment_best` |

默认聚合：

```text
Evidence Groundedness =
  0.50 * factual_precision
+ 0.15 * concept_f1
+ 0.15 * relation_precision
+ 0.10 * evidence_coverage
+ 0.05 * path_alignment_best
+ 0.05 * (1 - hallucination_rate)
```

解释：`hallucination_rate` 越低越好，因此在聚合时取反。

---

## 3. Interdisciplinary Integration

| 项目 | 内容 |
|---|---|
| 主指标 | Interdisciplinary Integration |
| 定义 | 衡量假设是否真实桥接多个学科，且这些学科之间具有实质性的认知距离。 |
| 子维度 1 | `disciplinary_diversity`：涉及学科的广度。 |
| 子维度 2 | `disciplinary_disparity`：学科之间距离是否足够大。 |
| 子维度 3 | `semantic_bridging`：路径前后是否形成实质性跨域桥接。 |
| 评估方法 | 以 `rao_stirling` 为主分，结合 `disciplinary_leap_index`、`embedding_bridging` 进行解释。 |
| 项目实现 | `rao_stirling`, `disciplinary_leap_index`, `embedding_bridging` |

默认聚合：

```text
Interdisciplinary Integration =
  0.60 * rao_stirling
+ 0.20 * disciplinary_leap_index
+ 0.20 * embedding_bridging
```

解释：`rao_stirling` 同时刻画学科多样性、平衡性和距离，因此作为 X 主分；`disciplinary_leap_index` 捕捉最大单步跨越；`embedding_bridging` 捕捉路径首尾语义距离。

---

## 4. Novelty

| 项目 | 内容 |
|---|---|
| 主指标 | Novelty |
| 定义 | 衡量假设相对历史知识图谱、参考路径和常规组合模式，是否提出了少见且有信息增量的知识重组。 |
| 子维度 1 | `atypical_combination`：概念组合是否非常规。 |
| 子维度 2 | `remote_association`：是否跨越较远语义空间形成新联系。 |
| 子维度 3 | `novelty_convention_balance`：新颖性与传统性之间是否平衡。 |
| 评估方法 | 以 `info_novelty` 为主分；辅助使用 `atypical_combination`、`remote_association_index`、`novelty_convention_balance`。 |
| 项目实现 | `info_novelty`, `atypical_combination`, `remote_association_index`, `novelty_convention_balance` |

默认聚合：

```text
Novelty =
  0.50 * info_novelty
+ 0.20 * atypical_combination
+ 0.20 * remote_association_index
+ 0.10 * novelty_convention_balance
```

解释：`info_novelty` 是基于 KG 三元组频率的 surprisal 分数；`atypical_combination` 衡量非常规组合；`remote_association_index` 衡量语义远程联想；`novelty_convention_balance` 防止假设完全脱离已有知识。

---

## 5. Testability

| 项目 | 内容 |
|---|---|
| 主指标 | Testability |
| 定义 | 衡量假设是否可以被操作化为可观测、可测量、可证伪的验证任务。 |
| 子维度 1 | `specificity`：研究问题是否足够具体。 |
| 子维度 2 | `measurability`：涉及变量是否可以被测量。 |
| 子维度 3 | `falsifiability`：是否存在可能否定该假设的结果。 |
| 子维度 4 | `validation_design_clarity`：是否能提出明确的最小验证方案。 |
| 评估方法 | 当前由 LLM 按子维度评分并取均值；现阶段系统字段为 `specificity`、`measurability`、`falsifiability`、`resource_feasibility`，后续建议将最后一项替换为 `validation_design_clarity`。 |
| 项目实现 | `testability`; 当前子项来自 `PROMPT_TESTABILITY` |

默认聚合：

```text
Testability = testability / 10
```

解释：`testability` 是四个 LLM 子分的平均值，原始范围为 `[0, 10]`；聚合前归一化到 `[0, 1]`，报告时映射到 `[1, 5]`。

---

## 6. Feasibility

| 项目 | 内容 |
|---|---|
| 主指标 | Feasibility |
| 定义 | 衡量假设在当前数据、方法、资源和时间约束下是否现实可执行。 |
| 子维度 1 | `data_feasibility`：验证所需数据、样本或证据是否可获得。 |
| 子维度 2 | `method_feasibility`：所需方法和流程是否成熟可用。 |
| 子维度 3 | `resource_feasibility`：设备、计算、时间和协作成本是否合理。 |
| 子维度 4 | `validation_readiness`：是否能形成最小可行验证方案。 |
| 评估方法 | 由独立的 feasibility prompt 进行 LLM 评分，4 个子分取均值作为 `feasibility` 总分。 |
| 项目实现 | `feasibility`, `feasibility_data`, `feasibility_method`, `feasibility_resource`, `feasibility_validation` |

默认聚合：

```text
Feasibility =
  0.25 * feasibility_data
+ 0.25 * feasibility_method
+ 0.25 * feasibility_resource
+ 0.25 * feasibility_validation
```

解释：四个子分原始范围为 `[0, 10]`，聚合前先归一化到 `[0, 1]`，报告时映射到 `[1, 5]`。若旧结果缺少四个子分，代码会回退使用 `{L}_feasibility`。

---

## 输出位置

标准 KG 评估输出：

```json
{
  "id": "...",
  "scores": {
    "L1_consistency_f1": 0.72
  },
  "x5_scores": {
    "L1": {
      "interdisciplinary_integration": 3.12,
      "structural_validity": 3.72,
      "evidence_groundedness": 3.44,
      "novelty": 3.28,
      "testability": 3.96,
      "feasibility": 3.76
    }
  }
}
```

多模型评估 summary 额外包含：

```json
{
  "by_model_overall": {},
  "x5_by_model_overall": {
    "L1": {
      "model_name": {
        "interdisciplinary_integration": 3.12,
        "structural_validity": 3.72
      }
    }
  },
  "x5_by_model_method": {}
}
```

雷达图生成：

```bash
python generate_x5_radar.py \
  --input outputs/.../multimodel_16metrics_summary.json \
  --output-dir outputs/.../radar_charts \
  --level L1
```

证据源开关示例：

```bash
# 默认：使用 Benchmark GT，不使用 web search
PYTHONPATH=. python crossdisc_extractor/benchmark/evaluate_benchmark.py \
  --benchmark data/benchmark.json \
  --predictions outputs/predictions.json \
  --output outputs/eval_results.json

# GT + web search
PYTHONPATH=. python crossdisc_extractor/benchmark/evaluate_benchmark.py \
  --benchmark data/benchmark.json \
  --predictions outputs/predictions.json \
  --output outputs/eval_results.json \
  --web-search

# 只使用 web search，不使用 Benchmark GT
PYTHONPATH=. python crossdisc_extractor/benchmark/evaluate_benchmark.py \
  --benchmark data/benchmark.json \
  --predictions outputs/predictions.json \
  --output outputs/eval_results.json \
  --no-benchmark-gt \
  --web-search \
  --web-provider openalex
```

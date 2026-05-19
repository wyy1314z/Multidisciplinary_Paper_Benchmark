# computer158 多智能体框架筛选

本文档记录 `benchmark_baseline` 中多智能体相关框架在 `computer158` 任务上的筛选结论。

筛选目标不是“原样复现上游论文所有工程栈”，而是满足下面两个硬约束：

1. 输入内容必须与现有单模型 `computer158` 任务一致
2. 输出格式必须兼容 `outputs/nature_nc_2026_single_query_hyp/computer158_16models`

## 1. 输入一致性约束

现有单模型 `computer158` 任务的真实输入来自 `run_query_benchmark.py`，内容只有：

- `title`
- `primary_discipline`
- `secondary_disciplines`
- 对应层级的 `query`
- 对于 `L2/L3`，还会一并包含 `L1 Query`

特别注意：

- 不包含 `abstract`
- 不包含 `introduction`
- 不包含检索文献、知识图谱、作者知识库、外部网页

因此，多智能体框架也必须只看到这同一份 brief。

## 2. 结论

### 2.1 选入

#### `sciagents`

- 来源：`benchmark_baseline/SciAgentsDiscovery-main`
- 采用方式：保留 `Ontologist -> Scientist -> Critic` 的角色协作机制
- 约束改造：
  - 不接上游 KG、Semantic Scholar、GraphReasoning
  - 只基于同一份 `computer158` brief 做概念化、生成、批评与格式化
- 选入原因：
  - 最符合“多角色协作生成假设”的需求
  - 即便去掉外部图谱，仍能保留较清晰的 agent 分工

#### `moose_chem`

- 来源：`benchmark_baseline/MOOSE-Chem-main`
- 采用方式：保留 `inspiration extraction -> composition -> ranking`
- 约束改造：
  - 不接默认 inspiration corpus
  - inspirations 只允许从同一份 `computer158` brief 中抽取
- 选入原因：
  - 能引入“灵感重组”这一类与普通单模型不同的生成机制
  - 不需要外部数据库也可以保留核心 agent 流程

#### `infal`

- 来源：`benchmark_baseline/InfAL-main`
- 采用方式：保留 `Generator -> Optimizer -> Discriminator`
- 约束改造：
  - `initial idea` 只能从同一份 `computer158` brief 生成
  - 不读取上游数据集中的已有 research ideas
- 选入原因：
  - 对“生成后再优化”的框架类型有代表性
  - 同输入限制下仍可保留 adversarial refinement 的核心思想

#### `virsci`

- 来源：`benchmark_baseline/Virtual-Scientists-main`
- 采用方式：保留 team-based debate / review / arbitration
- 约束改造：
  - 不接 AMiner、FAISS、author knowledge bank、adjacency matrix
  - 只做 paper-seeded lightweight team discussion
- 选入原因：
  - 能给数据库增加“团队协作式”生成风格
  - 与 `sciagents` 相比，更偏多科学家辩论与汇总

### 2.2 不选入

#### `ai_scientist`

- 来源：`benchmark_baseline/AI-Scientist-main`
- 不选入原因：
  - 上游主流程偏模板驱动、代码执行、实验运行、论文写作
  - 不是当前任务下最干净的“同输入多智能体生成”基线
  - 若硬接原版，会引入大量与 `computer158` query 任务无关的变量

## 3. 落地方式

最终采用的不是这些上游仓库的重型原版执行栈，而是：

- 在本仓库中实现 lightweight runner
- 只复用各框架的 agent 机制与交互拓扑
- 把输入严格锁死为单模型 `computer158` 的同一份 brief
- 把输出严格锁死为单模型结果同款 JSON schema

对应执行入口：

- [run_multiagent_query_benchmark.py](/ssd/wangyuyang/git/benchmark/run_multiagent_query_benchmark.py:1)
- [run_nature_nc_2026_computer158_multiagent_three_levels.sh](/ssd/wangyuyang/git/benchmark/run_nature_nc_2026_computer158_multiagent_three_levels.sh:1)

## 4. 当前阻塞

正式运行 `gpt-5.5` 之前，仍需解决两类环境问题：

1. 当前 shell 里没有 `OPENAI_API_KEY`
2. 现有 `gpt-5.5` 单模型结果曾报错：
   - `model ratio not configured for model: gpt-5.5`

因此，本次代码默认会先做 preflight / smoke test，避免全量任务直接写入错误结果。

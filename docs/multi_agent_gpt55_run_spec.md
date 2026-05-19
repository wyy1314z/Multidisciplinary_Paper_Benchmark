# 6框架 × GPT-5.5 运行规范

本文档给出一版与 `outputs/nature_nc_2026_single_query_hyp/computer158_16models` 风格兼容的多智能体运行规范，目标是：

- 6 个多智能体框架统一使用 `gpt-5.5` 作为主基座
- 输出目录、文件命名、字段结构尽量复用现有单模型格式
- 方便后续将单模型与多智能体生成的假设合并到同一个数据库

适用输入集：

- `outputs/nature_nc_2026_single_query_hyp/single_query_hypothesis_dataset_computer_158.json`


## 0. 运行前检查

当前仓库中已经存在 `gpt-5.5` 的失败记录，例如：

- `outputs/nature_nc_2026_single_query_hyp/computer158_16models/l1_results/gpt-5.5.json`

错误核心是：

- `model ratio not configured for model: gpt-5.5`

因此在正式运行 6 个框架前，必须先确认：

1. 网关或代理中 `gpt-5.5` 已启用
2. 计费倍率或模型映射已配置
3. 单次 smoke test 可以成功返回非错误假设

若上述问题未解决，不要直接启动全量任务，否则会批量写入错误结果。


## 1. 最终运行清单

统一主基座：

- `gpt-5.5`

统一输入：

- `computer_158` 的 158 条三层 query

统一框架列表：

1. `ai_scientist`
2. `sciagents`
3. `moose_chem`
4. `infal`
5. `moose_chem2`
6. `virsci`

对应最终运行清单：

1. `AI Scientist + gpt-5.5`
2. `SciAgents + gpt-5.5`
3. `MOOSE-Chem + gpt-5.5`
4. `InfAL + gpt-5.5`
5. `MOOSE-Chem2 + gpt-5.5`
6. `VIRSCI + gpt-5.5`

每个框架都跑：

- `L1`: 158 条
- `L2`: 158 条
- `L3`: 158 条

每个框架最终产出：

- `474` 条主假设记录

6 个框架合计：

- `2,844` 条主假设记录


## 2. 目录命名方案

建议在 `outputs/nature_nc_2026_single_query_hyp/` 下按“每个框架一个目录”组织，这样最接近当前 `computer158_16models` 的结构。

建议目录名：

- `computer158_ai_scientist_gpt55`
- `computer158_sciagents_gpt55`
- `computer158_moose_chem_gpt55`
- `computer158_infal_gpt55`
- `computer158_moose_chem2_gpt55`
- `computer158_virsci_gpt55`

每个目录内部统一包含：

```text
computer158_<framework>_gpt55/
├── l1_results/
│   └── gpt-5.5.json
├── l2_results/
│   └── gpt-5.5.json
├── l3_results/
│   └── gpt-5.5.json
├── models.txt
├── pipeline.pid
├── pipeline_<timestamp>.log
├── run_l1_<timestamp>.log
├── run_l2_<timestamp>.log
├── run_l3_<timestamp>.log
├── computer158_<framework>_gpt55_l1_l2_l3_hypotheses.json
└── computer158_<framework>_gpt55_l1_l2_l3_hypotheses.md
```

说明：

- `models.txt` 内容固定为一行：`gpt-5.5`
- `l1_results/l2_results/l3_results` 的文件名保持与现有单模型一致：`gpt-5.5.json`
- 聚合文件用来模仿 `computer10_multimodel_l1_l2_l3_hypotheses.json` 的浏览体验


## 3. 聚合文件格式

为了兼容你现有的“按论文查看所有方法输出”的方式，建议每个框架都额外生成一个聚合文件：

- `computer158_<framework>_gpt55_l1_l2_l3_hypotheses.json`

聚合文件的单条记录建议如下：

```json
{
  "index": 1,
  "title": "...",
  "journal": "...",
  "doi": "...",
  "publication_date": "...",
  "primary_discipline": "...",
  "secondary_disciplines": ["..."],
  "query": {
    "L1": "...",
    "L2": "...",
    "L3": "..."
  },
  "generated_hypotheses": {
    "L1": {
      "gpt-5.5": {
        "method_name": "ai_scientist-gpt-5.5-L1",
        "prompt_level": "L1",
        "hypothesis_format": "l1_single",
        "error": "",
        "text": "..."
      }
    },
    "L2": {
      "gpt-5.5": {
        "method_name": "ai_scientist-gpt-5.5-L2",
        "prompt_level": "L2",
        "hypothesis_format": "single_level",
        "error": "",
        "text": "..."
      }
    },
    "L3": {
      "gpt-5.5": {
        "method_name": "ai_scientist-gpt-5.5-L3",
        "prompt_level": "L3",
        "hypothesis_format": "single_level",
        "error": "",
        "text": "..."
      }
    }
  }
}
```

这里的 key 仍然保留 `gpt-5.5`，因为该聚合文件是“单框架、单模型”的视图。


## 4. 每层结果 JSON 的统一字段定义

为保证与现有 `computer158_16models/l1_results/*.json` 完全兼容，建议保留顶层字段不变：

```json
{
  "paper_id": "...",
  "method_name": "...",
  "prompt_level": "L1",
  "hypothesis_format": "l1_single",
  "query": "...",
  "free_text_hypotheses": ["..."],
  "error": "",
  "metadata": {}
}
```

### 4.1 顶层字段

- `paper_id`
  - 推荐使用 DOI URL
  - 例：`https://doi.org/10.1038/...`

- `method_name`
  - 统一格式：
  - `<framework>-gpt-5.5-<level>`
  - 例：
    - `ai_scientist-gpt-5.5-L1`
    - `sciagents-gpt-5.5-L2`
    - `moose_chem2-gpt-5.5-L3`

- `prompt_level`
  - 枚举：`L1` / `L2` / `L3`

- `hypothesis_format`
  - 建议：
    - `L1` 使用 `l1_single`
    - `L2/L3` 使用 `single_level`
  - 这样与现有文件保持一致

- `query`
  - 当前层级对应的 query 文本

- `free_text_hypotheses`
  - 列表，默认只放 1 条最终主假设
  - 若框架内部有多个候选，不要全部展开到这里
  - 只保留最终 top-1

- `error`
  - 成功时为空字符串
  - 失败时记录错误文本

- `metadata`
  - 承载所有多智能体特有信息


### 4.2 metadata 子字段

建议统一如下：

```json
{
  "journal": "...",
  "doi": "...",
  "publication_date": "...",
  "primary_discipline": "...",
  "secondary_disciplines": ["..."],
  "generation_family": "multi_agent",
  "framework_name": "ai_scientist",
  "framework_version": "v1",
  "backbone_model": "gpt-5.5",
  "agent_topology": "planner-generator-critic-refiner",
  "agent_roles": ["planner", "generator", "critic", "refiner"],
  "num_rounds": 2,
  "retrieval_enabled": false,
  "tool_use_enabled": false,
  "seed": 42,
  "temperature": 0.7,
  "final_selector": "critic",
  "elapsed_seconds": 18.4,
  "trace_id": "paper001_l2_run20260507_xxx"
}
```

最少必备字段：

- `generation_family`
- `framework_name`
- `framework_version`
- `backbone_model`
- `agent_topology`
- `agent_roles`
- `num_rounds`
- `retrieval_enabled`
- `tool_use_enabled`
- `seed`
- `temperature`

推荐补充字段：

- `final_selector`
- `elapsed_seconds`
- `trace_id`


## 5. 6 个框架的 method_name / topology 约定

### AI Scientist

- `framework_name`: `ai_scientist`
- `framework_version`: `v1`
- `agent_topology`: `generator-self_critic-refiner`
- `agent_roles`: `["generator", "self_critic", "refiner"]`

### SciAgents

- `framework_name`: `sciagents`
- `framework_version`: `v1`
- `agent_topology`: `ontologist-scientist-critic`
- `agent_roles`: `["ontologist", "scientist", "critic"]`

### MOOSE-Chem

- `framework_name`: `moose_chem`
- `framework_version`: `v1`
- `agent_topology`: `inspiration_extractor-generator-ranker`
- `agent_roles`: `["inspiration_extractor", "generator", "ranker"]`

### InfAL

- `framework_name`: `infal`
- `framework_version`: `v1`
- `agent_topology`: `generator-optimizer-discriminator`
- `agent_roles`: `["generator", "optimizer", "discriminator"]`

### MOOSE-Chem2

- `framework_name`: `moose_chem2`
- `framework_version`: `v1`
- `agent_topology`: `coarse_generator-refiner-ranker`
- `agent_roles`: `["coarse_generator", "refiner", "ranker"]`

### VIRSCI

- `framework_name`: `virsci`
- `framework_version`: `v1`
- `agent_topology`: `team_generator-reviewer-arbiter`
- `agent_roles`: `["team_generator", "reviewer", "arbiter"]`


## 6. 统一输出原则

为保证数据库可比较性，建议统一以下规则：

1. 每个 `paper × framework × level` 只保留 `1` 条最终假设
2. 不把中间 agent 讨论内容直接放入 `free_text_hypotheses`
3. 中间讨论内容单独保存到 trace 文件
4. 若失败，仍写入占位记录，保证数组长度和论文顺序一致
5. 所有框架统一使用相同输入字段：
   - `title`
   - `abstract`
   - `introduction`
   - `primary_discipline`
   - `secondary_disciplines`
   - 对应层级的 `query`


## 7. 建议的 trace 文件命名

如果要保留多智能体内部推理轨迹，建议单独放：

```text
computer158_<framework>_gpt55/
└── traces/
    ├── L1/
    │   └── <paper_hash>.json
    ├── L2/
    │   └── <paper_hash>.json
    └── L3/
        └── <paper_hash>.json
```

trace 文件中可包含：

- 初始输入
- 每轮 agent 输出
- 内部评分
- 最终选择理由

但这些内容不应直接进入主评分 JSON。


## 8. 最终建议

如果你现在就开始实现，我建议第一版严格按下面执行：

1. 6 个框架全部统一用 `gpt-5.5`
2. 每个框架一个目录
3. 每个目录保留 `l1_results / l2_results / l3_results / models.txt / logs`
4. 每条记录的顶层字段与 `computer158_16models` 保持完全一致
5. 多智能体特有信息全部塞进 `metadata`
6. 另行保存 trace，不污染主评分表

这版最利于：

- 和现有单模型库并排管理
- 构建专家标注数据库
- 后续比较“专家分 vs benchmark 分”的一致性

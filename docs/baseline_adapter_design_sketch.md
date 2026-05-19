# Baseline Adapter 设计草图

本文档面向 `/ssd/wangyuyang/git/benchmark` 的对比实验框架，给出 6 个推荐 baseline 的 adapter 设计草图。

统一约束：
- 外部 baseline 只允许读取 `title / abstract / introduction / discipline labels`
- 不直接读取 `concepts / relations / queries`
- 对外统一输出 `HypothesisOutput.free_text_hypotheses`
- 若方法天然带排序，则保持原顺序，交给评测侧按“首条优先，失败回退到最长”消费

公共依赖：
- 输入白名单 helper: `baseline.common.get_external_baseline_input`
- 输出协议: `baseline.common.HypothesisOutput`
- 评测入口: `baseline.evaluate_all.evaluate_single_output`

## 1. AI Scientist

- 目标文件: `baseline/adapters/ai_scientist.py`
- 目标类: `AiScientistAdapter`
- 输入构造:
  - `title`
  - `abstract`
  - `introduction snippet`
  - `primary / secondary disciplines`
- 生成流程:
  1. 拼装 research brief
  2. 让模型输出 JSON idea 数组
  3. 每条 idea 至少包含 `Name / Title / Hypothesis / Experiment`
- 输出归一化:
  - 主输出: `"[Name] Title: Hypothesis"`
  - 辅助信息: `Experiment / Novelty / Feasibility` 写入 `raw_responses`
- 适配说明:
  - 当前仓库已具备简化版，可作为最先稳定化的 baseline

## 2. SciAgents

- 目标文件: `baseline/adapters/sciagents.py`
- 目标类: `SciAgentsAdapter`
- 输入构造:
  - 仅使用论文文本和学科标签
  - 不喂 CrossDisc 已抽取概念，避免信息泄漏
- 生成流程:
  1. `Ontologist` 从 title/abstract/introduction 中抽概念、关系、gap
  2. `Scientist` 基于 gap 生成 hypotheses
  3. `Critic` 精炼 hypotheses 并给出内部评分
- 输出归一化:
  - 主输出: `refined hypothesis`
  - 可选拼接: `mechanism + testable prediction`
  - agent 中间产物保留到 `raw_responses`
- 后续增强:
  - 若要吃结构化指标，可新增一个文本到 3-step path 的 parser

## 3. MOOSE-Chem

- 目标文件: `baseline/adapters/moose_chem.py`
- 目标类: `MooseChemAdapter`
- 输入构造:
  - `title + abstract + introduction`
  - `primary / secondary disciplines`
- 生成流程:
  1. Stage 1 从论文中抽 inspiration fragments
  2. Stage 2 组合 inspirations 生成 ranked hypotheses
- 输出归一化:
  - 仅保留 `hypothesis` 字段到 `free_text_hypotheses`
  - `inspiration_sources` 保留在 `raw_responses`
- 后续增强:
  - 若后面接官方检索流程，可在 adapter 内新增 `retrieve_inspirations()` 阶段

## 4. InfAL

- 目标文件: `baseline/adapters/infal.py`
- 目标类: `InfALAdapter`
- 输入构造:
  - `title + abstract + introduction`
  - `primary / secondary disciplines`
  - 允许在 adapter 内部基于上述文本生成 `initial idea`
- 生成流程:
  1. `Generator` 产出初始 idea
  2. `Optimizer` 分别沿 `novelty` 或 `feasibility` 方向改写
  3. `Discriminator` 选择更优版本
- 输出归一化:
  - 推荐保留 2 条: `novelty-optimized` 与 `feasibility-optimized`
  - 顺序即方法内部排序
- 关键难点:
  - 官方范式更像“idea refinement”，需要在 adapter 内补一层 seed idea 生成

## 5. MOOSE-Chem2

- 目标文件: `baseline/adapters/moose_chem2.py`
- 目标类: `MooseChem2Adapter`
- 输入构造:
  - `title + abstract + introduction`
  - `discipline labels`
  - adapter 内补一个 `coarse hypothesis`
- 生成流程:
  1. 先从论文文本生成 coarse-grained hypothesis
  2. 多轮 refinement 到 fine-grained, actionable hypothesis
  3. 若方法内部提供 rank，则保留 rank-1 在首位
- 输出归一化:
  - 主输出: final fine-grained hypothesis
  - 可选保留: coarse hypothesis、refinement trace
- 关键难点:
  - 非化学任务的 prompt 迁移
  - coarse hypothesis 的稳定构造

## 6. VIRSCI / Virtual Scientists

- 目标文件: `baseline/adapters/virsci.py`
- 目标类: `VirSciAdapter`
- 输入构造:
  - 只从 `title / abstract / introduction / disciplines` 出发
  - 不强依赖官方全文数据库、author KB、FAISS 索引
- 生成流程:
  1. 构造 paper-seeded team brief
  2. 多 agent 分别扮演不同科学家角色提出 ideas
  3. 汇总、投票、精炼
- 输出归一化:
  - 主输出: team final proposal
  - 候选输出: top-k team ideas
  - 讨论记录放入 `raw_responses`
- 关键难点:
  - 官方工程栈较重，建议优先实现“轻量 agent 版”

## 推荐实现顺序

1. `AiScientistAdapter` 稳固化
2. `MooseChemAdapter` 稳固化
3. `SciAgentsAdapter` 稳固化
4. 新增 `InfALAdapter`
5. 新增 `MooseChem2Adapter`
6. 新增 `VirSciAdapter`

## 最小落地清单

- `baseline/common.py`
  - 统一外部输入 helper
- `baseline/evaluate_all.py`
  - 主假设选择策略: 首条优先，失败回退到最长
- `baseline/adapters/*.py`
  - 全部改用白名单输入 helper
- 新增 adapter
  - `infal.py`
  - `moose_chem2.py`
  - `virsci.py`

# Cross-Disciplinary Knowledge Extraction & Benchmarking System

本项目是一个面向跨学科研究的知识抽取、假设生成与自动评测系统。该系统利用大语言模型（LLM）从学术文献中提取结构化知识，构建跨学科知识图谱，并生成多层级的科学假设。此外，项目还包含了一套完整的 Benchmark 构建与自动评测流水线，用于评估模型在跨学科创新性、可行性和科学性方面的表现。

## 目录

- [核心功能](#核心功能)
- [环境配置](#环境配置)
- [快速开始](#快速开始)
  - [知识抽取](#1-知识抽取-extraction)
  - [结果导出](#2-结果导出-export)
  - [数据集构建](#3-benchmark-构建-build-dataset)
  - [自动评测](#4-自动评测-evaluation)
- [项目结构](#项目结构)
- [高级配置](#高级配置)

---

## 核心功能

1.  **三阶段知识抽取 (Multi-Stage Extraction)**
    -   **Stage 1: 结构化抽取 (Structure)** - 从论文摘要/全文中提取核心概念、实体及其语义关系。
    -   **Stage 2: 跨学科查询生成 (Query Generation)** - 生成 L1（浅层）、L2（中层）、L3（深层）三级跨学科探索查询。
    -   **Stage 3: 假设生成 (Hypothesis Generation)** - 基于提取的知识结构，生成具有逻辑链条的科学假设，并按学科层级分类。

2.  **Benchmark 数据集构建**
    -   将抽取得到的非结构化/半结构化结果转换为标准化的 Benchmark 格式。
    -   自动构建 Ground Truth 知识图谱，包含节点学科属性与层级化路径。

3.  **多维度自动评测 (Automated Evaluation)**
    -   **基于知识图谱的检索**: 根据学科相关性在 Ground Truth 中检索参考路径。
    -   **LLM-as-a-judge**: 利用大模型从**创新性 (Innovation)**、**可行性 (Feasibility)**、**科学性 (Scientificity)** 三个维度对生成假设进行打分 (0-10分)。
    -   **路径相似度计算**: 评估生成路径与真实科研路径的语义重合度。

4.  **数据导出与可视化**
    -   支持将复杂的嵌套 JSON 结果导出为 CSV/Excel 报表，便于人工核查与分析。

---

## 环境配置

### 1. 依赖安装

确保 Python 版本 >= 3.9。

```bash
pip install -r requirements.txt
# 主要依赖: openai, pydantic, networkx, tqdm, pandas, numpy
```

### 2. 环境变量

运行前必须配置 `PYTHONPATH` 和 LLM API 密钥。

```bash
# Linux / macOS
export PYTHONPATH=$PYTHONPATH:/path/to/project_root
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
# 可选：如果使用自定义 API Endpoint
# export OPENAI_BASE_URL="https://your-custom-endpoint/v1"
```

---

## 快速开始

### 1. 知识抽取 (Extraction)

使用 `extractor_multi_stage.py` 进行单篇或批量抽取。

**单篇测试 (`one` 模式):**
```bash
python3 crossdisc_extractor/extractor_multi_stage.py one \
  --title "Deep Learning in Genomics" \
  --abstract "This paper explores..." \
  --primary "Bioinformatics" \
  --output result_single.json
```

**批量处理 (`batch` 模式):**
支持断点续传与多线程并发。
```bash
python3 crossdisc_extractor/extractor_multi_stage.py batch \
  --input papers.json \
  --output extraction_results.json \
  --num-workers 4 \
  --max-tokens-struct 12000
```

### 2. 结果导出 (Export)

将复杂的 JSON 抽取结果转换为易读的 CSV 表格或简化版 JSON，包含学科、各级 Query 和假设摘要。

**导出为 CSV:**
```bash
python3 crossdisc_extractor/extractor_multi_stage.py export \
  --input extraction_results.json \
  --output extraction_summary.csv
```

**导出为 JSON:**
```bash
python3 crossdisc_extractor/extractor_multi_stage.py export \
  --input extraction_results.json \
  --output extraction_summary.json
```

### 3. Benchmark 构建 (Build Dataset)

将抽取结果清洗并转换为标准 Benchmark 格式（Ground Truth）。

```bash
python3 crossdisc_extractor/benchmark/build_dataset.py \
  --input extraction_results.json \
  --output benchmark_dataset.json
```

### 4. 自动评测 (Evaluation)

评估模型预测结果与 Benchmark 的一致性及质量。

```bash
python3 crossdisc_extractor/benchmark/evaluate_benchmark.py \
  --benchmark benchmark_dataset.json \
  --predictions prediction_results.json \
  --output eval_scores.json
```

---

## 项目结构

```text
crossdisc_extractor/
├── extractor_multi_stage.py    # [核心] 三阶段抽取主程序 (CLI 入口)
├── graph_builder.py            # 知识图谱构建模块 (NetworkX)
├── schemas.py                  # Pydantic 数据模型定义 (Extraction, Graph, Hypothesis)
├── benchmark/                  # Benchmark 与评测相关
│   ├── build_dataset.py        # 数据集构建脚本
│   ├── evaluate_benchmark.py   # 自动评测脚本 (KG构建 + LLM打分)
│   └── eval_prompts.py         # 评测用 Prompt 模板
├── prompts/                    # 抽取用 Prompt 模板
│   ├── struct_prompt_split.py  # 结构抽取 (概念/关系)
│   ├── query_prompt.py         # Query 生成
│   └── hypothesis_prompt_split.py # 假设生成
└── utils/                      # 工具库
    ├── llm.py                  # LLM 调用封装 (重试、错误处理)
    └── pdf_utils.py            # PDF 文本解析
```

## 高级配置

### 模型参数调整
在 `extractor_multi_stage.py` 中可通过 CLI 参数调整各阶段的 `max_tokens`，以防止长文本截断：
- `--max-tokens-struct`: 结构抽取阶段 (默认 12000)
- `--max-tokens-query`: Query 生成阶段
- `--max-tokens-hyp`: 假设生成阶段

### 评测维度定制
修改 `benchmark/eval_prompts.py` 中的 `PROMPT_EVAL_L1` 和 `PROMPT_EVAL_DEEP` 可调整 LLM 评分的标准和权重。

---

## 贡献与研究现状对比 (Contribution & Gap Analysis)

结合 2024-2025 年最新文献，本项目在 **评测任务认知深度**、**评测维度结构化** 以及 **评测标准客观性** 三个维度上填补了现有 Benchmark 的空白。

### 1. 评测任务的认知深度：从“执行能力”到“深度构思”
**(From Execution Capabilities to Deep Ideation)**

*   **已有 Benchmark Gap：**
    *   **侧重“手”的执行 (Execution-heavy)：** 目前主流的科学 Benchmark 主要考察 AI 作为“实验员”的能力。
        *   **MLAgentBench (2023)**、**ScienceAgentBench (ICLR 2025)** 和 **PaperBench (2025)** 主要评测模型能否正确写代码、跑通实验流程或复现论文结果。
        *   **The AI Scientist (2024)** 和 **Agent Laboratory (2025)** 虽然涉及全流程，但其评测核心仍在于“产出的完整性”而非“想法的深刻性”。
    *   **侧重“脑”的记忆 (Recall-heavy)：** 另一类 Benchmark 则侧重于教科书级别的解题或检索。
        *   **SciBench (ICML 2024)** 和 **GPQA** 主要考察对存量知识（大学习题）的记忆与应用，而非创造新知识。
        *   **LitSearch (2024)** 仅评估文献检索的准确率。
    *   **缺失的一环：** 缺乏专门针对 **"Deep Ideation" (深度构思)** —— 即**跨学科逻辑推演**和**复杂假设生成能力**的评测基准。现有的 Benchmark 无法区分一个 AI 是仅仅在做“词语拼接”，还是真正理解了生物学机制与深度学习算法之间的深层联系。

*   **本项目贡献 (Benchmark Contribution)：**
    *   **定义了“分层假设生成”任务 (Hierarchical Hypothesis Task)：** 本项目提出了首个 **L1-L3 分层假设评测标准**。我们不考代码能不能跑通，而是专门考察模型能否从表象关联 (L1) 推演至机理 (L2)，最终实现跨学科融合 (L3)。
    *   **填补认知评测空白：** 这是一个专注于 **Interdisciplinary Hypothesis Generation** 的高难度测试床，迫使模型走出“舒适区”，在没有直接训练数据的情况下建立学科间的逻辑桥梁。

### 2. 评测维度的结构化：从“文本打分”到“图谱度量”
**(From Textual Scoring to Graph-driven Metrics)**

*   **已有 Benchmark Gap：**
    *   **维度的单一性与主观性：** 现有的评测指标往往缺乏对“科学创新结构”的洞察。
        *   **Nova (2024)** 和 **SciMON (ACL 2024)** 主要依赖文本相似度或 LLM 自我打分 (Self-Eval) 来判断新颖性，这容易产生幻觉且缺乏可解释性。
        *   **ResearchBench (2025)** 虽然评估了灵感排序，但仍是基于列表的扁平化评估，无法捕捉知识点之间的拓扑关系。
    *   **图谱资源的未充分利用：** 像 **iKraph (Nature Sci. Data 2025)** 这样的工作虽然构建了图谱，但仅作为**数据资源**存在，并未将其转化为**评测标准**。目前尚无 Benchmark 利用知识图谱的拓扑结构来量化评估 AI 生成假设的“跨度”和“连接质量”。

*   **本项目贡献 (Benchmark Contribution)：**
    *   **引入结构化图论指标 (Graph-aware Metrics)：** 本 Benchmark 独创性地将**动态知识图谱**引入评测闭环。我们不只看生成的文本“像不像”论文，而是通过 **Bridging Score (桥接分数)** 和 **Path Consistency (路径一致性)** 等指标，量化模型在知识拓扑空间中的“跳跃距离”。
    *   **量化“创新跨度”：** 这是首个能用数字精确衡量“AI 是否成功连接了两个原本疏离的学科领域”的评测体系，比单纯的文本打分更能本质地反映科学发现的结构化创新。

### 3. 评测标准的客观性：基于真实科研路径的后验评估
**(Objective Evaluation Based on Historical Ground Truth)**

*   **已有 Benchmark Gap：**
    *   **缺乏标准答案 (Lack of Ground Truth)：** 科学发现本质上是开放的，导致评测极难标准化。
        *   **Breast Cancer Lab Validation (2025)** 实现了最硬核的湿实验验证，但成本极高、周期长，无法作为通用的 Benchmark 复现。
        *   **G-Eval (2024)** 和 **PandaLM (ICLR 2024)** 依赖 LLM-as-a-judge，容易受 Prompt 诱导，且存在“模型偏好循环验证”的问题。
        *   **HypER (EMNLP 2025)** 虽然引入了证据支持度，但主要关注推理链的有效性，而非结果的科学价值。

*   **本项目贡献 (Benchmark Contribution)：**
    *   **Hindsight Evaluation (后验评测范式)：** 本 Benchmark 巧妙利用**科学发展史**作为天然的实验室。我们从海量文献中构建出 **真实发生的科研演进路径 (Ground Truth Paths)** 作为参考答案。
    *   **可复现的客观标准：** 将高度主观的“创新性评测”转化为客观的“路径预测与重构”任务。这为 AI for Science 领域提供了一套**低成本、可复现、非主观**的标准答案集，解决了“只有做实验才能验证”的评测困境。

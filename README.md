# Cross-Disciplinary Knowledge Extraction & Benchmarking System

本项目是一个面向跨学科研究的**论文学科分类、知识抽取、假设生成与自动评测**一体化系统。系统集成了学科分类器（自动判定论文所属学科领域并识别跨学科论文）和知识抽取流水线（利用大语言模型从学术文献中提取结构化知识、构建跨学科知识图谱并生成多层级科学假设），提供从原始论文到评测结果的完整闭环。

## 目录

- [核心功能](#核心功能)
- [环境配置](#环境配置)
- [快速开始](#快速开始)
  - [单元测试](#0-单元测试)
  - [统一流水线](#统一流水线-crossdisc-pipeline)
  - [单篇抽取](#1-单篇论文抽取-one)
  - [批量抽取](#2-批量抽取-batch)
  - [结果导出](#3-结果导出-export)
  - [数据集构建](#4-benchmark-构建-build-dataset)
  - [自动评测](#5-自动评测-evaluation)
  - [结果可视化](#6-结果可视化)
  - [完整流程](#完整流程)
- [项目结构](#项目结构)
- [高级配置](#高级配置)
- [开发指南](#开发指南)
- [贡献与研究现状对比](#贡献与研究现状对比-contribution--gap-analysis)

---

## 核心功能

1.  **论文学科分类与跨学科识别 (Discipline Classification)**
    -   基于层级分类法（MSC 等）对论文进行自动学科分类。
    -   判断论文是否属于跨学科论文，提取主学科和辅学科层级。
    -   支持异步并发分类，可扩展至多种 LLM 后端（LangChain）。

2.  **三阶段知识抽取 (Multi-Stage Extraction)**
    -   **Stage 1: 结构化抽取 (Structure)** - 从论文摘要/全文中提取核心概念、实体及其语义关系。
    -   **Stage 2: 跨学科查询生成 (Query Generation)** - 生成 L1（浅层）、L2（中层）、L3（深层）三级跨学科探索查询。
    -   **Stage 3: 假设生成 (Hypothesis Generation)** - 基于提取的知识结构，生成具有逻辑链条的科学假设，并按学科层级分类。

3.  **Benchmark 数据集构建**
    -   将抽取得到的非结构化/半结构化结果转换为标准化的 Benchmark 格式。
    -   自动构建 Ground Truth 知识图谱，包含节点学科属性与层级化路径。

4.  **多维度自动评测 (Automated Evaluation)**
    -   **基于知识图谱的检索**: 根据学科相关性在 Ground Truth 中检索参考路径。
    -   **LLM-as-a-judge**: 利用大模型从**创新性 (Innovation)**、**可行性 (Feasibility)**、**科学性 (Scientificity)** 三个维度对生成假设进行打分 (0-10分)。
    -   **路径相似度计算**: 评估生成路径与真实科研路径的语义重合度。

5.  **统一流水线 (Unified Pipeline)**
    -   `crossdisc-pipeline full`：一键完成 论文分类 → 跨学科过滤 → 知识抽取 的全流程。
    -   `crossdisc-pipeline classify`：仅运行学科分类，输出跨学科论文。
    -   `crossdisc-pipeline extract`：仅对已分类数据运行知识抽取。

6.  **数据导出与可视化**
    -   支持将复杂的嵌套 JSON 结果导出为 CSV/Excel 报表，便于人工核查与分析。

---

## 环境配置

### 1. 依赖安装

确保 Python 版本 >= 3.9。

```bash
# 推荐：以可编辑模式安装（自动处理 PYTHONPATH）
pip install -e .

# 安装全部依赖（含开发工具、可视化、PDF解析）
pip install -e ".[all]"

# 或仅安装核心依赖
pip install -r requirements.txt
```

### 2. 环境变量

```bash
# 必填：LLM API 密钥
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 可选：自定义 API Endpoint（默认 http://api.shubiaobiao.cn/v1）
export OPENAI_BASE_URL="https://your-custom-endpoint/v1"

# 可选：指定模型名称（默认 deepseek-v3）
export OPENAI_MODEL="deepseek-v3"
```

> **注意**：未设置 `OPENAI_API_KEY` 时，LLM 调用将返回 Mock 随机分数，可用于功能验证但不具备实际评测意义。

---

## 快速开始

### 0. 单元测试

项目包含 114 个单元测试，覆盖数据模型、JSON 解析、配置管理、评测模块和学科分类器。

```bash
# 使用 Makefile（推荐）
make test              # 运行全部测试
make test-cov          # 带覆盖率报告
make lint              # 代码风格检查 (ruff)
make typecheck         # 类型检查 (mypy)
make ci                # 一键运行 lint + typecheck + test

# 或直接使用 pytest
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_schemas.py -v     # 数据模型 (25 tests)
python -m pytest tests/test_parsing.py -v     # JSON 解析 (20 tests)
python -m pytest tests/test_config.py -v      # 配置管理 (8 tests)
python -m pytest tests/test_evaluate.py -v    # 评测模块 (17 tests)
python -m pytest tests/test_classifier_*.py -v  # 学科分类器 (44 tests)
```

### 统一流水线 (crossdisc-pipeline)

统一流水线将学科分类与知识抽取整合为一个命令。

**完整流水线（分类 → 过滤跨学科 → 抽取）：**
```bash
crossdisc-pipeline full \
  --input papers.jsonl \
  --output results.jsonl \
  --config configs/default.yaml
```

**仅分类（输出跨学科论文）：**
```bash
crossdisc-pipeline classify \
  --input papers.jsonl \
  --output classified.jsonl \
  --config configs/default.yaml
```

**仅抽取（对已分类数据）：**
```bash
crossdisc-pipeline extract \
  --input classified.jsonl \
  --output results.jsonl
```

### 1. 单篇论文抽取 (one)

使用 `run.py` 进行单篇论文的三阶段知识抽取。

**最简用法：**
```bash
python run.py one \
  --title "Deep Learning in Genomics" \
  --abstract "This paper explores the application of deep learning..."
```

**完整参数（指定学科 + 中文输出 + 保存结果）：**
```bash
python run.py one \
  --title "Deep Learning in Genomics" \
  --abstract "This paper explores the application of deep learning..." \
  --primary "计算机科学技术" \
  --secondary "生物学,数学" \
  --language-mode chinese \
  --max-tokens-struct 4000 \
  --max-tokens-query 2000 \
  --max-tokens-hyp 4000 \
  --output result.json
```

**显示模型原始响应（调试用）：**
```bash
python run.py one \
  --title "..." --abstract "..." \
  --show-raw
```

### 2. 批量抽取 (batch)

支持多线程并发与断点续传。

**串行处理（默认，安全稳定）：**
```bash
python run.py batch \
  --input papers.json \
  --output results.jsonl
```

**并行处理（4 个 worker，限速每条间隔 1 秒）：**
```bash
python run.py batch \
  --input papers.json \
  --output results.jsonl \
  --num-workers 4 \
  --sleep 1
```

**断点续传（程序中断后恢复，跳过已完成记录）：**
```bash
python run.py batch \
  --input papers.json \
  --output results.jsonl \
  --resume
```

**强制重新处理全部（忽略已有输出）：**
```bash
python run.py batch \
  --input papers.json \
  --output results.jsonl \
  --no-resume
```

**抽样处理前 50 条 + 中文输出：**
```bash
python run.py batch \
  --input papers.json \
  --output results.jsonl \
  --max-items 50 \
  --language-mode chinese
```

> **输入格式**：JSON / JSONL / CSV，每条需包含 `title`、`abstract` 字段，可选 `primary`、`secondary`。

### 3. 结果导出 (export)

将复杂的 JSON 抽取结果转换为易读的 CSV 表格或简化版 JSON，包含学科、各级 Query 和假设摘要。

```bash
# 导出为 CSV
python run.py export \
  --input results.jsonl \
  --output summary.csv

# 导出为 JSON
python run.py export \
  --input results.jsonl \
  --output summary.json
```

### 4. Benchmark 构建 (Build Dataset)

将抽取结果清洗并转换为标准 Benchmark 格式（Ground Truth）。

```bash
python -m crossdisc_extractor.benchmark.build_dataset \
  --input results.jsonl \
  --output benchmark.json
```

### 5. 自动评测 (Evaluation)

评估模型预测结果与 Benchmark 的一致性及质量。评测维度包括创新性、可行性、科学性、桥接分数和路径一致性。

```bash
# 标准评测
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark benchmark.json \
  --predictions results.jsonl \
  --output eval_results.json

# 仅评测前 10 条（快速验证）
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark benchmark.json \
  --predictions results.jsonl \
  --output eval_results.json \
  --max-items 10
```

### 6. 结果可视化

基于评测结果生成创新性 vs 一致性的分析图表。

```bash
python visualize_results.py
```

### 辅助工具

```bash
# 验证抽取结果的路径链式结构
python scripts/verify_term_flow.py results.jsonl
```

### 完整流程

从批量抽取到评测的端到端流程：

```bash
# Step 1: 批量抽取（支持断点续传）
python run.py batch \
  --input papers.json \
  --output results.jsonl \
  --num-workers 2 --sleep 1 --language-mode chinese --resume

# Step 2: 构建 Benchmark KG
python -m crossdisc_extractor.benchmark.build_dataset \
  --input results.jsonl --output benchmark.json

# Step 3: 评测
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark benchmark.json \
  --predictions results.jsonl \
  --output eval_results.json

# Step 4: 验证数据质量
python scripts/verify_term_flow.py results.jsonl
```

---

## 项目结构

```text
.
├── pyproject.toml                     # 项目打包配置 & 工具链 (ruff/mypy/pytest)
├── Makefile                           # 常用命令入口 (make test/lint/format/ci)
├── requirements.txt                   # 兼容依赖清单 (pip install -r)
├── LICENSE                            # MIT 许可证
├── CHANGELOG.md                       # 版本变更记录
├── run.py                             # CLI 统一入口 (知识抽取)
├── configs/
│   ├── experiment_v1.yaml             # 实验配置模板 (模型/流水线/评测参数)
│   └── default.yaml                   # 统一配置 (分类器 + 抽取器)
├── data/
│   └── msc_converted.json             # 学科分类法 (层级分类体系)
├── crossdisc_extractor/               # 主包
│   ├── __init__.py                    # 版本号 + 公开 API 导出
│   ├── py.typed                       # PEP 561 类型标记
│   ├── config.py                      # 线程安全配置 (PipelineConfig + threading.local)
│   ├── extractor_multi_stage.py       # [核心] 三阶段抽取主程序 (支持断点续传)
│   ├── graph_builder.py               # 知识图谱构建模块 (NetworkX)
│   ├── schemas.py                     # Pydantic 数据模型 (语义链匹配校验)
│   ├── pipeline.py                    # [核心] 统一流水线 (分类→过滤→抽取)
│   ├── classifier/                    # 学科分类子包 (跨学科识别)
│   │   ├── __init__.py                # 公共 API 重新导出
│   │   ├── result.py                  # ClassificationResult 数据类
│   │   ├── config.py                  # 分类器配置 (LLMConfig/ProjectConfig)
│   │   ├── hierarchical.py            # 同步层级分类器
│   │   ├── hierarchical_async.py      # 异步层级分类器
│   │   ├── validator.py               # 选项验证器
│   │   ├── llm/                       # LLM 调用封装 (LangChain)
│   │   ├── taxonomy/                  # 学科分类法加载器
│   │   ├── prompts/                   # 分类 Prompt 模板
│   │   ├── utils/                     # 解析/格式化工具
│   │   └── eval_acc/                  # 分类准确率评估
│   ├── benchmark/
│   │   ├── build_dataset.py           # 数据集构建脚本
│   │   ├── evaluate_benchmark.py      # 自动评测 (中文分词 + MD5 缓存)
│   │   └── eval_prompts.py            # 评测用 Prompt 模板
│   ├── prompts/
│   │   ├── struct_prompt_split.py     # 结构抽取 (概念/关系)
│   │   ├── query_prompt.py            # Query 生成
│   │   └── hypothesis_prompt_split.py # 假设生成
│   └── utils/
│       ├── llm.py                     # LLM 调用封装 (重试/错误处理)
│       ├── parsing.py                 # JSON 解析 (中文标点兼容)
│       ├── pdf_utils.py               # PDF 文本解析
│       └── summarize.py               # 文本摘要工具
├── tests/                             # 单元测试 (114 tests)
│   ├── test_schemas.py                # 数据模型测试 (25 tests)
│   ├── test_parsing.py                # JSON 解析测试 (20 tests)
│   ├── test_config.py                 # 配置管理测试 (8 tests)
│   ├── test_evaluate.py               # 评测模块测试 (17 tests)
│   ├── test_classifier_config.py      # 分类器配置测试 (9 tests)
│   ├── test_classifier_llm.py         # 分类器 LLM 测试 (6 tests)
│   ├── test_classifier_taxonomy.py    # 分类法测试 (11 tests)
│   ├── test_classifier_utils.py       # 分类器工具测试 (12 tests)
│   └── test_classifier_validator.py   # 验证器测试 (6 tests)
├── scripts/
│   ├── verify_term_flow.py            # 路径链式结构验证
│   ├── classify.py                    # 批量学科分类脚本
│   ├── run_demo.py                    # 分类器演示
│   ├── extract_paper.py               # 论文元数据提取
│   ├── extract_introduction.py        # 论文引言提取
│   ├── evaluate_classification.py     # 分类准确率评估
│   ├── sample_dataset.py              # 数据集采样
│   └── merge_data.py                  # 数据合并
├── outputs/                           # 运行输出 (gitignored)
│   └── .gitkeep
├── visualize_results.py               # 评测结果可视化
└── .github/
    └── workflows/
        └── ci.yml                     # GitHub Actions CI (lint + test, Python 3.9-3.12)
```

## 高级配置

### 模型参数调整
通过 CLI 参数调整各阶段的 `max_tokens`，以防止长文本截断：
- `--max-tokens-struct`: 结构抽取阶段 (默认 12000)
- `--max-tokens-query`: Query 生成阶段
- `--max-tokens-hyp`: 假设生成阶段

### 语言模式
通过 `--language-mode` 控制输出语言：
- `chinese`（默认）：强制中文输出
- `original`：保留原文语言

### 断点续传 (Checkpoint/Resume)
批量处理支持基于 MD5 的断点续传机制，仅适用于 `.jsonl` 输出格式：
- `--resume`：开启断点续传，跳过已完成记录
- `--no-resume`：关闭断点续传，强制重新处理

### 线程安全配置
`PipelineConfig` 为不可变冻结数据类，支持多线程环境下的安全配置隔离：
```python
from crossdisc_extractor.config import PipelineConfig

cfg = PipelineConfig(language_mode="chinese", temperature_struct=0.2, seed=42)
cfg.apply_to_thread()  # 仅影响当前线程
```

### YAML 实验配置
使用 `configs/experiment_v1.yaml` 管理可复现的实验参数：
```yaml
model:
  generation_model: "deepseek-v3"
pipeline:
  language_mode: "chinese"
  seed: 42
batch:
  num_workers: 2
  resume: true
```

### 评测维度定制
修改 `benchmark/eval_prompts.py` 中的 `PROMPT_EVAL_L1` 和 `PROMPT_EVAL_DEEP` 可调整 LLM 评分的标准和权重。

---

## 开发指南

### 环境搭建

```bash
# 克隆项目
git clone <repo-url> && cd benchmark

# 安装全部依赖（含开发工具）
pip install -e ".[all]"
```

### 常用命令 (Makefile)

```bash
make help       # 查看所有可用命令
make lint       # 代码风格检查 (ruff)
make format     # 自动格式化代码 (ruff)
make typecheck  # 类型检查 (mypy)
make test       # 运行测试
make test-cov   # 运行测试 + 覆盖率报告
make ci         # 一键运行全部检查 (lint + typecheck + test)
make clean      # 清理构建缓存
make build      # 构建发布包
```

### CI/CD

项目配置了 GitHub Actions，在每次 push/PR 到 main 分支时自动运行：
- **Lint**: ruff 代码检查 + 格式检查
- **Type Check**: mypy 类型检查
- **Test**: 在 Python 3.9/3.10/3.11/3.12 上运行全部测试
- **Coverage**: 生成测试覆盖率报告

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

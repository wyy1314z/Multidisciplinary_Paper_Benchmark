# 保姆级使用指南：跨学科知识抽取与基准评测系统

本指南面向**首次接触本项目的用户**，从零开始带你完成环境配置、各项功能体验到完整端到端流程。
所有命令均可**直接复制到终端运行**。

---

## 目录

- [前置准备](#前置准备)
  - [1. 克隆项目](#1-克隆项目)
  - [2. 创建虚拟环境](#2-创建虚拟环境)
  - [3. 安装依赖](#3-安装依赖)
  - [4. 配置环境变量](#4-配置环境变量)
  - [5. 验证安装](#5-验证安装)
- [功能一：单元测试（验证项目完整性）](#功能一单元测试验证项目完整性)
- [功能二：学科分类 Demo（快速体验分类器）](#功能二学科分类-demo快速体验分类器)
- [功能三：批量学科分类](#功能三批量学科分类)
- [功能四：单篇论文知识抽取](#功能四单篇论文知识抽取)
- [功能五：批量知识抽取](#功能五批量知识抽取)
- [功能六：统一流水线（分类 + 抽取一键完成）](#功能六统一流水线分类--抽取一键完成)
- [功能七：结果导出](#功能七结果导出)
- [功能八：Benchmark 数据集构建](#功能八benchmark-数据集构建)
- [功能九：自动评测](#功能九自动评测)
- [功能十：结果可视化](#功能十结果可视化)
- [功能十一：辅助工具脚本](#功能十一辅助工具脚本)
  - [验证概念流与假设链结构](#1-验证概念流与假设链结构)
  - [提取论文元数据](#2-从-csv-提取论文元数据)
  - [提取论文引言](#3-从-pdf-提取论文引言)
  - [分类准确率评估](#4-分类准确率评估)
  - [数据集采样](#5-数据集采样)
  - [数据合并](#6-数据合并)
- [功能十二：开发相关命令](#功能十二开发相关命令)
- [完整端到端流程](#完整端到端流程)
- [附录：输入数据格式说明](#附录输入数据格式说明)
- [附录：常见问题](#附录常见问题)

---

## 前置准备

### 1. 克隆项目

```bash
git clone <你的仓库地址> benchmark
cd benchmark
```

> 如果你已有项目代码，直接 `cd` 进入项目根目录即可。

### 2. 创建虚拟环境

**强烈建议**使用虚拟环境，避免依赖冲突。

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> 确认 Python 版本 >= 3.9：
> ```bash
> python --version
> ```

### 3. 安装依赖

推荐使用可编辑模式安装（自动注册所有 CLI 入口命令）：

```bash
pip install -e ".[all]"
```

这会安装全部依赖（核心 + PDF 解析 + 可视化 + 开发工具）。

如果只需要核心功能，可以用：

```bash
pip install -e .
```

### 4. 配置环境变量

本项目所有 LLM 调用（知识抽取、学科分类、评测打分）都依赖 OpenAI 兼容接口。

```bash
# 【必填】LLM API 密钥
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 【可选】自定义 API 端点（默认值：http://api.shubiaobiao.cn/v1）
export OPENAI_BASE_URL="https://your-custom-endpoint/v1"

# 【可选】指定模型名称（默认值：deepseek-v3）
export OPENAI_MODEL="deepseek-v3"
```

> **提示**：如果未设置 `OPENAI_API_KEY`，LLM 调用会返回 Mock 随机结果，可用于功能验证但无实际意义。

建议将以上 `export` 命令添加到 `~/.bashrc` 或 `~/.zshrc` 中以便持久化。

### 5. 验证安装

运行以下命令确认安装成功：

```bash
python -c "import crossdisc_extractor; print(crossdisc_extractor.__version__)"
```

应输出版本号（如 `0.2.0`）。

---

## 功能一：单元测试（验证项目完整性）

项目包含 114 个单元测试，**不需要配置 API Key** 就能运行，推荐首先执行以确认项目安装正确。

**运行全部测试：**

```bash
make test
```

或者直接使用 pytest：

```bash
python -m pytest tests/ -v
```

**运行特定模块测试：**

```bash
# 数据模型测试（25 个）
python -m pytest tests/test_schemas.py -v

# JSON 解析测试（20 个）
python -m pytest tests/test_parsing.py -v

# 配置管理测试（8 个）
python -m pytest tests/test_config.py -v

# 评测模块测试（17 个）
python -m pytest tests/test_evaluate.py -v

# 学科分类器测试（44 个）
python -m pytest tests/test_classifier_config.py tests/test_classifier_llm.py tests/test_classifier_taxonomy.py tests/test_classifier_utils.py tests/test_classifier_validator.py -v
```

**运行测试并生成覆盖率报告：**

```bash
make test-cov
```

报告会生成在 `htmlcov/index.html`，可用浏览器打开查看。

---

## 功能二：学科分类 Demo（快速体验分类器）

**这是什么**：对一篇内置的示例论文运行学科分类，输出其所属学科层级和是否为跨学科论文。无需准备任何数据文件。

**前提**：需要配置好 `OPENAI_API_KEY`（或在配置文件中指定 API 信息）。

```bash
mdc-demo --config configs/default.yaml
```

**使用自定义模型：**

```bash
mdc-demo --config configs/default.yaml --model deepseek-v3 --api-base "https://uni-api.cstcloud.cn/v1"
```

**输出示例**：

```
=== Classification Result ===
Valid: True

Raw outputs per level:
  L1: ...
  L2: ...

Final paths:
  Path 1: 数学 → 微分几何 → ...
  Path 2: 物理学 → 理论物理 → ...

Multidisciplinary: Yes
Main discipline: 数学
```

---

## 功能三：批量学科分类

**这是什么**：对一批论文自动进行学科分类，判断每篇是否为跨学科论文，输出 CSV 结果。

**前提**：
- 准备输入文件（JSONL 格式，每行一个 JSON 对象，需包含 `title` 和 `abstract` 字段）
- 配置好 API Key

**第一步：准备输入数据**

创建一个 `papers.jsonl` 文件（每行一个 JSON），格式如下：

```bash
cat > papers.jsonl << 'EOF'
{"title": "Deep Learning for Protein Structure Prediction", "abstract": "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences. Our method combines graph neural networks with attention mechanisms to capture both local and global structural features, achieving state-of-the-art accuracy on CASP14 benchmark."}
{"title": "Quantum Computing Approaches to Drug Discovery", "abstract": "This paper explores the application of variational quantum eigensolver algorithms to molecular simulation for drug discovery. We demonstrate that near-term quantum computers can accelerate the screening of potential drug candidates by efficiently computing molecular ground state energies."}
EOF
```

**第二步：运行分类**

```bash
mdc-classify --input papers.jsonl --output classified.csv --config configs/default.yaml
```

**自定义并发数和模型：**

```bash
mdc-classify --input papers.jsonl --output classified.csv --config configs/default.yaml --model deepseek-v3 --api-base "https://uni-api.cstcloud.cn/v1"
```

**输出**：`classified.csv`，包含 `title, abstract, main_discipline, main_levels, non_main_levels, status` 等列。

---

## 功能四：单篇论文知识抽取

**这是什么**：对一篇论文执行三阶段 LLM 知识抽取：
1. **Stage 1（结构化抽取）**：提取核心概念、实体及语义关系
2. **Stage 2（查询生成）**：生成 L1/L2/L3 三级跨学科探索查询
3. **Stage 3（假设生成）**：生成多层级科学假设与逻辑链

### 最简用法（仅标题 + 摘要）

```bash
python run.py one \
  --title "Deep Learning for Protein Structure Prediction" \
  --abstract "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences. Our method combines graph neural networks with attention mechanisms to capture both local and global structural features."
```

### 指定学科 + 中文输出 + 保存到文件

```bash
python run.py one \
  --title "Deep Learning for Protein Structure Prediction" \
  --abstract "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences. Our method combines graph neural networks with attention mechanisms." \
  --primary "计算机科学技术" \
  --secondary "生物学,数学" \
  --language-mode chinese \
  --output outputs/single_result.json
```

### 完整参数示例（含学科层级 + Token 限制 + 调试输出）

```bash
python run.py one \
  --title "Deep Learning for Protein Structure Prediction" \
  --abstract "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences." \
  --primary "计算机科学技术" \
  --secondary "生物学,数学" \
  --main-levels "L1:计算机科学技术; L2:人工智能; L3:深度学习" \
  --non-main-levels "L1:生物学; L2:生物物理学; L1:数学; L2:应用数学" \
  --language-mode chinese \
  --max-tokens-struct 8192 \
  --max-tokens-query 4096 \
  --max-tokens-hyp 4096 \
  --show-raw \
  --output outputs/single_result.json
```

### 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--title` | 是 | - | 论文标题 |
| `--abstract` | 是 | - | 论文摘要 |
| `--primary` | 否 | `""` | 主学科名称 |
| `--secondary` | 否 | `""` | 辅学科，逗号/分号分隔 |
| `--pdf-url` | 否 | `""` | 论文 PDF 链接（自动抽取引言） |
| `--main-levels` | 否 | `""` | 主学科层级，如 `L1:X; L2:Y` |
| `--non-main-levels` | 否 | `""` | 非主学科层级 |
| `--language-mode` | 否 | `chinese` | 输出语言：`chinese` / `original` |
| `--max-tokens-struct` | 否 | `8192` | Stage 1 最大 token |
| `--max-tokens-query` | 否 | `4096` | Stage 2 最大 token |
| `--max-tokens-hyp` | 否 | `4096` | Stage 3 最大 token |
| `--show-raw` | 否 | 关闭 | 显示模型原始响应（调试用） |
| `--output` | 否 | 无（打印到终端） | 输出文件路径（.json/.jsonl/.csv/.xlsx） |

---

## 功能五：批量知识抽取

**这是什么**：对多篇论文批量运行三阶段知识抽取。支持串行/并行处理和断点续传。

### 准备输入数据

支持 JSON、JSONL、CSV 三种格式。每条数据至少需要 `title` 和 `abstract` 字段。

**JSONL 格式（推荐，支持断点续传）：**

```bash
cat > papers.jsonl << 'EOF'
{"title": "Deep Learning for Protein Structure Prediction", "abstract": "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences.", "primary": "计算机科学技术", "secondary": "生物学,数学"}
{"title": "Quantum Computing Approaches to Drug Discovery", "abstract": "This paper explores the application of variational quantum eigensolver algorithms to molecular simulation for drug discovery.", "primary": "物理学", "secondary": "化学,计算机科学技术"}
EOF
```

### 串行处理（默认，安全稳定）

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl
```

### 并行处理（4 线程 + 每条间隔 1 秒限速）

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --num-workers 4 \
  --sleep 1
```

### 断点续传（程序中断后恢复）

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --resume
```

> `--resume` 默认开启。中断后重新运行同一命令即可自动跳过已完成的记录。仅适用于 `.jsonl` 输出格式。

### 强制重新处理全部

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --no-resume
```

### 抽样处理前 50 条 + 中文输出

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --max-items 50 \
  --language-mode chinese
```

### 完整参数示例

```bash
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --num-workers 2 \
  --sleep 1 \
  --max-items 100 \
  --language-mode chinese \
  --max-tokens-struct 12000 \
  --max-tokens-query 12000 \
  --max-tokens-hyp 12000 \
  --resume
```

### 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` | 是 | - | 输入文件（.json/.jsonl/.csv） |
| `--output` | 是 | - | 输出文件（.json/.jsonl/.csv/.xlsx） |
| `--num-workers` | 否 | `1` | 并行线程数，建议 2-4 |
| `--sleep` | 否 | `0.0` | 每条之间休眠秒数（限速） |
| `--max-items` | 否 | 全部 | 最多处理多少条（用于抽样） |
| `--language-mode` | 否 | `chinese` | 输出语言：`chinese` / `original` |
| `--resume` | 否 | 开启 | 断点续传（仅 .jsonl） |
| `--no-resume` | 否 | - | 关闭断点续传，强制重新处理 |
| `--max-tokens-struct` | 否 | `12000` | Stage 1 最大 token |
| `--max-tokens-query` | 否 | `12000` | Stage 2 最大 token |
| `--max-tokens-hyp` | 否 | `12000` | Stage 3 最大 token |

---

## 功能六：统一流水线（分类 + 抽取一键完成）

**这是什么**：将学科分类与知识抽取整合为单一命令。有三个子命令：
- `full`：完整流程（分类 → 过滤跨学科论文 → 知识抽取）
- `classify`：仅运行分类
- `extract`：仅对已分类数据运行抽取

### 完整流水线（推荐）

```bash
crossdisc-pipeline full \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --config configs/default.yaml
```

### 完整流水线（带全部参数）

```bash
crossdisc-pipeline full \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --config configs/default.yaml \
  --model deepseek-v3 \
  --api-base "https://uni-api.cstcloud.cn/v1" \
  --concurrency 10 \
  --intermediate outputs/classified.jsonl \
  --num-workers 2 \
  --sleep 1 \
  --max-items 50 \
  --language-mode chinese \
  --max-tokens-struct 8192 \
  --max-tokens-query 4096 \
  --max-tokens-hyp 4096 \
  --resume
```

### 仅分类

```bash
crossdisc-pipeline classify \
  --input papers.jsonl \
  --output outputs/classified.jsonl \
  --config configs/default.yaml
```

### 仅抽取（对已分类数据）

```bash
crossdisc-pipeline extract \
  --input outputs/classified.jsonl \
  --output outputs/results.jsonl \
  --num-workers 2 \
  --sleep 1 \
  --language-mode chinese
```

### 参数说明

**分类相关参数**（`classify` 和 `full` 子命令可用）：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` / `-i` | 是 | - | 输入 JSONL 文件 |
| `--output` / `-o` | 是 | - | 输出文件 |
| `--config` | 否 | 无 | YAML 配置文件路径 |
| `--model` | 否 | 配置文件中的值 | LLM 模型名 |
| `--api-base` | 否 | 配置文件中的值 | API 端点 URL |
| `--api-key` | 否 | 环境变量 | API 密钥 |
| `--taxonomy` | 否 | `data/msc_converted.json` | 学科分类法文件 |
| `--concurrency` | 否 | `10` | 异步分类并发数 |

**抽取相关参数**（`extract` 和 `full` 子命令可用）：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--max-items` | 否 | 全部 | 最多处理条数 |
| `--sleep` | 否 | `0.0` | 每条间隔秒数 |
| `--num-workers` | 否 | `1` | 并行线程数 |
| `--language-mode` | 否 | `chinese` | 输出语言 |
| `--max-tokens-struct` | 否 | `8192` | Stage 1 最大 token |
| `--max-tokens-query` | 否 | `4096` | Stage 2 最大 token |
| `--max-tokens-hyp` | 否 | `4096` | Stage 3 最大 token |
| `--resume` / `--no-resume` | 否 | 开启 | 断点续传开关 |

**`full` 子命令专有参数**：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--intermediate` | 否 | `<output>_classified.jsonl` | 中间分类结果文件路径 |

---

## 功能七：结果导出

**这是什么**：将复杂的 JSON 抽取结果转换为易读的 CSV 或简化 JSON，包含学科、各级 Query 和假设摘要。

### 导出为 CSV

```bash
python run.py export \
  --input outputs/results.jsonl \
  --output outputs/summary.csv
```

### 导出为 JSON

```bash
python run.py export \
  --input outputs/results.jsonl \
  --output outputs/summary.json
```

导出的表格包含以下字段：`title`, `primary_discipline`, `secondary_disciplines`, `L1_query`, `L2_queries`, `L3_queries`, `L1_hypotheses`, `L2_hypotheses`, `L3_hypotheses`。

---

## 功能八：Benchmark 数据集构建

**这是什么**：将抽取结果清洗并转换为标准化的 Benchmark 格式，自动构建 Ground Truth 知识图谱。

**前提**：已完成批量抽取，有 `results.jsonl`（或 `.json`）输出文件。

> 注意：`build_dataset.py` 使用 `json.load()` 读取输入，因此需要标准 JSON 数组格式。
> 如果你的结果是 JSONL 格式，先转换为 JSON 数组：
> ```bash
> python -c "
> import json
> with open('outputs/results.jsonl') as f:
>     data = [json.loads(line) for line in f if line.strip()]
> with open('outputs/results.json', 'w') as f:
>     json.dump(data, f, ensure_ascii=False, indent=2)
> "
> ```

**构建 Benchmark：**

```bash
python -m crossdisc_extractor.benchmark.build_dataset \
  --input outputs/results.json \
  --output outputs/benchmark.json
```

---

## 功能九：自动评测

**这是什么**：评估模型预测结果与 Benchmark 的一致性及质量。评测维度包括：
- **创新性 (Innovation)**：假设的新颖程度（0-10 分）
- **可行性 (Feasibility)**：实际可实现性（0-10 分）
- **科学性 (Scientificity)**：科学严谨性（0-10 分）
- **桥接分数 (Bridging Score)**：跨学科知识连接质量
- **路径一致性 (Path Consistency)**：与 Ground Truth 的路径匹配度

**前提**：已完成 Benchmark 构建，有 `benchmark.json` 文件。

### 标准评测

```bash
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark outputs/benchmark.json \
  --predictions outputs/results.jsonl \
  --output outputs/eval_results.json
```

### 快速验证（仅评测前 10 条）

```bash
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark outputs/benchmark.json \
  --predictions outputs/results.jsonl \
  --output outputs/eval_results.json \
  --max-items 10
```

---

## 功能十：结果可视化

**这是什么**：基于评测结果生成「创新性 vs 路径一致性」散点图，按 L1/L2/L3 层级着色。

**前提**：
- 已完成自动评测，有 `eval_results.json` 文件
- 已安装可视化依赖（`pip install -e ".[viz]"` 或 `pip install matplotlib seaborn`）

> 默认读取 `outputs/eval_results_v7.json`，输出到 `outputs/innovation_vs_consistency.png`。
> 如需修改路径，可直接编辑 `visualize_results.py` 末尾的文件名。

```bash
python visualize_results.py
```

生成的图片位于 `outputs/innovation_vs_consistency.png`。

---

## 功能十一：辅助工具脚本

以下工具脚本位于 `scripts/` 目录下。

### 1. 验证概念流与假设链结构

检查抽取结果中的概念池、假设节点和逻辑链是否完整连贯。

```bash
python scripts/verify_term_flow.py outputs/results.json
```

### 2. 从 CSV 提取论文元数据

从 OpenAlex 等来源导出的 CSV 中提取论文元数据并解析 PDF 链接。

**输入 CSV 需包含的列**：`title`, `abstract`, `best_oa_location.pdf_url`, `primary_location.pdf_url`, `best_oa_location.landing_page_url` 等。

```bash
python scripts/extract_paper.py \
  --input raw_papers.csv \
  --output outputs/papers.jsonl
```

**自定义并发数：**

```bash
python scripts/extract_paper.py \
  --input raw_papers.csv \
  --output outputs/papers.jsonl \
  --max-workers 50
```

### 3. 从 PDF 提取论文引言

下载论文 PDF 并使用 LLM 提取引言部分。支持断点续传。

**前提**：输入 JSONL 中每条数据需包含 `pdf_url` 字段。

```bash
python scripts/extract_introduction.py \
  --input outputs/papers.jsonl \
  --output outputs/papers_with_intro.jsonl \
  --config configs/default.yaml
```

**自定义模型和 API：**

```bash
python scripts/extract_introduction.py \
  --input outputs/papers.jsonl \
  --output outputs/papers_with_intro.jsonl \
  --config configs/default.yaml \
  --model deepseek-v3 \
  --api-base "https://uni-api.cstcloud.cn/v1"
```

### 4. 分类准确率评估

对分类结果进行 LLM 评判并计算准确率。分为两步：

**第一步：LLM 评判**

```bash
python scripts/evaluate_classification.py judge \
  --input classified.csv \
  --output outputs/judged_results.jsonl \
  --provider openrouter \
  --model gpt-4o-mini
```

**第二步：计算准确率**

```bash
python scripts/evaluate_classification.py accuracy \
  --input outputs/judged_results.jsonl
```

**输出示例**：

```
Total accuracy:  0.8500
Level 1 accuracy: 0.9200
Level 2 accuracy: 0.8100
Level 3 accuracy: 0.7800
```

### 5. 数据集采样

从大数据集中按比例抽样，用于快速实验。

```bash
python scripts/sample_dataset.py \
  --input papers.jsonl \
  --output outputs/sampled.jsonl \
  --fraction 0.1 \
  --seed 42
```

> `--fraction 0.1` 表示采样 10%。默认值为 `1/300`。

### 6. 数据合并

将多个 Excel/CSV 文件合并为一个 JSONL 文件。

```bash
python scripts/merge_data.py \
  file1.xlsx file2.xlsx file3.csv \
  --output outputs/merged.jsonl
```

---

## 功能十二：开发相关命令

以下命令用于代码质量检查和持续集成，适合参与开发的同学使用。

```bash
# 查看所有可用的 Make 命令
make help

# 代码风格检查（ruff）
make lint

# 自动格式化代码（ruff）
make format

# 类型检查（mypy）
make typecheck

# 一键 CI 检查（lint + typecheck + test）
make ci

# 构建发布包
make build

# 清理构建缓存和临时文件
make clean
```

---

## 完整端到端流程

以下是从原始论文到最终评测可视化的完整工作流程。

### 方式一：使用统一流水线（推荐）

```bash
# Step 1：准备输入数据（示例）
cat > papers.jsonl << 'EOF'
{"title": "Deep Learning for Protein Structure Prediction", "abstract": "We present a novel deep learning approach that predicts protein 3D structures from amino acid sequences. Our method combines graph neural networks with attention mechanisms to capture both local and global structural features, achieving state-of-the-art accuracy on CASP14 benchmark."}
{"title": "Quantum Computing Approaches to Drug Discovery", "abstract": "This paper explores the application of variational quantum eigensolver algorithms to molecular simulation for drug discovery. We demonstrate that near-term quantum computers can accelerate the screening of potential drug candidates by efficiently computing molecular ground state energies."}
EOF

# Step 2：一键执行分类 + 抽取
crossdisc-pipeline full \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --config configs/default.yaml \
  --num-workers 2 \
  --sleep 1 \
  --language-mode chinese \
  --resume

# Step 3：JSONL 转 JSON（Benchmark 构建所需格式）
python -c "
import json
with open('outputs/results.jsonl') as f:
    data = [json.loads(line) for line in f if line.strip()]
with open('outputs/results.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
"

# Step 4：构建 Benchmark 知识图谱
python -m crossdisc_extractor.benchmark.build_dataset \
  --input outputs/results.json \
  --output outputs/benchmark.json

# Step 5：自动评测
python -m crossdisc_extractor.benchmark.evaluate_benchmark \
  --benchmark outputs/benchmark.json \
  --predictions outputs/results.jsonl \
  --output outputs/eval_results.json

# Step 6：验证数据质量
python scripts/verify_term_flow.py outputs/results.json

# Step 7：可视化
python visualize_results.py
```

### 方式二：分步执行

```bash
# Step 1：准备数据（同上）

# Step 2：学科分类
crossdisc-pipeline classify \
  --input papers.jsonl \
  --output outputs/classified.jsonl \
  --config configs/default.yaml

# Step 3：知识抽取
crossdisc-pipeline extract \
  --input outputs/classified.jsonl \
  --output outputs/results.jsonl \
  --num-workers 2 \
  --sleep 1 \
  --language-mode chinese \
  --resume

# Step 4-7：同方式一
```

### 方式三：直接使用 run.py（跳过分类）

适用于已有学科信息、只需进行知识抽取的场景：

```bash
# 批量抽取
python run.py batch \
  --input papers.jsonl \
  --output outputs/results.jsonl \
  --num-workers 2 \
  --sleep 1 \
  --language-mode chinese \
  --resume

# 导出 CSV 便于查看
python run.py export \
  --input outputs/results.jsonl \
  --output outputs/summary.csv
```

---

## 附录：输入数据格式说明

### JSONL 格式（推荐）

每行一个 JSON 对象：

```jsonl
{"title": "论文标题", "abstract": "论文摘要", "primary": "主学科", "secondary": "辅学科1,辅学科2", "pdf_url": "https://example.com/paper.pdf"}
{"title": "另一篇论文", "abstract": "另一篇摘要"}
```

### JSON 格式

标准 JSON 数组：

```json
[
  {"title": "论文标题", "abstract": "论文摘要"},
  {"title": "另一篇论文", "abstract": "另一篇摘要"}
]
```

### CSV 格式

```csv
title,abstract,primary,secondary,pdf_url
论文标题,论文摘要,主学科,"辅学科1,辅学科2",https://example.com/paper.pdf
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `title` | 是 | 论文标题 |
| `abstract` | 是 | 论文摘要 |
| `primary` / `主学科` | 否 | 主学科名称 |
| `secondary` / `辅学科` | 否 | 辅学科（逗号/分号分隔） |
| `pdf_url` | 否 | PDF 链接（用于自动抽取引言） |
| `main_levels` / `主学科层级` | 否 | 如 `L1:数学; L2:代数学` |
| `non_main_levels` / `非主学科层级` | 否 | 如 `L1:物理学; L2:光学` |
| `introduction` | 否 | 论文引言（若已有，可直接提供） |

---

## 附录：常见问题

### Q1：运行时报 `ModuleNotFoundError: No module named 'crossdisc_extractor'`

确保以可编辑模式安装了项目：

```bash
pip install -e .
```

### Q2：`crossdisc-pipeline` 或 `mdc-classify` 命令找不到

CLI 入口需要通过 `pip install -e .` 安装后才能使用。确认已安装且当前虚拟环境已激活。

### Q3：API 调用报错 `401 Unauthorized`

检查环境变量是否正确设置：

```bash
echo $OPENAI_API_KEY
echo $OPENAI_BASE_URL
```

### Q4：批量处理中断了怎么办？

只要输出文件是 `.jsonl` 格式，直接重新运行同一命令即可自动续传（`--resume` 默认开启）。

### Q5：如何调整 LLM 模型？

三种方式（优先级从高到低）：

1. **命令行参数**：`--model deepseek-v3 --api-base "https://..."`
2. **环境变量**：`export OPENAI_MODEL="deepseek-v3"`
3. **配置文件**：修改 `configs/default.yaml` 中的 `model_name` 和 `api_base`

### Q6：想看模型原始输出怎么调试？

单篇抽取时加 `--show-raw`：

```bash
python run.py one --title "..." --abstract "..." --show-raw
```

### Q7：评测分数全是 0 或随机值？

确认已正确设置 `OPENAI_API_KEY`。未设置时，LLM 调用返回 Mock 随机结果。

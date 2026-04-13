# Temporal Run Diagnosis

## Key Findings
- benchmark 候选在分类阶段从 80 降到 37，缩水 43 篇。
- 2025 验证集在分类阶段从 20 降到 11，缩水 9 篇。
- 日志中出现 40 次低于 cross-disc 阈值过滤。
- 日志中出现 12 次单学科过滤。
- 分类层级选择中出现 8 次 'no valid items'，说明模型输出与候选层级不匹配。
- 抽取结果里有 11 条记录出现 primary 落入 secondary_list，跨学科元信息被污染。
- validity 结果中有 11 篇文章只在嵌套 metadata 中保留期刊/影响信号，顶层字段为空。
- query 评测中 L1_relation_precision 全为 0，关系级对齐完全失效。
- query 评测中 L1_path_alignment_best 全为 0，路径对齐指标完全失效。
- query eval 只有 11 条样本，统计解释力偏弱。

## Stage Counts
- `benchmark_raw`: 80
- `benchmark_classified`: 37
- `benchmark_extractions`: 37
- `benchmark_dataset`: 36
- `validity_raw`: 20
- `validity_classified`: 11
- `validity_extractions`: 11
- `validity_result`: 11
- `query_eval`: 11
- `query_results`: 11

## Log Diagnostics
- `non_multidisciplinary_count`: 12
- `below_threshold_count`: 40
- `no_valid_items_count`: 8
- `below_threshold_examples`:
  - A draft human pangenome reference
  - Plasma proteomic associations with genetics and health in th
  - Students’ voices on generative AI: perceptions, benefits, an
  - MIMIC-IV, a freely accessible electronic health record datas
  - Suppressing quantum errors by scaling a surface code logical
  - Heat-related mortality in Europe during the summer of 2022
  - Operando studies reveal active Cu nanograins for CO2 electro
  - JBrowse 2: a modular genome browser with views of synteny an
- `non_multidisciplinary_examples`:
  - {'计算机科学技术'}): Examining Science Education in ChatGPT: An Exploratory Study
  - {'计算机科学技术'}): Artificial intelligence in higher education: the state of th
  - {'计算机科学技术'}): A survey of uncertainty in deep neural networks
  - {'计算机科学技术'}): Visual attention network
  - {'计算机科学技术'}): Generative AI
  - {'计算机科学技术'}): Deep learning modelling techniques: current progress, applic
  - {'计算机科学技术'}): Role of AI chatbots in education: systematic literature revi
  - {'地球科学'}): High-resolution (1 km) Köppen-Geiger maps for 1901–2099 base
- `no_valid_items_examples`:
  - base_path=['社会学'], parsed_items=['妇女问题研究', '社会工作', '社会群体及分层问题研究', '社会问题研究'], raw_output=[妇女问题研究; 社会工作; 社会群体及分层问题研究; 社会问题研究]
  - base_path=['社会学'], parsed_items=['妇女问题研究', '社会工作', '社会问题研究', '社会群体及分层问题研究'], raw_output=[妇女问题研究; 社会工作; 社会问题研究; 社会群体及分层问题研究]
  - base_path=['社会学'], parsed_items=['妇女问题研究', '社会工作', '社会问题研究', '社会群体及分层问题研究'], raw_output=[妇女问题研究; 社会工作; 社会问题研究; 社会群体及分层问题研究]
  - base_path=['环境科学技术'], parsed_items=['环境生态学', '环境地学', '环境管理学', '环境生物学'], raw_output=[环境生态学; 环境地学; 环境管理学; 环境生物学]
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境化学', '环境管理学'], raw_output=[环境生物学; 环境毒理学; 环境化学; 环境管理学]
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境化学', '环境管理学'], raw_output=[环境生物学; 环境毒理学; 环境化学; 环境管理学]
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境化学', '环境地学'], raw_output=[环境生物学; 环境毒理学; 环境化学; 环境地学]
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境管理学', '环境地学'], raw_output=[环境生物学; 环境毒理学; 环境管理学; 环境地学]

## Extraction Diagnostics
### benchmark_extractions
- `total`: 37
- `ok`: 36
- `failed`: 1
- `primary_in_secondary_list_count`: 35
- `primary_in_secondary_list_examples`: ['MitoHiFi: a python pipeline for mitochondrial genome assembly from PacBio high fidelity reads', 'De novo design of protein structure and function with RFdiffusion', 'Accurate medium-range global weather forecasting with 3D neural networks', 'Evaluating the Feasibility of ChatGPT in Healthcare: An Analysis of Multiple Clinical and Research Scenarios', 'A comprehensive AI policy education framework for university teaching and learning', 'Scaling deep learning for materials discovery', 'cGAS–STING drives ageing-related inflammation and neurodegeneration', 'A foundation model for generalizable disease detection from retinal images']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: [{'title': 'Algorithm for optimized mRNA design improves stability and immunogenicity', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}]

### validity_extractions
- `total`: 11
- `ok`: 11
- `failed`: 0
- `primary_in_secondary_list_count`: 11
- `primary_in_secondary_list_examples`: ['A generative model for inorganic materials design', 'The green hydrogen ambition and implementation gap', 'Trust in scientists and their role in society across 68 countries', 'Towards conversational diagnostic artificial intelligence', 'Segment Anything for Microscopy', 'Complexities of the global plastics supply chain revealed in a trade-linked material flow analysis', 'Impacts of climate change on global agriculture accounting for adaptation', 'Functional connectomics spanning multiple areas of mouse visual cortex']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: []

## Validity Diagnostics
- `num_papers`: 11
- `metadata_nested_present_count`: 11
- `metadata_top_level_missing_count`: 11
- `overall_metric_summary`: {'consistency': {'mean': 0.0, 'zero_count': 11, 'non_null_count': 11}, 'concept_f1': {'mean': 0.3704, 'zero_count': 0, 'non_null_count': 11}, 'relation_precision': {'mean': 0.0404, 'zero_count': 9, 'non_null_count': 11}, 'path_alignment_best': {'mean': 0.0, 'zero_count': 11, 'non_null_count': 11}, 'rao_stirling': {'mean': 0.0, 'zero_count': 11, 'non_null_count': 11}, 'innovation': {'mean': 6.9004, 'zero_count': 0, 'non_null_count': 11}, 'scientificity': {'mean': 7.1435, 'zero_count': 0, 'non_null_count': 11}, 'testability': {'mean': 7.0154, 'zero_count': 0, 'non_null_count': 11}}

## Query Evaluation Diagnostics
- `num_rows`: 11
- `parse_error_count`: 1
- `parse_cache_count`: 10
- `model_counts`: {'qwen3-235b-a22b': 11}
- `metric_summary`: {'L1_concept_f1': {'mean': 0.127, 'zero_count': 2, 'non_null_count': 9}, 'L1_relation_precision': {'mean': 0.0, 'zero_count': 9, 'non_null_count': 9}, 'L1_path_alignment_best': {'mean': 0.0, 'zero_count': 9, 'non_null_count': 9}, 'L1_rao_stirling': {'mean': 0.0, 'zero_count': 9, 'non_null_count': 9}, 'L2_concept_f1': {'mean': 0.0824, 'zero_count': 1, 'non_null_count': 10}, 'L2_relation_precision': {'mean': 0.0, 'zero_count': 10, 'non_null_count': 10}, 'L2_path_alignment_best': {'mean': 0.0, 'zero_count': 10, 'non_null_count': 10}, 'L3_concept_f1': {'mean': 0.0466, 'zero_count': 2, 'non_null_count': 10}, 'L3_relation_precision': {'mean': 0.0, 'zero_count': 10, 'non_null_count': 10}, 'L3_path_alignment_best': {'mean': 0.0, 'zero_count': 10, 'non_null_count': 10}, 'L1_factual_precision': {'mean': 1.0, 'zero_count': 0, 'non_null_count': 9}, 'L1_innovation': {'mean': 7.5463, 'zero_count': 0, 'non_null_count': 9}, 'L1_scientificity': {'mean': 8.6667, 'zero_count': 0, 'non_null_count': 9}, 'L1_testability': {'mean': 7.4722, 'zero_count': 0, 'non_null_count': 9}}
- `summary_keys`: ['by_model_method', 'by_model_overall']

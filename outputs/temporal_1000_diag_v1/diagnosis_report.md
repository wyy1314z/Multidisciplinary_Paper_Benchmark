# Temporal Run Diagnosis

## Key Findings
- benchmark 候选在分类阶段从 800 降到 316，缩水 484 篇。
- 2025 验证集在分类阶段从 200 降到 89，缩水 111 篇。
- 日志中出现 510 次低于 cross-disc 阈值过滤。
- 日志中出现 85 次单学科过滤。
- 分类层级选择中出现 31 次 'no valid items'，说明模型输出与候选层级不匹配。
- 抽取结果里有 76 条记录出现 primary 落入 secondary_list，跨学科元信息被污染。
- validity 结果中有 96 篇文章只在嵌套 metadata 中保留期刊/影响信号，顶层字段为空。

## Stage Counts
- `benchmark_raw`: 800
- `benchmark_classified`: 316
- `benchmark_extractions`: 369
- `benchmark_dataset`: 356
- `validity_raw`: 200
- `validity_classified`: 89
- `validity_extractions`: 105
- `validity_result`: 96
- `query_eval`: None
- `query_results`: None

## Log Diagnostics
- `non_multidisciplinary_count`: 85
- `below_threshold_count`: 510
- `no_valid_items_count`: 31
- `below_threshold_examples`:
  - Plasma proteomic associations with genetics and health in th
  - MitoHiFi: a python pipeline for mitochondrial genome assembl
  - A survey of uncertainty in deep neural networks
  - JBrowse 2: a modular genome browser with views of synteny an
  - cGAS–STING drives ageing-related inflammation and neurodegen
  - Operando studies reveal active Cu nanograins for CO2 electro
  - Parameter-efficient fine-tuning of large-scale pre-trained l
  - Lecanemab: Appropriate Use Recommendations
- `non_multidisciplinary_examples`:
  - {'计算机科学技术'}): Examining Science Education in ChatGPT: An Exploratory Study
  - {'计算机科学技术'}): Students’ voices on generative AI: perceptions, benefits, an
  - {'生物学'}): A draft human pangenome reference
  - {'计算机科学技术'}): Artificial intelligence in higher education: the state of th
  - {'计算机科学技术'}): Generative AI
  - {'计算机科学技术'}): Visual attention network
  - {'计算机科学技术'}): Deep learning modelling techniques: current progress, applic
  - {'计算机科学技术'}): Role of AI chatbots in education: systematic literature revi
- `no_valid_items_examples`:
  - base_path=['环境科学技术'], parsed_items=['环境化学', '环境毒理学', '水体环境学', '水污染防治工程'], raw_output=[环境化学; 环境毒理学; 水体环境学; 水污染防治工程]
  - base_path=['环境科学技术'], parsed_items=['环境化学', '环境毒理学', '水污染防治工程', '环境质量监测与评价'], raw_output=[环境化学; 环境毒理学; 水污染防治工程; 环境质量监测与评价]
  - base_path=['环境科学技术'], parsed_items=['环境化学', '环境毒理学', '水污染防治工程', '环境质量监测与评价'], raw_output=[环境化学; 环境毒理学; 水污染防治工程; 环境质量监测与评价]
  - base_path=['环境科学技术'], parsed_items=['环境化学', '环境毒理学', '水体环境学', '水污染防治工程'], raw_output=[环境化学; 环境毒理学; 水体环境学; 水污染防治工程]
  - base_path=['农学'], parsed_items=['农业生态学', '农业微生物学', '作物生理学', '土壤生物学'], raw_output=[农业生态学; 农业微生物学; 作物生理学; 土壤生物学]
  - base_path=['化学'], parsed_items=['配位化学', '有机光化学', '光化学', '高分子光化学'], raw_output=[配位化学; 有机光化学; 光化学; 高分子光化学]
  - base_path=['农学'], parsed_items=['农业生态学', '土壤生态学', '农业系统工程', '农业区划'], raw_output=[农业生态学; 土壤生态学; 农业系统工程; 农业区划]
  - base_path=['临床医学'], parsed_items=['神经外科学', '肿瘤诊断学', '实验诊断学', '外科学其他学科'], raw_output=[神经外科学; 肿瘤诊断学; 实验诊断学; 外科学其他学科]

## Extraction Diagnostics
### benchmark_extractions
- `total`: 369
- `ok`: 356
- `failed`: 13
- `primary_in_secondary_list_count`: 299
- `primary_in_secondary_list_examples`: ['MIMIC-IV, a freely accessible electronic health record dataset', 'De novo design of protein structure and function with RFdiffusion', 'Plasma proteomic associations with genetics and health in the UK Biobank', 'Accurate medium-range global weather forecasting with 3D neural networks', 'A comprehensive AI policy education framework for university teaching and learning', 'Suppressing quantum errors by scaling a surface code logical qubit', 'cGAS–STING drives ageing-related inflammation and neurodegeneration', 'A foundation model for generalizable disease detection from retinal images']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: [{'title': 'Evaluating the Feasibility of ChatGPT in Healthcare: An Analysis of Multiple Clinical and Research Scenarios', 'error': 'unknown_error: 12 validation errors for StructExtraction\n概念.主学科.2.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.主学科.2.source\n  Input should be a valid string [typ'}, {'title': 'Scaling deep learning for materials discovery', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'Spatially informed clustering, integration, and deconvolution of spatial transcriptomics with GraphST', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'Nanocellulose-Assisted Construction of Multifunctional MXene-Based Aerogels with Engineering Biomimetic Texture for Pres', 'error': "unknown_error: 2 validation errors for StructExtraction\n概念.辅学科.化学\n  Input should be a valid list [type=list_type, input_value={'ConceptEntry': [{'term'...act', 'confidence': 0}]}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.11/v/list_type\n概念.辅学科.化学工程\n  Input shou"}, {'title': 'Robust mapping of spatiotemporal trajectories and cell–cell interactions in healthy and diseased tissues', 'error': "unknown_error: 2 validation errors for QueryAndBuckets\n按辅助学科分类.生物学.rationale\n  Field required [type=missing, input_value={'概念': ['伪时间空...验提升研究精度'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.11/v/missing\n按辅助学科分类.计算机科学技术.rationale\n  Field required [type=missing, "}]

### validity_extractions
- `total`: 105
- `ok`: 96
- `failed`: 9
- `primary_in_secondary_list_count`: 76
- `primary_in_secondary_list_examples`: ['Bioaccumulation of microplastics in decedent human brains', 'A generative model for inorganic materials design', 'The green hydrogen ambition and implementation gap', 'Segment Anything for Microscopy', 'Complexities of the global plastics supply chain revealed in a trade-linked material flow analysis', 'Impacts of climate change on global agriculture accounting for adaptation', 'Functional connectomics spanning multiple areas of mouse visual cortex', 'The design space of E(3)-equivariant atom-centred interatomic potentials']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: [{'title': 'Towards conversational diagnostic artificial intelligence', 'error': "unknown_error: 1 validation error for StructExtraction\n跨学科关系.5.direction\n  Input should be '->' [type=literal_error, input_value='<-', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/literal_error"}, {'title': 'Nanoparticles in agriculture: balancing food security and environmental sustainability', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'UAV swarms: research, challenges, and future directions', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'Spatial transcriptomics identifies molecular niche dysregulation associated with distal lung remodeling in pulmonary fib', 'error': "unknown_error: 2 validation errors for StructExtraction\n概念.辅学科.生物学\n  Input should be a valid list [type=list_type, input_value={'主学科': [{'term': '...', 'confidence': 0.88}]}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.11/v/list_type\n概念.辅学科.计算机科学技术\n  Input should"}, {'title': 'Artificial intelligence for individualized treatment of persistent atrial fibrillation: a randomized controlled trial', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}]

## Validity Diagnostics
- `num_papers`: 96
- `metadata_nested_present_count`: 96
- `metadata_top_level_missing_count`: 96
- `overall_metric_summary`: {'consistency': {'mean': 0.0, 'zero_count': 96, 'non_null_count': 96}, 'concept_f1': {'mean': 0.4124, 'zero_count': 0, 'non_null_count': 96}, 'relation_precision': {'mean': 0.0913, 'zero_count': 74, 'non_null_count': 96}, 'path_alignment_best': {'mean': 0.0, 'zero_count': 96, 'non_null_count': 96}, 'rao_stirling': {'mean': 0.0, 'zero_count': 96, 'non_null_count': 96}, 'innovation': {'mean': 3.7903, 'zero_count': 43, 'non_null_count': 96}, 'scientificity': {'mean': 3.9978, 'zero_count': 43, 'non_null_count': 96}, 'testability': {'mean': 3.9633, 'zero_count': 43, 'non_null_count': 96}}

## Query Evaluation Diagnostics

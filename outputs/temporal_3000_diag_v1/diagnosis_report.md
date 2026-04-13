# Temporal Run Diagnosis

## Key Findings
- benchmark 候选在分类阶段从 2400 降到 971，缩水 1429 篇。
- 2025 验证集在分类阶段从 600 降到 274，缩水 326 篇。
- 日志中出现 1447 次低于 cross-disc 阈值过滤。
- 日志中出现 308 次单学科过滤。
- 分类层级选择中出现 141 次 'no valid items'，说明模型输出与候选层级不匹配。
- 抽取结果里有 259 条记录出现 primary 落入 secondary_list，跨学科元信息被污染。
- validity 结果中有 262 篇文章只在嵌套 metadata 中保留期刊/影响信号，顶层字段为空。

## Stage Counts
- `benchmark_raw`: 2400
- `benchmark_classified`: 971
- `benchmark_extractions`: 971
- `benchmark_dataset`: 922
- `validity_raw`: 600
- `validity_classified`: 274
- `validity_extractions`: 274
- `validity_result`: 262
- `query_eval`: None
- `query_results`: None

## Log Diagnostics
- `non_multidisciplinary_count`: 308
- `below_threshold_count`: 1447
- `no_valid_items_count`: 141
- `below_threshold_examples`:
  - MitoHiFi: a python pipeline for mitochondrial genome assembl
  - Plasma proteomic associations with genetics and health in th
  - Students’ voices on generative AI: perceptions, benefits, an
  - A survey of uncertainty in deep neural networks
  - Heat-related mortality in Europe during the summer of 2022
  - Operando studies reveal active Cu nanograins for CO2 electro
  - Lecanemab: Appropriate Use Recommendations
  - Extensive global wetland loss over the past three centuries
- `non_multidisciplinary_examples`:
  - {'生物学'}): A draft human pangenome reference
  - {'计算机科学技术'}): Artificial intelligence in higher education: the state of th
  - {'计算机科学技术'}): Examining Science Education in ChatGPT: An Exploratory Study
  - {'计算机科学技术'}): Visual attention network
  - {'计算机科学技术'}): Generative AI
  - {'计算机科学技术'}): Deep learning modelling techniques: current progress, applic
  - {'计算机科学技术'}): Parameter-efficient fine-tuning of large-scale pre-trained l
  - {'计算机科学技术'}): Role of AI chatbots in education: systematic literature revi
- `no_valid_items_examples`:
  - base_path=['社会学'], parsed_items=['妇女问题研究', '社会工作', '社会问题研究', '社会群体及分层问题研究'], raw_output=[妇女问题研究; 社会工作; 社会问题研究; 社会群体及分层问题研究]
  - base_path=['环境科学技术'], parsed_items=['环境生态学', '环境管理学', '大气环境学', '环境质量监测与评价'], raw_output=[环境生态学; 环境管理学; 大气环境学; 环境质量监测与评价]
  - base_path=['环境科学技术'], parsed_items=['环境生态学', '环境地学', '区域环境学', '环境系统工程'], raw_output=[环境生态学; 环境地学; 区域环境学; 环境系统工程]
  - base_path=['环境科学技术'], parsed_items=['环境生态学', '环境管理学', '大气环境学', '环境质量监测与评价'], raw_output=[环境生态学; 环境管理学; 大气环境学; 环境质量监测与评价]
  - base_path=['环境科学技术'], parsed_items=['水体环境学(包括海洋环境学)', '环境化学', '环境管理学', '环境质量监测与评价'], raw_output=[水体环境学(包括海洋环境学); 环境化学; 环境管理学; 环境质量监测与评价]
  - base_path=['农学'], parsed_items=['农业生态学', '植物营养学', '土壤肥料学', '农业环保工程'], raw_output=[农业生态学; 植物营养学; 土壤肥料学; 农业环保工程]
  - base_path=['环境科学技术'], parsed_items=['环境化学', '环境生物学', '水污染防治工程', '环境质量监测与评价'], raw_output=[环境化学; 环境生物学; 水污染防治工程; 环境质量监测与评价]
  - base_path=['农学'], parsed_items=['农业生态学', '农业气象学与农业气候学', '农业生物化学', '农业系统工程'], raw_output=[农业生态学; 农业气象学与农业气候学; 农业生物化学; 农业系统工程]

## Extraction Diagnostics
### benchmark_extractions
- `total`: 971
- `ok`: 922
- `failed`: 49
- `primary_in_secondary_list_count`: 913
- `primary_in_secondary_list_examples`: ['MIMIC-IV, a freely accessible electronic health record dataset', 'De novo design of protein structure and function with RFdiffusion', 'Accurate medium-range global weather forecasting with 3D neural networks', 'Evaluating the Feasibility of ChatGPT in Healthcare: An Analysis of Multiple Clinical and Research Scenarios', 'A comprehensive AI policy education framework for university teaching and learning', 'Scaling deep learning for materials discovery', 'Suppressing quantum errors by scaling a surface code logical qubit', 'JBrowse 2: a modular genome browser with views of synteny and structural variation']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: [{'title': 'Learning local equivariant representations for large-scale atomistic dynamics', 'error': 'unknown_error: 10 validation errors for StructExtraction\n概念.辅学科.化学.1.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.辅学科.化学.1.source\n  Input should be a valid strin'}, {'title': 'Causal relationship between gut microbiota and cancers: a two-sample Mendelian randomisation study', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'CheckList for EvaluAtion of Radiomics research (CLEAR): a step-by-step reporting guideline for authors and reviewers end', 'error': 'unknown_error: 7 validation errors for StructExtraction\n概念.辅学科.基础医学.3.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.辅学科.基础医学.3.source\n  Input should be a valid st'}, {'title': 'Fusion-based quantum computation', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'Realization of a minimal Kitaev chain in coupled quantum dots', 'error': 'unknown_error: 6 validation errors for StructExtraction\n概念.辅学科.材料科学.3.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.辅学科.材料科学.3.source\n  Input should be a valid st'}]

### validity_extractions
- `total`: 274
- `ok`: 262
- `failed`: 12
- `primary_in_secondary_list_count`: 259
- `primary_in_secondary_list_examples`: ['Bioaccumulation of microplastics in decedent human brains', 'A generative model for inorganic materials design', 'The green hydrogen ambition and implementation gap', 'Trust in scientists and their role in society across 68 countries', 'Towards conversational diagnostic artificial intelligence', 'Segment Anything for Microscopy', 'Complexities of the global plastics supply chain revealed in a trade-linked material flow analysis', 'Impacts of climate change on global agriculture accounting for adaptation']
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: [{'title': 'Integrating the environmental and genetic architectures of aging and mortality', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}, {'title': 'Implementing large language models in healthcare while balancing control, collaboration, costs and security', 'error': "unknown_error: 2 validation errors for StructExtraction\n概念.辅学科.临床医学\n  Input should be a valid list [type=list_type, input_value={'ConceptEntry': [{'term'...', 'confidence': 0.85}]}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.11/v/list_type\n概念.辅学科.管理学\n  Input sho"}, {'title': 'High-Temperature Stealth Across Multi-Infrared and Microwave Bands with Efficient Radiative Thermal Management', 'error': 'unknown_error: 4 validation errors for StructExtraction\n概念.辅学科.材料科学.4.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.辅学科.材料科学.4.source\n  Input should be a valid st'}, {'title': 'Financial inclusion and fintech: a state-of-the-art systematic literature review', 'error': 'unknown_error: 2 validation errors for StructExtraction\n概念.辅学科.计算机科学技术.4.evidence\n  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]\n    For further information visit https://errors.pydantic.dev/2.11/v/string_type\n概念.辅学科.计算机科学技术.4.source\n  Input should be a va'}, {'title': 'Foundation model of neural activity predicts response to new stimulus types', 'error': 'unknown_error: 无法从模型输出中提取合法 JSON 对象'}]

## Validity Diagnostics
- `num_papers`: 262
- `metadata_nested_present_count`: 262
- `metadata_top_level_missing_count`: 262
- `overall_metric_summary`: {'consistency': {'mean': 0.0, 'zero_count': 262, 'non_null_count': 262}, 'concept_f1': {'mean': 0.3908, 'zero_count': 0, 'non_null_count': 262}, 'relation_precision': {'mean': 0.0621, 'zero_count': 209, 'non_null_count': 262}, 'path_alignment_best': {'mean': 0.0, 'zero_count': 262, 'non_null_count': 262}, 'rao_stirling': {'mean': 0.0, 'zero_count': 262, 'non_null_count': 262}, 'innovation': {'mean': 3.9746, 'zero_count': 112, 'non_null_count': 262}, 'scientificity': {'mean': 4.2322, 'zero_count': 112, 'non_null_count': 262}, 'testability': {'mean': 4.1484, 'zero_count': 112, 'non_null_count': 262}}

## Query Evaluation Diagnostics

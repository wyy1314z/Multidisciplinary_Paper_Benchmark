# Temporal Run Diagnosis

## Key Findings
- 分类层级选择中出现 2 次 'no valid items'，说明模型输出与候选层级不匹配。
- validity 结果中有 3 篇文章只在嵌套 metadata 中保留期刊/影响信号，顶层字段为空。

## Stage Counts
- `benchmark_raw`: 3
- `benchmark_classified`: 3
- `benchmark_extractions`: 3
- `benchmark_dataset`: 3
- `validity_raw`: 3
- `validity_classified`: 3
- `validity_extractions`: 3
- `validity_result`: 3
- `query_eval`: 3
- `query_results`: 0

## Log Diagnostics
- `non_multidisciplinary_count`: 0
- `below_threshold_count`: 0
- `no_valid_items_count`: 2
- `no_valid_items_examples`:
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境化学', '环境管理学'], raw_output=[环境生物学; 环境毒理学; 环境化学; 环境管理学]
  - base_path=['环境科学技术'], parsed_items=['环境生物学', '环境毒理学', '环境化学', '环境管理学'], raw_output=[环境生物学; 环境毒理学; 环境化学; 环境管理学]

## Extraction Diagnostics
### benchmark_extractions
- `total`: 3
- `ok`: 3
- `failed`: 0
- `primary_in_secondary_list_count`: 0
- `primary_in_secondary_list_examples`: []
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: []

### validity_extractions
- `total`: 3
- `ok`: 3
- `failed`: 0
- `primary_in_secondary_list_count`: 0
- `primary_in_secondary_list_examples`: []
- `empty_query_count`: 0
- `empty_hypothesis_count`: 0
- `failed_examples`: []

## Validity Diagnostics
- `num_papers`: 3
- `metadata_nested_present_count`: 3
- `metadata_top_level_missing_count`: 3
- `overall_metric_summary`: {'consistency': {'mean': 0.0, 'zero_count': 3, 'non_null_count': 3}, 'concept_f1': {'mean': 0.3628, 'zero_count': 0, 'non_null_count': 3}, 'relation_precision': {'mean': 0.0, 'zero_count': 3, 'non_null_count': 3}, 'path_alignment_best': {'mean': 0.0, 'zero_count': 3, 'non_null_count': 3}, 'rao_stirling': {'mean': 0.0, 'zero_count': 3, 'non_null_count': 3}, 'innovation': {'mean': 2.3333, 'zero_count': 2, 'non_null_count': 3}, 'scientificity': {'mean': 2.5667, 'zero_count': 2, 'non_null_count': 3}, 'testability': {'mean': 2.3403, 'zero_count': 2, 'non_null_count': 3}}

## Query Evaluation Diagnostics
- `num_rows`: 0
- `parse_error_count`: 0
- `parse_cache_count`: 0
- `model_counts`: {}
- `metric_summary`: {'L1_concept_f1': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_relation_precision': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_path_alignment_best': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_rao_stirling': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L2_concept_f1': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L2_relation_precision': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L2_path_alignment_best': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L3_concept_f1': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L3_relation_precision': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L3_path_alignment_best': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_factual_precision': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_innovation': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_scientificity': {'mean': None, 'zero_count': 0, 'non_null_count': 0}, 'L1_testability': {'mean': None, 'zero_count': 0, 'non_null_count': 0}}
- `summary_keys`: ['by_model_method', 'by_model_overall']

# LLM Usage Summary

- `num_records`: 339
- `total_tokens`: 488160
- `prompt_tokens`: 389413
- `completion_tokens`: 98747
- `calls`: 339
- `error_calls`: 210

## By Stage
- `stage1`: calls=32, total_tokens=27530, prompt=26909, completion=621, latency_sum=78.6315s
- `stage2`: calls=21, total_tokens=111202, prompt=60877, completion=50325, latency_sum=1192.8485s
- `stage5`: calls=37, total_tokens=32120, prompt=31345, completion=775, latency_sum=84.2879s
- `stage6`: calls=21, total_tokens=114104, prompt=79786, completion=34318, latency_sum=842.2048s
- `stage7`: calls=213, total_tokens=198474, prompt=185766, completion=12708, latency_sum=367.7564s
- `stage9`: calls=15, total_tokens=4730, prompt=4730, completion=0, latency_sum=4.2692s

## Largest Token Commands
- `stage7::evaluate_benchmark_validity`: total_tokens=198474, prompt=185766, completion=12708, calls=213, latency_sum=367.7564s
- `stage6::extract_validity_candidates`: total_tokens=114104, prompt=79786, completion=34318, calls=21, latency_sum=842.2048s
- `stage2::extract_benchmark_candidates`: total_tokens=111202, prompt=60877, completion=50325, calls=21, latency_sum=1192.8485s
- `stage5::classify_validity_candidates`: total_tokens=32120, prompt=31345, completion=775, calls=37, latency_sum=84.2879s
- `stage1::classify_benchmark_candidates`: total_tokens=27530, prompt=26909, completion=621, calls=32, latency_sum=78.6315s
- `stage9::run_query_benchmark`: total_tokens=4730, prompt=4730, completion=0, calls=15, latency_sum=4.2692s

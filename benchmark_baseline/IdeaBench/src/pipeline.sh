#!/bin/bash

### Code to generate and evaluate research ideas. Please refer to the Research Idea Generation and the Evaluation of the Generated Ideas sections of the main paper for more details. 

# Base path for the project directory
base_path="/ssd/wangyuyang/git/benchmark/benchmark_baseline/IdeaBench/"

# Check if correct conda environment is activated
if [[ "$CONDA_DEFAULT_ENV" != "ideabench_env" ]]; then
    echo "WARNING: You are currently in '$CONDA_DEFAULT_ENV' environment."
    echo "Please run 'conda activate ideabench_env' before running this script."
    echo "Press Ctrl+C to stop, or wait 5 seconds to continue anyway..."
    sleep 5
fi

# SET UP CONFIG HERE:
# Input model you are interested in generating research ideas with here. 
# models=("gemini-1.5-pro" "gpt-4o-mini" "llama3.1-70b") 
models=("gpt-4o-mini") # Modified: Only running GPT-4o-mini to avoid API errors with other providers
all_ref="False" # When True, the LLM inputs all of a target paper's references. Whether they are filtered or not is determined by the filtered_ref variable.
num_hyp=3 # The number of research ideas you want to generate for a given query.
num_ref=3 # The maximum number of a target paper's references you want the LLM to input as background information when generating a research idea. NOTE: This is overrided when all_ref="True" 
filtered_ref="True" # When True, you are using filtered references, otherwise, you using unfiltered references.


# SET UP API KEYS HERE:
# Use environment variable OPENAI_API_KEY if set, otherwise use the default key
default_api_key='sk-4fNRq0tLAmQW7Vaf35D28d714dC54eF68c78427701Aa2959'
open_ai_api_key="${OPENAI_API_KEY:-$default_api_key}"
gemini_api_key="${OPENAI_API_KEY:-$default_api_key}"
llama_api_key="${OPENAI_API_KEY:-$default_api_key}" # NOTE: llama_api_key is aquired through DeepInfra.

# API Proxy Configuration - set OPENAI_API_BASE for custom endpoints
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://uni-api.cstcloud.cn/v1}"


if [ "$filtered_ref" == "True" ] ; then
    ref_file="${base_path}data/dataset/filtered_references.csv"
else
    ref_file="${base_path}data/dataset/raw_references.csv"
fi

# Loop over each model and execute the Python script
for model in "${models[@]}"
do
    if [[ $model =~ ^gpt ]]; then
        api_key=$open_ai_api_key
    elif [[ $model =~ ^gemini ]]; then
        api_key=$gemini_api_key
    else
        api_key=$llama_api_key
    fi
    echo "Running model: $model"
    date '+%A %W %Y %X'
    output_file="${base_path}data/generated_research_ideas/gen_hyp_${model}_all_ref_${all_ref}_filtered_ref_${filtered_ref}_hyp_${num_hyp}_ref_${num_ref}.csv"
    python "${base_path}src/generation/generate_hypotheses.py" --all_ref "$all_ref" --num_ref "$num_ref" --num_hyp "$num_hyp" --model_name "$model" \
    --references "$ref_file" \
    --target_papers "${base_path}data/dataset/target_papers.csv" \
    --output "$output_file" \
    --api_key "$api_key"
    date '+%A %W %Y %X'

    echo "Evaluating model: $model"
    date '+%A %W %Y %X'
    eval_file="${base_path}data/evaluated_research_ideas/eval_hyp_${model}_all_ref_${all_ref}_filtered_ref_${filtered_ref}_hyp_${num_hyp}_ref_${num_ref}.csv"

    python "${base_path}src/evaluation/evaluate_hypotheses.py" --input "$output_file" --output "$eval_file" --openai_api "$open_ai_api_key"
    python "${base_path}src/evaluation/llm_ranking_eval.py" --ranking_criteria novelty --input "$eval_file" --output "$eval_file" --openai_api "$open_ai_api_key"
    python "${base_path}src/evaluation/llm_ranking_eval.py" --ranking_criteria feasibility --input "$eval_file" --output "$eval_file" --openai_api "$open_ai_api_key"
done
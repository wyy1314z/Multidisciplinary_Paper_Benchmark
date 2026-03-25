#!/bin/bash

# Script to run IdeaBench on a single custom paper

# Base path for the project directory
base_path="/ssd/wangyuyang/git/benchmark/benchmark_baseline/IdeaBench/"

# Check environment
if [[ "$CONDA_DEFAULT_ENV" != "ideabench_env" ]]; then
    echo "WARNING: You are currently in '$CONDA_DEFAULT_ENV' environment."
    echo "Please run 'conda activate ideabench_env' before running this script."
    exit 1
fi

# Ask for input if not provided as arguments
paper_title="$1"
if [ -z "$paper_title" ]; then
    echo "Please enter the title of the paper you want to test (or press Enter to provide Paper ID):"
    read -r paper_title
fi

paper_id=""
if [ -z "$paper_title" ]; then
    echo "Please enter the Semantic Scholar Paper ID:"
    read -r paper_id
    if [ -z "$paper_id" ]; then
        echo "Error: You must provide either a Title or a Paper ID."
        exit 1
    fi
fi

# Configuration
# model="gpt-4o-mini"
model="deepseek-v3"
num_hyp=3
# Use environment variable OPENAI_API_KEY if set, otherwise use the default key
default_api_key='sk-4fNRq0tLAmQW7Vaf35D28d714dC54eF68c78427701Aa2959'
open_ai_api_key="${OPENAI_API_KEY:-$default_api_key}"

# API Proxy Configuration
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://uni-api.cstcloud.cn/v1}"
# export https_proxy="http://127.0.0.1:7890"
# export http_proxy="http://127.0.0.1:7890"

# Semantic Scholar API Key (Optional, for higher rate limits)
# export S2_API_KEY="your-api-key-here"

# If OPENAI_API_BASE is set in environment, export it for Python scripts
if [ -n "$OPENAI_API_BASE" ]; then
    export OPENAI_API_BASE
fi

# If S2_API_KEY is set in environment, export it for Python scripts
if [ -n "$S2_API_KEY" ]; then
    export S2_API_KEY
fi

# Define temporary paths
data_dir="${base_path}data/custom_test"
target_file="${data_dir}/target.csv"
raw_refs_file="${data_dir}/raw_refs.csv"
filtered_refs_file="${data_dir}/filtered_refs.csv"
output_gen_file="${data_dir}/generated_ideas.csv"
output_eval_file="${data_dir}/evaluated_ideas.csv"

mkdir -p "$data_dir"

echo "------------------------------------------------"
echo "Step 1: Fetching paper metadata..."
if [ -n "$paper_title" ]; then
    python "${base_path}src/dataset/setup_custom_paper.py" --title "$paper_title" --output "$target_file"
else
    python "${base_path}src/dataset/setup_custom_paper.py" --paper_id "$paper_id" --output "$target_file"
fi

if [ $? -ne 0 ]; then
    echo "Failed to fetch paper."
    exit 1
fi

echo "------------------------------------------------"
echo "Step 2: Retrieving references..."
python "${base_path}src/dataset/retrieve_references.py" --input "$target_file" --output "$raw_refs_file"

echo "------------------------------------------------"
echo "Step 3: Filtering references..."
# Note: We use raw_refs as target_papers output just to satisfy the script args, we don't need to filter the target paper itself heavily for single test
python "${base_path}src/dataset/filter_references.py" \
    --references "$raw_refs_file" \
    --target_papers "$target_file" \
    --references_output "$filtered_refs_file" \
    --target_papers_output "$target_file" # Overwrite is fine here

echo "------------------------------------------------"
echo "Step 4: Generating Hypotheses with $model..."
python "${base_path}src/generation/generate_hypotheses.py" \
    --all_ref "False" \
    --num_ref 5 \
    --num_hyp "$num_hyp" \
    --model_name "$model" \
    --references "$filtered_refs_file" \
    --target_papers "$target_file" \
    --output "$output_gen_file" \
    --api_key "$open_ai_api_key"

echo "------------------------------------------------"
echo "Step 5: Evaluating Hypotheses..."
python "${base_path}src/evaluation/evaluate_hypotheses.py" \
    --input "$output_gen_file" \
    --output "$output_eval_file" \
    --openai_api "$open_ai_api_key"

# Ranking evaluation
python "${base_path}src/evaluation/llm_ranking_eval.py" \
    --ranking_criteria novelty \
    --input "$output_eval_file" \
    --output "$output_eval_file" \
    --openai_api "$open_ai_api_key"

python "${base_path}src/evaluation/llm_ranking_eval.py" \
    --ranking_criteria feasibility \
    --input "$output_eval_file" \
    --output "$output_eval_file" \
    --openai_api "$open_ai_api_key"

echo "------------------------------------------------"
echo "Done! Results saved to:"
echo "Generation: $output_gen_file"
echo "Evaluation: $output_eval_file"

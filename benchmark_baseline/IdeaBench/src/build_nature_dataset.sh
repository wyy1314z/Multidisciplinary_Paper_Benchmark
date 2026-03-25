#!/bin/bash

# Base path for the project directory - Adjust if needed or use PWD
# Assuming running from project root
base_path=$(pwd)/

# Input and Output configurations
input_csv="/ssd/wangyuyang/git/data/raw_data/nature_2025.csv"
output_dir="${base_path}data/dataset/nature_2025"
mkdir -p "$output_dir"

target_papers_file="${output_dir}/target_papers.csv"
raw_refs_file="${output_dir}/raw_references.csv"
filtered_refs_file="${output_dir}/filtered_references.csv"
filtered_target_papers_file="${output_dir}/filtered_target_papers.csv"

# Parse arguments
limit=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --limit) limit="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "========================================================"
echo "Step 1: Processing Nature 2025 CSV to get Target Papers"
echo "========================================================"
if [ -n "$limit" ]; then
    echo "Running with limit: $limit"
    python "${base_path}src/dataset/process_nature_csv.py" \
        --input "$input_csv" \
        --output "$target_papers_file" \
        --limit "$limit"
else
    python "${base_path}src/dataset/process_nature_csv.py" \
        --input "$input_csv" \
        --output "$target_papers_file"
fi

if [ ! -f "$target_papers_file" ]; then
    echo "Error: Target papers file not generated."
    exit 1
fi

echo ""
echo "========================================================"
echo "Step 2: Retrieving References for Target Papers"
echo "========================================================"
# This step calls Semantic Scholar API for each paper, might take time
python "${base_path}src/dataset/retrieve_references.py" \
    --input "$target_papers_file" \
    --output "$raw_refs_file"

if [ ! -f "$raw_refs_file" ]; then
    echo "Error: Raw references file not generated."
    exit 1
fi

echo ""
echo "========================================================"
echo "Step 3: Filtering References (Strict Cleaning)"
echo "========================================================"
python "${base_path}src/dataset/filter_references.py" \
    --references "$raw_refs_file" \
    --target_papers "$target_papers_file" \
    --references_output "$filtered_refs_file" \
    --target_papers_output "$filtered_target_papers_file"

echo ""
echo "========================================================"
echo "Pipeline Completed Successfully!"
echo "Outputs:"
echo "1. Target Papers (Filtered): $filtered_target_papers_file"
echo "2. References (Filtered):    $filtered_refs_file"
echo "========================================================"

import json
import os
import argparse
from typing import List, Dict, Any
from crossdisc_extractor.schemas import Extraction
from crossdisc_extractor.graph_builder import build_graph_and_metrics

def load_extractions(input_path: str) -> List[Dict[str, Any]]:
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    valid_data = []
    for item in data:
        if item.get("ok") and item.get("parsed"):
            valid_data.append(item)
    return valid_data

def convert_to_benchmark_format(item: Dict[str, Any]) -> Dict[str, Any]:
    parsed = item["parsed"]
    try:
        # Re-construct Extraction object to ensure graph is built
        extraction = Extraction(**parsed)
        if not extraction.graph:
            extraction = build_graph_and_metrics(extraction)
        
        # Benchmark Entry Format
        entry = {
            "id": item.get("title", "")[:50], # Simple ID
            "input": {
                "title": extraction.meta.title,
                "primary_discipline": extraction.meta.primary,
                "secondary_disciplines": extraction.meta.secondary_list,
                # Abstract is usually not in parsed meta but in original item
                "abstract": item.get("abstract", "") 
            },
            "ground_truth": {
                "graph": extraction.graph.model_dump() if extraction.graph else None,
                "hypothesis_paths": {
                    "L1": [[p.model_dump() for p in path] for path in extraction.假设.一级],
                    "L2": [[p.model_dump() for p in path] for path in extraction.假设.二级],
                    "L3": [[p.model_dump() for p in path] for path in extraction.假设.三级]
                }
            },
            "metrics": extraction.metrics.model_dump() if extraction.metrics else {}
        }
        return entry
    except Exception as e:
        print(f"Error converting item {item.get('title')}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Build Benchmark Dataset from Extractions")
    parser.add_argument("--input", required=True, help="Input JSON file with extraction results")
    parser.add_argument("--output", required=True, help="Output JSON file for benchmark dataset")
    args = parser.parse_args()

    print(f"Loading data from {args.input}...")
    items = load_extractions(args.input)
    print(f"Found {len(items)} valid items.")

    benchmark_data = []
    for item in items:
        entry = convert_to_benchmark_format(item)
        if entry:
            benchmark_data.append(entry)

    print(f"Converted {len(benchmark_data)} items to benchmark format.")
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)
    print(f"Saved benchmark dataset to {args.output}")

if __name__ == "__main__":
    main()

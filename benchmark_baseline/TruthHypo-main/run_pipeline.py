#!/usr/bin/env python
"""
TruthHypo Benchmark Runner
===========================
Usage modes:

1) MINIMAL / CoT-only (no external knowledge sources needed):
   python run_pipeline.py --mode cot --n_samples 5

2) KG-augmented (requires KG data downloaded):
   python run_pipeline.py --mode kg --n_samples 5 --kg_dir ./LinkHypoGen

3) RAG-augmented (requires PubMed corpus downloaded):
   python run_pipeline.py --mode rag --n_samples 5 --corpus_dir ./corpus

4) RAG+KG (requires both):
   python run_pipeline.py --mode rag_kg --n_samples 5 --kg_dir ./LinkHypoGen --corpus_dir ./corpus

Environment variables:
  OPENAI_API_KEY   - your API key
  OPENAI_BASE_URL  - (optional) custom API endpoint, e.g. https://uni-api.cstcloud.cn/v1
"""

import os
import sys
import json
import re
import argparse
import pandas as pd

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def parse_hypothesis(text):
    """Extract hypothesis from LLM output."""
    try:
        match = re.findall(r'```json\s*({(?:[^`]|\`(?!``))*})', text, re.DOTALL)
        if match:
            return json.loads(match[-1]).get("proposed_hypothesis", text)
    except Exception:
        pass
    return text


def run_cot(args, data):
    from src.agent.cot import CoTAgent
    agent = CoTAgent(model_name=args.model_name)
    results = []
    for idx, row in data.iterrows():
        print(f"[CoT] Sample {idx+1}/{len(data)}: {row['question'][:80]}...")
        outputs = agent.generate_hypothesis(row["question"], temperature=args.temperature, n_hypotheses=args.n_hypotheses)
        for out in outputs:
            hypothesis = parse_hypothesis(out)
            results.append({
                "x_id": row["x_id"],
                "y_id": row["y_id"],
                "relation": row["relation"],
                "question": row["question"],
                "raw_output": out,
                "hypothesis": hypothesis,
            })
    return results


def run_kg(args, data):
    from src.agent.kg import KGAgent
    agent = KGAgent(model_name=args.model_name, load_dir=args.kg_dir)
    results = []
    for idx, row in data.iterrows():
        print(f"[KG] Sample {idx+1}/{len(data)}: {row['question'][:80]}...")
        outputs, nodes, edges = agent.generate_hypothesis(row["question"], temperature=args.temperature, n_hypotheses=args.n_hypotheses)
        for out in outputs:
            hypothesis = parse_hypothesis(out)
            results.append({
                "x_id": row["x_id"],
                "y_id": row["y_id"],
                "relation": row["relation"],
                "question": row["question"],
                "raw_output": out,
                "hypothesis": hypothesis,
            })
    return results


def run_rag(args, data):
    from src.agent.rag import RAGAgent
    agent = RAGAgent(model_name=args.model_name, retriever_name=args.retriever, corpus_name=args.corpus)
    results = []
    for idx, row in data.iterrows():
        print(f"[RAG] Sample {idx+1}/{len(data)}: {row['question'][:80]}...")
        outputs, documents = agent.generate_hypothesis(row["question"], temperature=args.temperature, n_hypotheses=args.n_hypotheses)
        for out in outputs:
            hypothesis = parse_hypothesis(out)
            results.append({
                "x_id": row["x_id"],
                "y_id": row["y_id"],
                "relation": row["relation"],
                "question": row["question"],
                "raw_output": out,
                "hypothesis": hypothesis,
            })
    return results


def run_rag_kg(args, data):
    from src.agent.rag_kg import RAGKGAgent
    agent = RAGKGAgent(model_name=args.model_name, retriever_name=args.retriever, corpus_name=args.corpus, load_dir=args.kg_dir)
    results = []
    for idx, row in data.iterrows():
        print(f"[RAG+KG] Sample {idx+1}/{len(data)}: {row['question'][:80]}...")
        outputs, documents, nodes, edges = agent.generate_hypothesis(row["question"], temperature=args.temperature, n_hypotheses=args.n_hypotheses)
        for out in outputs:
            hypothesis = parse_hypothesis(out)
            results.append({
                "x_id": row["x_id"],
                "y_id": row["y_id"],
                "relation": row["relation"],
                "question": row["question"],
                "raw_output": out,
                "hypothesis": hypothesis,
            })
    return results


def run_verification(args, results):
    """Run KnowHD verification on generated hypotheses."""
    if args.verify == "none":
        return results

    if args.verify == "kg":
        from src.verifier.kg_verifier import KGVerifier
        verifier = KGVerifier(model_name=args.model_name, load_dir=args.kg_dir)
    elif args.verify == "rag":
        from src.verifier.rag_verifier import RAGVerifier
        verifier = RAGVerifier(model_name=args.model_name, retriever_name=args.retriever, corpus_name=args.corpus)
    elif args.verify == "rag_kg":
        from src.verifier.rag_kg_verifier import RAGKGVerifier
        verifier = RAGKGVerifier(model_name=args.model_name, retriever_name=args.retriever, corpus_name=args.corpus, load_dir=args.kg_dir)
    else:
        print(f"Unknown verify mode: {args.verify}, skipping verification")
        return results

    for i, r in enumerate(results):
        print(f"[Verify-{args.verify}] Verifying {i+1}/{len(results)}...")
        claims, groundness, _, _, _ = verifier.verify_claims(r["hypothesis"])
        r["claims"] = claims
        r["groundness"] = groundness
        r["groundness_score"] = sum(groundness) / len(groundness) if groundness else 0.0
    return results


def evaluate(results, data):
    """Compute accuracy: check if the generated hypothesis matches the ground-truth relation."""
    correct = 0
    total = len(results)
    for r in results:
        gt_relation = r["relation"]
        hyp_text = r["hypothesis"].lower()
        # Simple heuristic: check if the ground truth relation keyword appears
        if gt_relation.replace("_", " ") in hyp_text or gt_relation.replace("_", "") in hyp_text:
            correct += 1
            r["match"] = True
        else:
            r["match"] = False
    print(f"\n=== Evaluation ===")
    print(f"Total samples: {total}")
    print(f"Keyword match accuracy: {correct}/{total} = {correct/total:.2%}" if total > 0 else "No samples")
    if any("groundness_score" in r for r in results):
        avg_ground = sum(r.get("groundness_score", 0) for r in results) / total
        print(f"Average groundedness: {avg_ground:.4f}")


def main():
    parser = argparse.ArgumentParser(description="TruthHypo Benchmark Pipeline")
    parser.add_argument("--mode", choices=["cot", "kg", "rag", "rag_kg"], default="cot",
                        help="Hypothesis generation mode")
    parser.add_argument("--verify", choices=["none", "kg", "rag", "rag_kg"], default="none",
                        help="Verification mode (KnowHD)")
    parser.add_argument("--model_name", default="OpenAI/gpt-4o-mini",
                        help="Model name (prefix with OpenAI/ for API models)")
    parser.add_argument("--n_samples", type=int, default=0,
                        help="Number of test samples to run (0 = all)")
    parser.add_argument("--n_hypotheses", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--data_path", default=os.path.join(PROJECT_ROOT, "data", "edges_test.tsv"))
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "results.json"))
    parser.add_argument("--kg_dir", default="./LinkHypoGen",
                        help="Path to KG data (nodes.tsv, edges_train.tsv)")
    parser.add_argument("--corpus_dir", default="./corpus",
                        help="Path to literature corpus")
    parser.add_argument("--retriever", default="BM25",
                        help="Retriever name for RAG modes")
    parser.add_argument("--corpus", default="PubMed",
                        help="Corpus name for RAG modes")
    args = parser.parse_args()

    # Load test data
    print(f"Loading data from {args.data_path}...")
    data = pd.read_csv(args.data_path, sep='\t')
    if args.n_samples > 0:
        data = data.head(args.n_samples)
    print(f"Running on {len(data)} samples")

    # Hypothesis generation
    mode_fn = {"cot": run_cot, "kg": run_kg, "rag": run_rag, "rag_kg": run_rag_kg}
    results = mode_fn[args.mode](args, data)

    # Verification
    results = run_verification(args, results)

    # Evaluation
    evaluate(results, data)

    # Save
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()

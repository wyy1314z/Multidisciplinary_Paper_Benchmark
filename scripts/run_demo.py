"""Demo script: classify a single paper and print results."""

import argparse
import logging
import sys

from crossdisc_extractor.classifier.config import load_config
from crossdisc_extractor.classifier.taxonomy.loader import Taxonomy
from crossdisc_extractor.classifier.prompts.msc_prompt_builder import DisciplinePromptBuilder
from crossdisc_extractor.classifier.hierarchical import SyncHierarchicalClassifier
from crossdisc_extractor.classifier.utils.formatting import format_multiple_paths
from crossdisc_extractor.classifier.utils.parsing import extract_multidisciplinary, extract_main_discipline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


SAMPLE_PAPER = {
    "title": "Stringy differential geometry, beyond Riemann",
    "abstract": (
        "While the fundamental object in Riemannian geometry is a metric, closed "
        "string theories call for us to put a two-form gauge field and a scalar dilaton "
        "on an equal footing with the metric. Here we propose a novel differential "
        "geometry which treats the three objects in a unified manner, manifests not only "
        "diffeomorphism and one-form gauge symmetry but also O(D, D) T-duality, and "
        "enables us to rewrite the known low energy effective action of them as a single "
        "term. Further, we develop a corresponding vielbein formalism and gauge the "
        "internal symmetry which is given by a direct product of two local Lorentz "
        "groups, SO(1, D-1) times SO(1, D-1). We comment that the notion of cosmological "
        "constant naturally changes."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a demo paper")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--api-base", default=None, help="Override API base URL")
    parser.add_argument("--api-key", default=None, help="Override API key")
    parser.add_argument("--taxonomy", default=None, help="Override taxonomy JSON path")
    args = parser.parse_args()

    cfg = load_config(args.config, model_name=args.model, api_base=args.api_base, api_key=args.api_key)
    taxo_path = args.taxonomy or cfg.taxonomy_path

    taxonomy = Taxonomy.from_json_file(taxo_path)
    prompt_builder = DisciplinePromptBuilder()
    classifier = SyncHierarchicalClassifier(taxonomy, prompt_builder, cfg.llm)

    result = classifier.classify((SAMPLE_PAPER["title"], SAMPLE_PAPER["abstract"]))

    print("\n=== Classification Result ===")
    print(f"Valid: {result.valid}")
    print(f"\nRaw outputs per level:")
    for i, raw in enumerate(result.raw_outputs, start=1):
        print(f"  L{i}: {raw}")

    print(f"\nFinal paths:")
    print(format_multiple_paths(result.paths))

    multi = extract_multidisciplinary(result.raw_outputs)
    print(f"\nMultidisciplinary: {multi}")
    if multi == "Yes":
        main_disc = extract_main_discipline(result.raw_outputs)
        print(f"Main discipline: {main_disc}")


if __name__ == "__main__":
    main()

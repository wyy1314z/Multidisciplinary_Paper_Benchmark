"""Sample a fraction of records from a JSONL dataset."""

import argparse
import logging

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample a fraction of a JSONL dataset")
    parser.add_argument("--input", "-i", required=True, help="Input JSONL file")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    parser.add_argument("--fraction", "-f", type=float, default=1 / 300, help="Sampling fraction (default: 1/300)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    df = pd.read_json(args.input, lines=True)
    logger.info("Original: %d records", len(df))

    df_sampled = df.sample(frac=args.fraction, random_state=args.seed)
    logger.info("Sampled: %d records (fraction=%.6f)", len(df_sampled), args.fraction)

    df_sampled.to_json(args.output, orient="records", lines=True, force_ascii=False)
    logger.info("Saved to %s (actual ratio: %.5f)", args.output, len(df_sampled) / len(df))


if __name__ == "__main__":
    main()

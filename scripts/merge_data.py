"""Merge Excel files into a single JSONL dataset."""

import argparse
import json
import logging

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Excel/CSV files into JSONL")
    parser.add_argument("inputs", nargs="+", help="Input Excel (.xlsx) or CSV files")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    args = parser.parse_args()

    frames = []
    for path in args.inputs:
        if path.endswith(".xlsx"):
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path)
        logger.info("Loaded %d rows from %s", len(df), path)
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    logger.info("Merged total: %d rows", len(merged))

    with open(args.output, "w", encoding="utf-8") as f:
        for _, row in merged.iterrows():
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

    logger.info("Written to %s", args.output)


if __name__ == "__main__":
    main()

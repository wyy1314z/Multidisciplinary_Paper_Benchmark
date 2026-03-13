"""Run LLM-based evaluation on classification results."""

import argparse
import logging
from pathlib import Path

from crossdisc_extractor.classifier.eval_acc.eval import judge_classify_true_or_false, calculate_accuracy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = str(Path(__file__).resolve().parent.parent / "crossdisc_extractor" / "classifier" / "eval_acc" / "math_prompt.txt")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate classification accuracy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sub-command: judge
    judge_parser = subparsers.add_parser("judge", help="Run LLM judge on classification results")
    judge_parser.add_argument("--input", "-i", required=True, help="Input JSONL file")
    judge_parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    judge_parser.add_argument("--prompt", default=_DEFAULT_PROMPT, help="System prompt file")
    judge_parser.add_argument("--provider", default="openrouter", help="LLM provider")
    judge_parser.add_argument("--model", default="gpt-4o-mini", help="Model name")

    # Sub-command: accuracy
    acc_parser = subparsers.add_parser("accuracy", help="Calculate accuracy from judge output")
    acc_parser.add_argument("--input", "-i", required=True, help="Judged JSONL file")

    args = parser.parse_args()

    if args.command == "judge":
        judge_classify_true_or_false(
            args.input, args.output, args.prompt,
            provider=args.provider, model=args.model,
        )
    elif args.command == "accuracy":
        results = calculate_accuracy(args.input)
        print(f"\nTotal accuracy:  {results['total_acc']:.4f}")
        print(f"Level 1 accuracy: {results['level1_acc']:.4f}")
        print(f"Level 2 accuracy: {results['level2_acc']:.4f}")
        print(f"Level 3 accuracy: {results['level3_acc']:.4f}")


if __name__ == "__main__":
    main()

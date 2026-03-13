"""Choice validation against taxonomy constraints."""

from typing import List


class ChoiceValidator:
    """Validates and filters LLM choices against an allowed set."""

    def __init__(self, allowed: List[str], max_k: int = 1) -> None:
        self.allowed = set(allowed)
        self.max_k = max_k

    def validate_one(self, choice: str) -> bool:
        """Check if a single choice is in the allowed set."""
        return choice in self.allowed

    def validate_many(self, choices: List[str]) -> List[str]:
        """Filter choices to valid, deduplicated items up to max_k."""
        seen: set = set()
        out: List[str] = []
        for ch in choices:
            if ch in self.allowed and ch not in seen:
                out.append(ch)
                seen.add(ch)
                if len(out) >= self.max_k:
                    break
        return out

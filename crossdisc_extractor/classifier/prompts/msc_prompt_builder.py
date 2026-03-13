"""Discipline-specific prompt builder for hierarchical classification."""

from typing import Dict, List, Optional

from .base import PromptBuilder

# Kept simple: the classifier calls LLM once per level, so the LLM
# should only output a flat bracketed list of selected option names.
_LEVEL0_INSTRUCTIONS = (
    "You are an expert research classifier. "
    "Your task is to determine ALL relevant top-level (L1) academic disciplines "
    "for a given paper.\n\n"
    "CRITICAL RULES:\n"
    " - You MUST select ALL first-level disciplines that the paper touches upon, "
    "even if one is clearly dominant. Most research papers span 2-3 disciplines.\n"
    " - Output ONLY a single bracketed list of selected discipline NAMES, "
    "exactly as they appear in the option KEYS.\n"
    " - Do NOT use the VALUE descriptions as labels.\n"
    " - Do NOT invent new disciplines or modify labels.\n"
    " - For example, a paper about 'nano-catalysts for drug delivery' would select: "
    "[化学; 材料科学; 临床医学]\n"
    " - A paper about 'machine learning for protein folding' would select: "
    "[计算机科学技术; 生物学]\n\n"
    "OUTPUT FORMAT:\n"
    " - Output exactly one line: [option1; option2; option3]\n"
    " - Use semicolons to separate items.\n"
    " - Example: [化学; 材料科学; 临床医学]\n"
    " - Example: [计算机科学技术]\n"
)

_DEEPER_LEVEL_INSTRUCTIONS = (
    "You are an expert research classifier. "
    "Your task is to select the most relevant sub-discipline(s) "
    "for a given paper within a specific parent discipline.\n\n"
    "CRITICAL RULES:\n"
    " - Output ONLY a single bracketed list of selected discipline NAMES, "
    "exactly as they appear in the option KEYS.\n"
    " - Do NOT use the VALUE descriptions as labels.\n"
    " - Do NOT invent new disciplines or modify labels.\n\n"
    "OUTPUT FORMAT:\n"
    " - Output exactly one line: [option1; option2]\n"
    " - Use semicolons to separate items.\n"
    " - Example: [物理化学; 有机化学]\n"
)


class DisciplinePromptBuilder(PromptBuilder):
    """Builds prompts for academic discipline classification."""

    def build_level_prompt(
        self,
        title: str,
        abstract: str,
        level_index: int,
        parent_path: List[str],
        options: List[str],
        options_exp: Dict[str, str],
        max_choices: int,
        introduction: Optional[str] = None,
    ) -> str:
        level_num = level_index + 1
        parent_str = "/".join(parent_path) if parent_path else "(root)"
        final_options = {key: options_exp.get(key, "") for key in options}

        intro_block = ""
        if introduction:
            intro_block = f"Introduction:\n{introduction}\n\n"

        if level_index == 0:
            instructions = _LEVEL0_INSTRUCTIONS
        else:
            instructions = _DEEPER_LEVEL_INSTRUCTIONS

        return (
            f"{instructions}\n"
            f"Task: Select up to {max_choices} Level-{level_num} discipline labels "
            f"for the paper under parent path: {parent_str}.\n"
            f"Paper title:\n{title}\n\n"
            f"Abstract:\n{abstract}\n\n"
            f"{intro_block}"
            f"Valid discipline options (choose 1..{max_choices}):\n{final_options}\n\n"
            f"K = {max_choices}. Output a single bracketed list of your selected options.\n"
        )

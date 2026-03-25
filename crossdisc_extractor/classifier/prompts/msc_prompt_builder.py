"""Discipline-specific prompt builder for hierarchical classification."""

from typing import Dict, List, Optional

from .base import PromptBuilder

# Kept simple: the classifier calls LLM once per level, so the LLM
# should only output a flat bracketed list of selected option names.
_LEVEL0_INSTRUCTIONS = (
    "You are an expert research classifier. "
    "Your task is to identify the core top-level (L1) academic disciplines "
    "for a given paper.\n\n"
    "CRITICAL RULES:\n"
    " - Only select disciplines that are SUBSTANTIALLY involved in the paper's "
    "core methodology, theory, or subject matter.\n"
    " - Do NOT select a discipline merely because the paper's application domain "
    "is loosely related to it. For example, a chemistry paper that happens to "
    "mention a biological application should NOT automatically include 生物学.\n"
    " - Closely related disciplines (e.g. 化学 vs 材料科学 vs 化学工程, or "
    "生物学 vs 基础医学 vs 临床医学) should only BOTH be selected if the paper "
    "genuinely draws on distinct theories/methods from each.\n"
    " - It is perfectly valid to select only ONE discipline if the paper is "
    "primarily within a single field.\n"
    " - Output ONLY a single bracketed list of selected discipline NAMES, "
    "exactly as they appear in the option KEYS.\n"
    " - Do NOT use the VALUE descriptions as labels.\n"
    " - Do NOT invent new disciplines or modify labels.\n\n"
    "OUTPUT FORMAT:\n"
    " - Output exactly one line: [option1; option2]\n"
    " - Use semicolons to separate items.\n"
    " - Example (single discipline): [化学]\n"
    " - Example (cross-disciplinary): [计算机科学技术; 生物学]\n"
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


_CROSSDISC_CONFIDENCE_INSTRUCTIONS = (
    "You are an expert research classifier. "
    "Given a paper and its classified discipline paths, assess whether the paper is "
    "genuinely cross-disciplinary.\n\n"
    "A paper is genuinely cross-disciplinary when:\n"
    " - It integrates theories, methods, or frameworks from MULTIPLE DISTINCT fields\n"
    " - The contribution cannot be fully understood within a single discipline\n"
    " - There is substantial intellectual synthesis across field boundaries\n\n"
    "A paper is NOT genuinely cross-disciplinary when:\n"
    " - It belongs to one discipline but uses a standard tool from another "
    "(e.g. a biology paper using routine statistical analysis is not cross-disciplinary "
    "with mathematics)\n"
    " - It touches on a neighboring sub-field within the same broad area "
    "(e.g. organic chemistry and materials chemistry)\n"
    " - The connection to a secondary discipline is superficial or purely applicational\n\n"
    "OUTPUT FORMAT (strict JSON, one line):\n"
    '  {"score": <float 0.0-1.0>, "reason": "<brief explanation>"}\n\n'
    "Score guidelines:\n"
    " - 0.0-0.3: Not cross-disciplinary (single field, or superficial overlap)\n"
    " - 0.3-0.6: Weakly cross-disciplinary (minor methodological borrowing)\n"
    " - 0.6-0.8: Moderately cross-disciplinary (meaningful integration of two fields)\n"
    " - 0.8-1.0: Strongly cross-disciplinary (deep synthesis of multiple fields)\n"
)


class DisciplinePromptBuilder(PromptBuilder):
    """Builds prompts for academic discipline classification."""

    def build_crossdisc_confidence_prompt(
        self,
        title: str,
        abstract: str,
        disciplines: List[str],
        introduction: Optional[str] = None,
    ) -> str:
        """Build a prompt to assess cross-disciplinary confidence."""
        intro_block = ""
        if introduction:
            intro_block = f"Introduction:\n{introduction}\n\n"

        disc_str = ", ".join(disciplines)
        return (
            f"{_CROSSDISC_CONFIDENCE_INSTRUCTIONS}\n"
            f"Paper title:\n{title}\n\n"
            f"Abstract:\n{abstract}\n\n"
            f"{intro_block}"
            f"Classified disciplines: [{disc_str}]\n\n"
            f"Assess the cross-disciplinary confidence score for this paper.\n"
        )

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

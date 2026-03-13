"""LLM abstraction layer."""

import logging
import re
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from crossdisc_extractor.classifier.config import LLMConfig

logger = logging.getLogger(__name__)


class BaseLLM:
    """Minimal LLM wrapper with sync/async invocation and output parsing."""

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self.llm = ChatOpenAI(
            model_name=cfg.model_name,
            openai_api_base=cfg.api_base,
            openai_api_key=cfg.api_key,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )

    def invoke(self, prompt: str) -> str:
        """Synchronous single-turn prompt invocation."""
        try:
            resp = self.llm.invoke([HumanMessage(content=prompt)])
            return (resp.content or "").strip()
        except Exception as e:
            logger.error("LLM invoke failed: %s", e)
            return ""

    async def ainvoke(self, prompt: str) -> str:
        """Asynchronous single-turn prompt invocation."""
        try:
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return (resp.content or "").strip()
        except Exception as e:
            logger.error("LLM async invoke failed: %s", e)
            return ""

    @staticmethod
    def parse_bracket_list(
        text: Optional[str],
        strict_list_regex: str,
        bracket_inner_regex: str,
        term_max_len: int = 128,
    ) -> List[str]:
        """Extract items from a bracketed list in LLM output.

        Supports both strict ``[a, b, c]`` and loose ``[[a];[b];[c]]`` formats.
        Returns deduplicated items clamped to *term_max_len* characters.
        """
        text = (text or "").strip()
        if re.match(strict_list_regex, text):
            inner = text[1:-1]
        else:
            m = re.search(bracket_inner_regex, text)
            inner = m.group(1) if m else ""

        # Split by semicolons or commas (LLM may use either separator)
        raw_items = [s.strip() for s in re.split(r"[;,]", inner) if s and s.strip()]
        items: List[str] = []
        seen: set = set()
        for it in raw_items:
            it = it.replace("[", "").replace("]", "")
            it = re.sub(r"\s+", " ", it).strip()
            if ";" in it or "\n" in it:
                continue
            if len(it) > term_max_len:
                it = it[:term_max_len].rstrip()
            low = it.lower()
            if it and low not in seen:
                seen.add(low)
                items.append(it)
        return items

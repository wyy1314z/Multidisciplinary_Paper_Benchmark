"""
baseline/common.py — 共享数据结构与 adapter 基类。

所有 baseline 都接收统一的 PaperInput，输出统一的 HypothesisOutput，
从而可以在同一评估框架下公平比较。
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
#  统一输入格式
# ---------------------------------------------------------------------------

@dataclass
class PaperInput:
    """一篇论文的标准化输入，所有 baseline 共用。"""
    paper_id: str
    title: str
    abstract: str
    introduction: str = ""
    primary_discipline: str = ""
    secondary_disciplines: List[str] = field(default_factory=list)
    # 可选：已抽取的概念/关系（仅 CrossDisc adapter 使用）
    concepts: Optional[Dict[str, Any]] = None
    relations: Optional[List[Dict[str, Any]]] = None
    queries: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


EXTERNAL_BASELINE_INTRO_MAX_CHARS = 2000


@dataclass(frozen=True)
class ExternalBaselineInput:
    """
    外部 baseline 的最小公平输入视图。

    这层显式屏蔽 concepts / relations / queries 等项目内部结构化字段，
    让外部 baseline 统一只使用论文文本与学科标签。
    """
    title: str
    abstract: str
    introduction: str = ""
    primary_discipline: str = "N/A"
    secondary_disciplines: tuple[str, ...] = ()

    @property
    def secondary_text(self) -> str:
        return ", ".join(self.secondary_disciplines) if self.secondary_disciplines else "N/A"

    @property
    def introduction_text(self) -> str:
        return self.introduction or "N/A"


def _normalize_prompt_text(text: str) -> str:
    """压缩空白，避免长文本 prompt 中出现异常空行或多空格。"""
    return " ".join((text or "").split())


def _truncate_text(text: str, max_chars: int) -> str:
    text = _normalize_prompt_text(text)
    if not text or len(text) <= max_chars:
        return text

    clipped = text[:max_chars].rsplit(" ", 1)[0].strip()
    if not clipped:
        clipped = text[:max_chars].strip()
    return f"{clipped}..."


def get_external_baseline_input(
    paper: PaperInput,
    intro_max_chars: int = EXTERNAL_BASELINE_INTRO_MAX_CHARS,
) -> ExternalBaselineInput:
    """
    返回外部 baseline 允许使用的输入字段。

    白名单:
    - title
    - abstract
    - introduction
    - primary / secondary discipline labels
    """
    secondary = tuple(
        d for d in (_normalize_prompt_text(x) for x in (paper.secondary_disciplines or []))
        if d
    )
    primary = _normalize_prompt_text(paper.primary_discipline) or "N/A"

    return ExternalBaselineInput(
        title=_normalize_prompt_text(paper.title),
        abstract=_normalize_prompt_text(paper.abstract),
        introduction=_truncate_text(paper.introduction, intro_max_chars),
        primary_discipline=primary,
        secondary_disciplines=secondary,
    )


# ---------------------------------------------------------------------------
#  统一输出格式
# ---------------------------------------------------------------------------

@dataclass
class HypothesisPath:
    """一条结构化假设路径（3-step 三元组链）。"""
    steps: List[Dict[str, Any]]  # [{step, head, relation, tail, claim}, ...]
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"steps": self.steps, "summary": self.summary}


@dataclass
class HypothesisOutput:
    """一篇论文对应的假设生成结果。"""
    paper_id: str
    method_name: str
    # 自由文本假设（IdeaBench / Vanilla LLM 风格）
    free_text_hypotheses: List[str] = field(default_factory=list)
    # 结构化路径假设（CrossDisc 风格），按层级
    structured_paths: Dict[str, List[HypothesisPath]] = field(default_factory=dict)
    # 原始 LLM 响应（用于调试）
    raw_responses: List[str] = field(default_factory=list)
    # 生成耗时（秒）
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "method_name": self.method_name,
            "free_text_hypotheses": self.free_text_hypotheses,
            "structured_paths": {
                level: [p.to_dict() for p in paths]
                for level, paths in self.structured_paths.items()
            },
            "raw_responses": self.raw_responses,
            "elapsed_seconds": self.elapsed_seconds,
        }


# ---------------------------------------------------------------------------
#  Adapter 基类
# ---------------------------------------------------------------------------

class BaseHypothesisAdapter(abc.ABC):
    """所有 baseline 的统一接口。"""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Baseline 名称，如 'IdeaBench', 'VanillaLLM', 'CrossDisc'。"""
        ...

    @abc.abstractmethod
    def generate(self, paper: PaperInput, num_hypotheses: int = 3) -> HypothesisOutput:
        """给定论文输入，生成假设。"""
        ...


# ---------------------------------------------------------------------------
#  工具函数
# ---------------------------------------------------------------------------

def save_outputs(outputs: List[HypothesisOutput], path: str):
    data = [o.to_dict() for o in outputs]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_outputs(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

"""
crossdisc_extractor/config.py

修复内容：
1. 使用 threading.local 替换全局可变对象，消除并行处理时的竞争条件
2. 新增不可变 PipelineConfig dataclass，集中管理所有运行时参数
3. 保留原有 set_language_mode / get_language_mode 接口，向后兼容
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LanguageMode(str, Enum):
    CHINESE  = "chinese"
    ORIGINAL = "original"


# ── 线程安全的语言模式存储 ──────────────────────────────────────
# 使用 threading.local：每个线程独立维护自己的语言模式，
# 并行 worker 之间互不干扰。
_thread_local = threading.local()
_DEFAULT_LANGUAGE_MODE = LanguageMode.CHINESE


def set_language_mode(mode: str) -> None:
    """设置当前线程的语言模式（向后兼容接口）。"""
    _thread_local.language_mode = LanguageMode(mode)


def get_language_mode() -> LanguageMode:
    """获取当前线程的语言模式，默认 CHINESE。"""
    return getattr(_thread_local, "language_mode", _DEFAULT_LANGUAGE_MODE)


# ── 不可变 Pipeline 配置 ────────────────────────────────────────
@dataclass(frozen=True)
class PipelineConfig:
    """
    不可变配置对象，线程安全，可在 worker 之间安全传递。
    frozen=True 保证参数在传递过程中不被意外修改。
    """
    language_mode:       str   = "chinese"
    temperature_struct:  float = 0.2
    temperature_query:   float = 0.2
    temperature_hyp:     float = 0.3
    max_tokens_struct:   int   = 8192
    max_tokens_query:    int   = 4096
    max_tokens_hyp:      int   = 4096
    seed:                int   = 42
    # 明确锁定模型版本，保证实验结果可复现
    model_id:            str   = ""   # 留空时由环境变量 OPENAI_MODEL 决定

    def with_overrides(self, **kwargs) -> "PipelineConfig":
        """返回覆盖了指定字段的新配置对象（原对象不变）。"""
        current = {f: getattr(self, f) for f in self.__dataclass_fields__}
        current.update(kwargs)
        return PipelineConfig(**current)

    def apply_to_thread(self) -> None:
        """将本配置中的语言模式写入当前线程的 local 存储。"""
        set_language_mode(self.language_mode)

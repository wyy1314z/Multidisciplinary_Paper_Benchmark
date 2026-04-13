"""Helpers for lightweight LLM usage telemetry."""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Dict, Iterable, Mapping, Optional

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None


_FALSEY = {"0", "false", "no", "off", ""}


def telemetry_enabled() -> bool:
    path = os.environ.get("CROSSDISC_LLM_USAGE_LOG", "").strip()
    return bool(path)


def _get_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) else default


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def estimate_text_tokens(text: str, model: str = "") -> int:
    text = text or ""
    if not text:
        return 0
    if tiktoken is not None:
        try:
            enc = tiktoken.encoding_for_model(model or "gpt-4o-mini")
        except Exception:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                enc = None
        if enc is not None:
            try:
                return len(enc.encode(text))
            except Exception:
                pass

    cjk = sum(1 for ch in text if _is_cjk(ch))
    remainder = "".join(ch for ch in text if not _is_cjk(ch))
    pieces = re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", remainder)
    other = 0
    for piece in pieces:
        if re.fullmatch(r"[A-Za-z0-9_]+", piece):
            other += max(1, math.ceil(len(piece) / 4))
        else:
            other += 1
    return cjk + other


def estimate_messages_tokens(messages: Iterable[Mapping[str, Any]], model: str = "") -> int:
    total = 0
    for msg in messages:
        role = str(msg.get("role", ""))
        content = msg.get("content", "")
        total += estimate_text_tokens(role, model=model)
        if isinstance(content, str):
            total += estimate_text_tokens(content, model=model)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total += estimate_text_tokens(part, model=model)
                elif isinstance(part, Mapping):
                    total += estimate_text_tokens(str(part.get("text", "")), model=model)
    return total


def normalize_usage(usage: Any) -> Optional[Dict[str, int]]:
    if usage is None:
        return None
    data: Dict[str, Any]
    if isinstance(usage, Mapping):
        data = dict(usage)
    else:
        data = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
            if hasattr(usage, key):
                data[key] = getattr(usage, key)
        if not data and hasattr(usage, "model_dump"):
            try:
                dumped = usage.model_dump()
                if isinstance(dumped, Mapping):
                    data = dict(dumped)
            except Exception:
                data = {}
    if not data:
        return None

    prompt = data.get("prompt_tokens", data.get("input_tokens"))
    completion = data.get("completion_tokens", data.get("output_tokens"))
    total = data.get("total_tokens")
    try:
        prompt_i = int(prompt) if prompt is not None else 0
    except Exception:
        prompt_i = 0
    try:
        completion_i = int(completion) if completion is not None else 0
    except Exception:
        completion_i = 0
    try:
        total_i = int(total) if total is not None else prompt_i + completion_i
    except Exception:
        total_i = prompt_i + completion_i
    return {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": total_i or (prompt_i + completion_i),
    }


def extract_langchain_usage(resp: Any) -> Optional[Dict[str, int]]:
    for attr in ("usage_metadata", "response_metadata"):
        meta = getattr(resp, attr, None)
        usage = normalize_usage(meta)
        if usage:
            return usage
        if isinstance(meta, Mapping):
            for key in ("token_usage", "usage"):
                usage = normalize_usage(meta.get(key))
                if usage:
                    return usage
    return None


def log_usage_event(
    *,
    call_kind: str,
    model: str,
    prompt_text: str = "",
    messages: Optional[Iterable[Mapping[str, Any]]] = None,
    output_text: str = "",
    usage: Any = None,
    success: bool = True,
    error: str = "",
    latency_sec: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    path = _get_env("CROSSDISC_LLM_USAGE_LOG")
    if not path:
        return

    normalized = normalize_usage(usage)
    if messages is not None:
        prompt_tokens_est = estimate_messages_tokens(messages, model=model)
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    else:
        prompt_tokens_est = estimate_text_tokens(prompt_text, model=model)
        prompt_chars = len(prompt_text or "")
    completion_tokens_est = estimate_text_tokens(output_text or "", model=model)
    completion_chars = len(output_text or "")

    record: Dict[str, Any] = {
        "ts": round(time.time(), 3),
        "pid": os.getpid(),
        "stage": _get_env("CROSSDISC_STAGE"),
        "command": _get_env("CROSSDISC_COMMAND"),
        "call_kind": call_kind,
        "model": model,
        "success": bool(success),
        "latency_sec": round(float(latency_sec or 0.0), 4),
        "prompt_chars": int(prompt_chars),
        "completion_chars": int(completion_chars),
        "prompt_tokens_est": int(prompt_tokens_est),
        "completion_tokens_est": int(completion_tokens_est),
        "usage_source": "actual" if normalized else "estimate",
        "prompt_tokens": int(normalized["prompt_tokens"]) if normalized else int(prompt_tokens_est),
        "completion_tokens": int(normalized["completion_tokens"]) if normalized else int(completion_tokens_est),
        "total_tokens": int(normalized["total_tokens"]) if normalized else int(prompt_tokens_est + completion_tokens_est),
    }
    if error:
        record["error"] = error[:500]
    if extra:
        record.update(extra)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def env_stream_enabled(default: bool = True) -> bool:
    raw = _get_env("CROSSDISC_LLM_STREAM", "1" if default else "0").lower()
    return raw not in _FALSEY

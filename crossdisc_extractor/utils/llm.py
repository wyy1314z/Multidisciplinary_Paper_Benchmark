# crossdisc_extractor/utils/llm.py
from __future__ import annotations

import os
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import OpenAI, APIStatusError, APITimeoutError

logger = logging.getLogger("crossdisc.llm")

# MODEL_NAME = os.environ.get("OPENAI_MODEL", "deepseek-v3")
MODEL_NAME = os.environ.get("OPENAI_MODEL") or "qwen3-235b-a22b"
BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://api.shubiaobiao.cn/v1")
API_KEY = os.environ.get("OPENAI_API_KEY")

if not API_KEY:
    print("Warning: OPENAI_API_KEY not found. Client will be initialized with dummy key.")
    client = None
else:
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY,
        max_retries=0,  # 把重试权交给 tenacity
    )


class ModelCallError(RuntimeError):
    """通用 LLM 调用相关错误基类"""
    pass


class ModelTransportError(ModelCallError):
    """网络 / 超时 / HTTP 层错误，可通过 tenacity 重试"""
    pass


class ModelOutputError(ModelCallError):
    """模型输出格式或内容结构错误，不适合通过重试解决"""
    pass


def _get_content_from_resp(resp: Any) -> str:
    """
    尽量兼容各种 OpenAI 兼容 API 的返回结构。
    """
    # ChatCompletion-like object
    if hasattr(resp, "choices"):
        choice0 = resp.choices[0]
        message = getattr(choice0, "message", None)
        content = None
        if message is not None:
            content = getattr(message, "content", None)
        else:
            content = getattr(choice0, "text", None)

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    if "text" in part and isinstance(part["text"], dict):
                        val = part["text"].get("value") or part["text"].get("text")
                        if isinstance(val, str):
                            parts.append(val)
                    elif "content" in part and isinstance(part["content"], str):
                        parts.append(part["content"])
            if parts:
                return "".join(parts)

        text_attr = getattr(choice0, "text", None)
        if isinstance(text_attr, str):
            return text_attr

    # dict
    if isinstance(resp, dict):
        if "choices" in resp:
            choices = resp.get("choices") or []
            if choices:
                c0 = choices[0]
                if isinstance(c0, dict):
                    msg = c0.get("message") or {}
                    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                        return msg["content"]
                    if "text" in c0 and isinstance(c0["text"], str):
                        return c0["text"]
        if "content" in resp and isinstance(resp["content"], str):
            return resp["content"]

    # string
    if isinstance(resp, str):
        try:
            obj = json.loads(resp)
        except Exception:
            return resp

        if isinstance(obj, dict):
            if "choices" in obj:
                choices = obj.get("choices") or []
                if choices:
                    c0 = choices[0]
                    if isinstance(c0, dict):
                        msg = c0.get("message") or {}
                        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                            return msg["content"]
                        if "text" in c0 and isinstance(c0["text"], str):
                            return c0["text"]
                return resp
            if "content" in obj and isinstance(obj["content"], str):
                return obj["content"]
            return resp

        return resp

    raise RuntimeError(f"无法从模型返回中提取 content，类型: {type(resp)}, 值: {repr(resp)[:200]}")


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=120),
    retry=retry_if_exception_type(ModelTransportError),
    before_sleep=lambda rs: logger.info(
        "LLM 重试 #%d，等待 %.0fs…", rs.attempt_number, rs.next_action.sleep
    ),
)
def chat_completion_with_retry(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    seed: Optional[int] = None,
    timeout: int = 1500,
    max_tokens: Optional[int] = None,
) -> str:
    """
    通用 ChatCompletion 封装：带网络/超时层面的重试。
    """
    if not API_KEY:
        # Mock Response for testing without API Key
        # Generate random scores to simulate distribution for visualization
        inn = round(random.uniform(5.0, 9.5), 1)
        fea = round(random.uniform(4.0, 9.0), 1)
        sci = round(random.uniform(6.0, 9.5), 1)
        
        return f"""
        {{
            "innovation_score": {inn},
            "feasibility_score": {fea},
            "scientificity_score": {sci},
            "reason": "Mock evaluation with random scores."
        }}
        """

    kwargs: Dict[str, Any] = dict(
        model=MODEL_NAME,
        messages=messages,
        temperature=temperature,
        timeout=timeout,
    )
    if seed is not None:
        kwargs["seed"] = seed

    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)

    # 强制开启 stream=True 以避免 HTTP 524 (Gateway Timeout)
    # 因为很多代理层（如 Cloudflare / Nginx）会在 100s-600s 无数据传输时切断连接。
    # 使用流式传输可以保持连接活跃。
    kwargs["stream"] = True

    try:
        resp = client.chat.completions.create(**kwargs)

        # 处理流式响应
        collected_content = []
        finish_reason = None
        for chunk in resp:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                collected_content.append(choice.delta.content)
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if finish_reason == "length":
            logger.warning(
                "模型输出因 max_tokens 限制被截断 (finish_reason='length')，"
                "当前 max_tokens=%s，建议增大该值",
                kwargs.get("max_tokens", "未设置"),
            )

        return "".join(collected_content)

    except Exception as e:
        # 优化：如果是 524 超时或 APITimeoutError，回退参数通常无效，直接抛出以便重试
        if isinstance(e, APITimeoutError):
            raise ModelTransportError(f"LLM 调用超时 (Client Timeout): {e}")
        if isinstance(e, APIStatusError) and e.status_code == 524:
            raise ModelTransportError(f"LLM 调用超时 (Server 524): {e}")
        # 429 Rate Limit: 读取 Retry-After 并等待后重试
        if isinstance(e, APIStatusError) and e.status_code == 429:
            retry_after = 30
            if hasattr(e, "response") and e.response is not None:
                retry_after = int(e.response.headers.get("Retry-After", 30))
            logger.warning("Rate limited (429), 等待 %ds 后重试…", retry_after)
            time.sleep(retry_after)
            raise ModelTransportError(f"Rate limited, retry after {retry_after}s")
        # 522/554 等其他网关超时，也直接重试
        if isinstance(e, APIStatusError) and e.status_code in (502, 503, 522, 554):
            raise ModelTransportError(f"LLM 网关错误 (HTTP {e.status_code}): {e}")

        # 一些 OpenAI-compatible 服务端可能不支持 max_tokens/seed 等参数。
        # 做一次确定性回退：移除可疑参数再试一次。
        fallback_kwargs = dict(kwargs)
        removed = []
        if "max_tokens" in fallback_kwargs:
            fallback_kwargs.pop("max_tokens", None)
            removed.append("max_tokens")
        if "seed" in fallback_kwargs:
            fallback_kwargs.pop("seed", None)
            removed.append("seed")
        
        # 回退时也保持 stream=True，除非流式本身也是问题（极少见）
        # 但为了保险，如果流式失败，可以尝试关闭流式？不，524 主要是因为非流式太慢。
        # 这里假设回退主要是参数不支持。
        
        if removed:
            try:
                resp = client.chat.completions.create(**fallback_kwargs)
                collected_content = []
                for chunk in resp:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        collected_content.append(delta.content)
                return "".join(collected_content)
            except Exception as e2:
                raise ModelTransportError(f"LLM 调用失败(回退移除 {removed} 后仍失败): {e2}")
        else:
            raise ModelTransportError(f"LLM 调用失败: {e}")

    # 下面的代码在 stream=True 模式下不再需要，因为我们手动聚合了 content
    # try:
    #     content = _get_content_from_resp(resp)
    #     return content
    # except Exception as e:
    #     raise ModelOutputError(f"无法解析 LLM 响应: {e}")

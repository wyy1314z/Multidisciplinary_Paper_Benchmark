"""Unified multi-provider Chat client for evaluation."""

import base64
import logging
import os
import time
from typing import Any, Dict, List, Literal, Optional

import requests

logger = logging.getLogger(__name__)

Provider = Literal["openrouter", "openai", "deepseek"]


class UniChatClient:
    """Multi-provider LLM chat client.

    Supported providers:
        - ``openrouter``: https://openrouter.ai/api/v1/chat/completions
        - ``openai``: https://api.openai.com/v1/chat/completions
        - ``deepseek``: https://uni-api.cstcloud.cn/v1/chat/completions

    Required environment variables:
        - ``OPENROUTER_API_KEY``
        - ``OPENAI_API_KEY``
    """

    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
    DEEPSEEK_API_URL = "https://uni-api.cstcloud.cn/v1/chat/completions"

    MODEL_MAP_OPENROUTER: Dict[str, str] = {
        "deepseek-r1": "deepseek/deepseek-r1",
        "gpt-4o-mini-preview": "openai/gpt-4o-mini-search-preview",
        "gpt-4o-mini": "openai/gpt-4o-mini",
        "gpt-4.5-preview": "openai/gpt-4.5-preview",
        "gpt-o3": "openai/o3",
        "gpt-4.1": "openai/gpt-4.1",
        "gpt-oss-120b-2508": "openai/gpt-oss-120b",
        "gpt-5-chat-2508": "openai/gpt-5-chat",
        "gpt-5-2508": "openai/gpt-5",
    }

    def __init__(self, default_provider: Provider = "openrouter") -> None:
        self.default_provider = default_provider

    @staticmethod
    def _b64_image(path: str, mime: str = "image/png") -> str:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    def _build_messages(
        self,
        content: str,
        image_paths: Optional[List[str]],
        system_instruction: Optional[str],
    ) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if system_instruction:
            msgs.append({"role": "system", "content": system_instruction})
        if image_paths:
            images = [
                {"type": "image_url", "image_url": {"url": self._b64_image(p)}}
                for p in image_paths
            ]
            msgs.append({"role": "user", "content": [{"type": "text", "text": content}] + images})
        else:
            msgs.append({"role": "user", "content": content})
        return msgs

    @staticmethod
    def _post_with_retry(
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        retries: int = 2,
        timeout: int = 30,
        backoff: float = 60.0,
    ) -> Optional[requests.Response]:
        for i in range(retries):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
                r.raise_for_status()
                return r
            except requests.exceptions.RequestException as e:
                if i < retries - 1:
                    logger.warning(
                        "[%s] Request failed (%d/%d): %s, retrying in %.0fs...",
                        url, i + 1, retries, e, backoff,
                    )
                    time.sleep(backoff)
        return None

    def _call_openrouter(self, model_key: str, messages: List[Dict[str, Any]]) -> Optional[str]:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("Missing env: OPENROUTER_API_KEY")
        if model_key not in self.MODEL_MAP_OPENROUTER:
            raise ValueError(f"Unknown OpenRouter model alias: {model_key}")

        payload = {"model": self.MODEL_MAP_OPENROUTER[model_key], "messages": messages}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        resp = self._post_with_retry(self.OPENROUTER_API_URL, headers, payload)
        if not resp:
            return None
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error("[OpenRouter] Parse error: %s | raw: %s", e, str(data)[:200])
            return None

    def _call_openai(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Missing env: OPENAI_API_KEY")

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        resp = self._post_with_retry(self.OPENAI_API_URL, headers, payload)
        if not resp:
            return None
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error("[OpenAI] Parse error: %s | raw: %s", e, str(data)[:200])
            return None

    def _call_deepseek(
        self,
        model_key: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Missing env: OPENAI_API_KEY")

        payload = {
            "model": model_key,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        resp = self._post_with_retry(self.DEEPSEEK_API_URL, headers, payload, timeout=60)
        if not resp:
            return None

        data = resp.json()
        if isinstance(data, dict):
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            if "result" in data:
                return data["result"]
        logger.warning("[DeepSeek] Unrecognized response: %s", str(data)[:200])
        return None

    def chat(
        self,
        content: str,
        *,
        model: str,
        provider: Optional[Provider] = None,
        image_paths: Optional[List[str]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        """Unified chat interface.

        Args:
            content: User message content.
            model: Model identifier (alias for openrouter, raw name for openai/deepseek).
            provider: Provider to use (defaults to ``self.default_provider``).
            image_paths: Optional list of local image paths for multimodal input.
            system_instruction: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
        """
        prov = provider or self.default_provider
        messages = self._build_messages(content, image_paths, system_instruction)

        if prov == "openrouter":
            return self._call_openrouter(model, messages)
        elif prov == "openai":
            return self._call_openai(model, messages, temperature, max_tokens)
        elif prov == "deepseek":
            return self._call_deepseek(model, messages, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {prov}")

"""HTTP request utilities with retry and backoff."""

import logging
import random
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def request_with_retry(
    method,
    url: str,
    max_retries: int = 5,
    backoff_factor: float = 1.5,
    **kwargs,
) -> Optional[requests.Response]:
    """Execute an HTTP request with exponential backoff retry.

    Args:
        method: ``requests.get`` or ``requests.post``.
        url: Target URL.
        max_retries: Maximum number of attempts.
        backoff_factor: Base for exponential backoff.
        **kwargs: Forwarded to the request method.

    Returns:
        The response, or ``None`` if all retries failed.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = method(url, **kwargs)
            if response.status_code >= 500 or response.status_code == 429:
                raise requests.RequestException(f"Server error {response.status_code}")
            return response
        except Exception as e:
            if attempt >= max_retries:
                logger.error("Request failed after %d retries: %s - %s", max_retries, url, e)
                return None
            sleep_time = min(backoff_factor ** attempt, 60.0) + random.uniform(0, 0.5)
            logger.warning(
                "Attempt %d/%d failed, retrying in %.2fs: %s (%s)",
                attempt, max_retries, sleep_time, url, e,
            )
            time.sleep(sleep_time)
    return None

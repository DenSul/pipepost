"""Shared retry utilities for HTTP destinations."""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter


logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying (5xx, timeouts, connection errors)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.RequestError)


http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
    before_sleep=lambda rs: logger.warning(
        "HTTP attempt %d failed: %s — retrying",
        rs.attempt_number,
        rs.outcome.exception() if rs.outcome else "unknown",
    ),
)

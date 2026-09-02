"""Shared Gemini client — retries transient API failures.

The Gemini API fails in three distinct ways that matter here:
  503 UNAVAILABLE      — model overloaded, clears in seconds. Always retry.
  429 RESOURCE_EXHAUSTED with a per-minute quota — clears in ~a minute. Retry.
  429 RESOURCE_EXHAUSTED with a per-day quota — does not clear today. Give up
                         immediately rather than burning minutes on doomed waits.
"""

import logging
import random
import re
import time

from google import genai
from google.genai import errors as genai_errors

from config import GEMINI_API_KEY, GEMINI_MAX_RETRIES, GEMINI_RETRY_MAX_DELAY

logger = logging.getLogger(__name__)

# Overloaded model, rate limit, and transient gateway faults.
RETRYABLE_CODES = {429, 500, 502, 503, 504}


def make_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _error_details(exc: Exception) -> list:
    """Return the error's `details` list, tolerating either shape the SDK uses."""
    details = getattr(exc, "details", None)
    if isinstance(details, list):
        return details
    # Some SDK versions hand back the whole response body instead.
    if isinstance(details, dict):
        return details.get("error", {}).get("details", []) or []
    return []


def _is_daily_quota(exc: Exception) -> bool:
    """True when the 429 is a per-day quota, which no amount of waiting fixes."""
    for item in _error_details(exc):
        if not isinstance(item, dict):
            continue
        if not str(item.get("@type", "")).endswith("QuotaFailure"):
            continue
        for violation in item.get("violations", []) or []:
            if "PerDay" in str(violation.get("quotaId", "")):
                return True
    return False


def _server_delay(exc: Exception) -> float | None:
    """Google's own suggested wait, e.g. retryDelay: '41s'."""
    for item in _error_details(exc):
        if not isinstance(item, dict):
            continue
        if not str(item.get("@type", "")).endswith("RetryInfo"):
            continue
        match = re.fullmatch(r"([\d.]+)s", str(item.get("retryDelay", "")).strip())
        if match:
            return float(match.group(1))
    return None


def _backoff(exc: Exception, attempt: int) -> float:
    """Seconds to wait before attempt N — server's hint if given, else exponential."""
    delay = _server_delay(exc)
    if delay is None:
        delay = 2 ** attempt + random.uniform(0, 1)
    return min(delay, GEMINI_RETRY_MAX_DELAY)


def generate_with_retry(client: genai.Client, model: str, contents, config=None):
    """client.models.generate_content, retried on transient failures."""
    last_exc = None

    for attempt in range(GEMINI_MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except genai_errors.APIError as exc:
            last_exc = exc
            code = getattr(exc, "code", None)

            if code not in RETRYABLE_CODES:
                raise

            if code == 429 and _is_daily_quota(exc):
                logger.error(
                    "Gemini kunlik limit tugadi — ertaga qayta urinib ko'ring "
                    "yoki https://aistudio.google.com da billing yoqing."
                )
                raise

            if attempt == GEMINI_MAX_RETRIES - 1:
                break

            wait = _backoff(exc, attempt)
            logger.warning(
                "Gemini %s — %.1fs kutib qayta urinaman (%d/%d)",
                code, wait, attempt + 1, GEMINI_MAX_RETRIES,
            )
            time.sleep(wait)

    logger.error("Gemini %d urinishdan keyin ham javob bermadi.", GEMINI_MAX_RETRIES)
    raise last_exc

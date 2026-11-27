"""Shared plumbing for the live canvas benchmarks: a patient client and statistics.

Free tiers (Gemini, Groq) cap requests and tokens per minute. A benchmark that
stops at the first 429 measures the quota, not the model; one that lets the SDK
retry silently hides how often it happened. ``PatientChatOpenAI`` waits the time
the provider asks for, counts every retry and the seconds spent waiting, and
gives up at once on daily caps, which no short wait can fix.
"""

from __future__ import annotations

import math
import re
from time import sleep

import openai
from langchain_openai import ChatOpenAI

RETRY_STATS = {"retries": 0, "waited_s": 0.0}
_WAIT = re.compile(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", re.IGNORECASE)
_DAILY = re.compile(r"per day|\bRPD\b|\bTPD\b", re.IGNORECASE)


def retry_wait_seconds(exc: Exception) -> float:
    """Seconds the provider asked to wait, from the header or the message."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        if headers.get("retry-after"):
            return float(headers["retry-after"])
    except (TypeError, ValueError):
        pass
    match = _WAIT.search(str(exc))
    if not match:
        return 10.0
    minutes = int(match.group(1) or 0)
    value = float(match.group(2))
    return minutes * 60 + (value / 1000 if match.group(3).lower() == "ms" else value)


def is_daily_limit(exc: Exception) -> bool:
    return bool(_DAILY.search(str(exc)))


def _wait(exc: Exception) -> None:
    seconds = min(retry_wait_seconds(exc) + 0.5, 90.0)
    RETRY_STATS["retries"] += 1
    RETRY_STATS["waited_s"] += seconds
    sleep(seconds)


class PatientChatOpenAI(ChatOpenAI):
    """ChatOpenAI that waits out per-minute rate limits and counts the waits."""

    max_rate_limit_retries: int = 8

    def _generate(self, *args, **kwargs):
        for attempt in range(self.max_rate_limit_retries + 1):
            try:
                return super()._generate(*args, **kwargs)
            except openai.RateLimitError as exc:
                if attempt == self.max_rate_limit_retries or is_daily_limit(exc):
                    raise
                _wait(exc)
        raise AssertionError("unreachable")

    def _stream(self, *args, **kwargs):
        for attempt in range(self.max_rate_limit_retries + 1):
            started = False
            try:
                for chunk in super()._stream(*args, **kwargs):
                    started = True
                    yield chunk
                return
            except openai.RateLimitError as exc:
                if started or attempt == self.max_rate_limit_retries or is_daily_limit(exc):
                    raise
                _wait(exc)


def build_client(model: str, base_url: str | None, api_key: str, *, max_tokens: int = 1024):
    kwargs = {"model": model, "api_key": api_key, "temperature": 0, "max_retries": 0,
              "timeout": 120, "max_tokens": max_tokens, "stream_usage": True}
    if base_url:
        kwargs["base_url"] = base_url
    return PatientChatOpenAI(**kwargs)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; ``None`` without trials."""
    if total <= 0:
        return None
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return round(max(0.0, centre - margin), 3), round(min(1.0, centre + margin), 3)

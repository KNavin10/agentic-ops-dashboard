"""Small, in-memory helpers for request observability.

This module deliberately keeps only derived request data in memory.  It does
not persist questions, answers, or tool arguments.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any

DAILY_COST_CEILING_USD = float(os.getenv("DAILY_COST_CEILING_USD", "1.00"))
GROQ_INPUT_USD_PER_MILLION = float(os.getenv("GROQ_INPUT_USD_PER_MILLION", "0.15"))
GROQ_OUTPUT_USD_PER_MILLION = float(os.getenv("GROQ_OUTPUT_USD_PER_MILLION", "0.60"))
CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "3600"))


def generate_request_id() -> str:
    """Return a new request identifier."""
    return str(uuid.uuid4())


def hash_question(question: str) -> str:
    """Return the stable SHA-256 digest of a stripped question."""
    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate dollars using the currently configured token rates."""
    return (
        input_tokens / 1_000_000 * GROQ_INPUT_USD_PER_MILLION
        + output_tokens / 1_000_000 * GROQ_OUTPUT_USD_PER_MILLION
    )


def _contains_sensitive_tool(tool_sequence: Iterable[str] | str | None) -> bool:
    if tool_sequence is None:
        return False
    if isinstance(tool_sequence, str):
        tool_sequence = [tool_sequence]
    return any(tool in {"export_report", "email_summary"} for tool in tool_sequence)


class ResponseCache:
    """A small TTL cache for safe, successful responses."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[tuple[str | None, str, bool], tuple[float, Any]] = {}

    @staticmethod
    def key(
        user_id: str | None,
        question_hash: str,
        approve_sensitive: bool,
    ) -> tuple[str | None, str, bool]:
        return user_id, question_hash, bool(approve_sensitive)

    def get(
        self,
        user_id: str | None,
        question_hash: str,
        approve_sensitive: bool = False,
    ) -> Any | None:
        key = self.key(user_id, question_hash, approve_sensitive)
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, response = item
        if self._clock() >= expires_at:
            del self._items[key]
            return None
        return response

    def put(
        self,
        user_id: str | None,
        question_hash: str,
        response: Any,
        *,
        status: str,
        approve_sensitive: bool = False,
        tool_sequence: Iterable[str] | str | None = None,
    ) -> bool:
        """Cache only safe successful responses; return whether it was stored."""
        if (
            status != "ok"
            or approve_sensitive
            or _contains_sensitive_tool(tool_sequence)
        ):
            return False
        self._items[self.key(user_id, question_hash, approve_sensitive)] = (
            self._clock() + CACHE_TTL_SECONDS,
            response,
        )
        return True

    def clear(self) -> None:
        self._items.clear()


# A process-local cache is sufficient for this learning project.
response_cache = ResponseCache()


def get_cached_response(
    user_id: str | None,
    question_hash: str,
    approve_sensitive: bool = False,
) -> Any | None:
    return response_cache.get(user_id, question_hash, approve_sensitive)


def cache_response(
    user_id: str | None,
    question_hash: str,
    response: Any,
    *,
    status: str,
    approve_sensitive: bool = False,
    tool_sequence: Iterable[str] | str | None = None,
) -> bool:
    return response_cache.put(
        user_id,
        question_hash,
        response,
        status=status,
        approve_sensitive=approve_sensitive,
        tool_sequence=tool_sequence,
    )

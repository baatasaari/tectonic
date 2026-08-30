"""Token counting — same lightweight local estimator used across this
platform's other modules instead of `tiktoken` (see Context
Engineering's `SimpleTokenCounter` for the original rationale: no network
dependency for encoding files).
"""
from __future__ import annotations

import re
from typing import Protocol

_WORD_RE = re.compile(r"\S+")


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class SimpleTokenCounter:
    _TOKENS_PER_WORD = 1.3

    def count(self, text: str) -> int:
        words = len(_WORD_RE.findall(text))
        return max(1, round(words * self._TOKENS_PER_WORD)) if text.strip() else 0

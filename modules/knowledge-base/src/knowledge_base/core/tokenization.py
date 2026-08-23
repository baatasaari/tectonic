"""Token counting — same lightweight local estimator used across this
platform's other modules (e.g. Context Engineering's `SimpleTokenCounter`)
instead of `tiktoken`, whose encodings are fetched from a remote blob
store on first use: a network dependency this module's chunking tests
shouldn't carry. Swapping in `tiktoken` means implementing the same
`count` interface.
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

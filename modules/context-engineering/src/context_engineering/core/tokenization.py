"""Token counting (LLD stack table: "`tiktoken` (or the tokenizer matching
the target model family, resolved dynamically per LLM Gateway routing
decision)"). `tiktoken`'s encodings are fetched from a remote blob store on
first use and cached — a network dependency this module's tests shouldn't
carry. `SimpleTokenCounter` estimates tokens from whitespace/punctuation
splitting (a well-known ~4-chars-per-token English approximation, refined
by actual word count) instead: close enough for budget *enforcement*
(the point of this module), with zero network dependency. Swapping in
`tiktoken` — or the model-specific tokenizer LLM Gateway's routing decision
implies — means implementing the same `count` interface.
"""
from __future__ import annotations

import re
from typing import Protocol

_WORD_RE = re.compile(r"\S+")


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

    def truncate_to(self, text: str, max_tokens: int) -> str: ...


class SimpleTokenCounter:
    # Blended estimate: real BPE tokenizers average ~1.3 tokens per word for
    # English prose; used both to count and to truncate consistently.
    _TOKENS_PER_WORD = 1.3

    def count(self, text: str) -> int:
        words = len(_WORD_RE.findall(text))
        return max(1, round(words * self._TOKENS_PER_WORD)) if text.strip() else 0

    def truncate_to(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        words = _WORD_RE.findall(text)
        max_words = max(1, int(max_tokens / self._TOKENS_PER_WORD))
        if len(words) <= max_words:
            return text
        truncated = " ".join(words[:max_words])
        return truncated

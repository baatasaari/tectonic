"""Shared text-similarity helpers for the Semantic Cache.

The LLD names RedisVL (real vector embeddings + ANN search) as the
production choice. This module implements a lightweight local term-
frequency cosine similarity instead — the same "use the LLD's own
lightweight fallback" move Modules 1 and 2 make elsewhere — so semantic
caching works without a network round-trip to an embedding model on every
lookup, and without a hard dependency on a vector-search library this build
can't verify offline. Swapping in real embeddings means implementing
`embed()`/`cosine_similarity()` against RedisVL and leaving the cache
classes that call them unchanged.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed(text: str) -> Counter[str]:
    """A sparse term-frequency vector — deliberately not a real embedding,
    just enough signal to catch near-duplicate prompts."""
    return Counter(_TOKEN_RE.findall(text.lower()))


def cosine_similarity(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def messages_text(messages) -> str:
    return "\n".join(f"{m.role}:{m.content}" for m in messages)

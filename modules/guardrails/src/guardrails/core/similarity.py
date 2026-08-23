"""Term-frequency cosine similarity — same lightweight-fallback approach
used across this platform's other modules (e.g. Agentic RAG's Heuristic
Groundedness Critic), reused here for the Groundedness Checker (LLD:
"shared implementation with Agentic RAG's Groundedness Critic" — see the
module README for why this is a parallel implementation rather than a
literal code share).
"""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> Counter[str]:
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

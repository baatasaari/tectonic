"""Term-frequency cosine similarity — the same lightweight-fallback move
Module 3 makes for semantic caching, applied here as the Primary
Classifier's actual scoring mechanism (LLD stack table: "fine-tuned small
model ... served locally"). This is a legitimate small local classifier for
a bounded, versioned per-tenant taxonomy: score each intent by its closest
labelled example, no external model-serving dependency required for tests
or for a deployment that hasn't trained a real model yet. Swapping in a
real fine-tuned model means implementing the same `score` interface.
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

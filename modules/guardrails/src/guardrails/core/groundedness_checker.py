"""Groundedness Checker (LLD §2 sub-components): assesses whether an
output is supported by provided context, via term-overlap cosine
similarity against `groundedness.threshold`.
"""
from __future__ import annotations

from guardrails.core.similarity import cosine_similarity, tokenize


def score(output_text: str, context: str) -> float:
    return cosine_similarity(tokenize(output_text), tokenize(context))


def is_grounded(output_text: str, context: str, threshold: float) -> bool:
    return score(output_text, context) >= threshold

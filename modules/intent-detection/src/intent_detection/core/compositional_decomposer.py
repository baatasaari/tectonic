"""Compositional Decomposer (LLD §2.2, differentiator: "compositional
intent detection for multi-goal utterances"). Rule-based signal detection —
multiple verb-adjacent clauses joined by a conjunction — triggers LLM
fallback rather than attempting decomposition itself; the actual splitting
into distinct intents happens in the LLM Fallback Handler, which can
reason about the clauses properly. This component's only job is a fast,
explainable "does this look compositional" signal.
"""
from __future__ import annotations

import re

_CONJUNCTION_SPLIT_RE = re.compile(r"\b(?:and|also|as well as|then)\b|[;]", re.IGNORECASE)


class CompositionalDecomposer:
    def has_multi_intent_signal(self, text: str) -> bool:
        clauses = [c.strip() for c in _CONJUNCTION_SPLIT_RE.split(text) if c.strip()]
        # A conjunction alone isn't enough ("fish and chips" is one clause
        # in spirit) — require at least two clauses that each look like
        # their own action (contain more than a couple of words), a cheap
        # proxy for "each clause plausibly carries its own intent."
        substantial_clauses = [c for c in clauses if len(c.split()) >= 2]
        return len(substantial_clauses) >= 2

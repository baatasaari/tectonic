"""Salience Scorer (LLD §2 sub-components) — the module's differentiator:
"not all recent messages are equal." Rule-based scoring against four
signals (numbers, named commitments, explicit "remember this" cues, and
entity density), each contributing a bounded weight, summed and capped
to `[0, 1]`. An optional LLM-based tier is named in the LLD for higher-
value tenants but not implemented here — see the module README.
"""
from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\d")
_COMMITMENT_RE = re.compile(
    r"\b(i will|we will|i'll|we'll|i promise|committ?ed? to|by (monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|\d{1,2}[/-]\d{1,2}))\b",
    re.IGNORECASE,
)
_REMEMBER_RE = re.compile(r"\b(remember this|please remember|note that|important:|don't forget|do not forget)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"\S+")
_CAPITALIZED_RE = re.compile(r"\b[A-Z][a-zA-Z]+\b")

_NUMBER_WEIGHT = 0.25
_COMMITMENT_WEIGHT = 0.4
_REMEMBER_WEIGHT = 0.5
_ENTITY_DENSITY_WEIGHT = 0.3


def score(content: str) -> float:
    if not content.strip():
        return 0.0

    total_score = 0.0
    if _NUMBER_RE.search(content):
        total_score += _NUMBER_WEIGHT
    if _COMMITMENT_RE.search(content):
        total_score += _COMMITMENT_WEIGHT
    if _REMEMBER_RE.search(content):
        total_score += _REMEMBER_WEIGHT

    words = _WORD_RE.findall(content)
    if words:
        # First word of the message is excluded from the capitalisation
        # count so ordinary sentence-initial capitalisation doesn't read
        # as an entity mention.
        capitalized = _CAPITALIZED_RE.findall(" ".join(words[1:]))
        density = len(capitalized) / len(words)
        total_score += min(_ENTITY_DENSITY_WEIGHT, density * _ENTITY_DENSITY_WEIGHT * 3)

    return min(1.0, total_score)

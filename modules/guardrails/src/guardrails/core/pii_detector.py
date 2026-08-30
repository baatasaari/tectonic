"""Presidio PII Detector (LLD §2 sub-components) — deviation from
Microsoft Presidio; see the module README's "Design notes vs. the LLD".
Regex/heuristic detection and redaction for a fixed set of entity types.
"""
from __future__ import annotations

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "PHONE_NUMBER": re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
    "CREDIT_CARD": re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)"),
    "SSN": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    # Heuristic only: two-or-more consecutive capitalised words, not at the
    # very start of a sentence — a coarse stand-in for a real named-entity
    # recognizer, prone to both false positives (proper nouns generally)
    # and false negatives (single-token names).
    "PERSON": re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b"),
}


def detect(text: str, entity_types: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for entity_type in entity_types:
        pattern = _PATTERNS.get(entity_type)
        if pattern is None:
            continue
        matches = pattern.findall(text)
        if matches:
            found[entity_type] = matches
    return found


def detect_and_redact(text: str, entity_types: list[str]) -> tuple[str, list[str]]:
    redacted = text
    entities_found: list[str] = []
    for entity_type in entity_types:
        pattern = _PATTERNS.get(entity_type)
        if pattern is None:
            continue
        if pattern.search(redacted):
            entities_found.append(entity_type)
            redacted = pattern.sub(f"[REDACTED_{entity_type}]", redacted)
    return redacted, entities_found

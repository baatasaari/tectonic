"""Jailbreak/Injection Detector (LLD §2 sub-components) — deviation from
the LLD's "pattern detectors, fine-tuned classifier, and an LLM Gateway
fallback for ambiguous cases" layered defence: the fine-tuned classifier
tier is replaced with a second, weaker pattern tier (see the module
README). Strong patterns are high-confidence matches on well-known
jailbreak phrasing; weak signals are ambiguous and deferred to the LLM
Gateway fallback.
"""
from __future__ import annotations

import re
from enum import StrEnum

_STRONG_PATTERNS = [
    re.compile(r"ignore (all |any |the )?(previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"you are now (DAN|in developer mode|unrestricted)", re.IGNORECASE),
    re.compile(r"disregard (your|the) (system prompt|guidelines|rules)", re.IGNORECASE),
    re.compile(r"pretend (you have|there are) no (restrictions|rules|limits)", re.IGNORECASE),
    re.compile(r"reveal your (system prompt|instructions)", re.IGNORECASE),
]

_WEAK_SIGNALS = [
    re.compile(r"\bignore\b", re.IGNORECASE),
    re.compile(r"\boverride\b", re.IGNORECASE),
    re.compile(r"\bbypass\b", re.IGNORECASE),
    re.compile(r"\bpretend\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bdo anything now\b", re.IGNORECASE),
]


class DetectionResult(StrEnum):
    CLEAN = "clean"
    DETECTED = "detected"
    AMBIGUOUS = "ambiguous"


def detect(text: str) -> DetectionResult:
    if any(p.search(text) for p in _STRONG_PATTERNS):
        return DetectionResult.DETECTED
    if any(p.search(text) for p in _WEAK_SIGNALS):
        return DetectionResult.AMBIGUOUS
    return DetectionResult.CLEAN

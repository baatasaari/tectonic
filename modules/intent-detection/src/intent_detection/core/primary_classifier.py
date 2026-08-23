"""Primary Classifier (LLD §2.2): fast single-pass classification against
the tenant's taxonomy — scores each intent by the input's closest labelled
example, via the term-frequency cosine similarity in similarity.py.
"""
from __future__ import annotations

from intent_detection.core.domain import DetectedIntent, IntentDefinition
from intent_detection.core.similarity import cosine_similarity, tokenize


class PrimaryClassifier:
    def classify(self, text: str, intents: list[IntentDefinition]) -> list[DetectedIntent]:
        """Returns every intent scored, sorted by confidence descending —
        the caller decides how many to keep and whether to fall back."""
        text_vec = tokenize(text)
        scored = []
        for intent in intents:
            if not intent.examples:
                scored.append(DetectedIntent(name=intent.name, confidence=0.0))
                continue
            best = max(cosine_similarity(text_vec, tokenize(example)) for example in intent.examples)
            scored.append(DetectedIntent(name=intent.name, confidence=best))
        scored.sort(key=lambda d: d.confidence, reverse=True)
        return scored

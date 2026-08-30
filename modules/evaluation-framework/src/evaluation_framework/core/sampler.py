"""Production Sampler (LLD §2 sub-components): selects a configurable
percentage of live traffic for continuous evaluation.

**Deviation from the LLD.** The LLD specifies a Kafka consumer sampling
live traffic. This module has no Kafka broker to consume from in this
build (the same Kafka-to-HTTP substitution used elsewhere in this
platform, e.g. Sentinel Agents' event ingestion) — `POST
/v1/evaluation-framework/sample` is the HTTP substitute: an upstream
module posts each interaction here directly, and `ProductionSampler`
still performs the actual sampling decision rather than evaluating
every single call, preserving the LLD's cost-control intent. The
decision is a deterministic hash of `interaction_id` rather than
`random()`, so the same interaction always samples the same way — useful
for reproducing "why was this one evaluated" during debugging.
"""
from __future__ import annotations

import hashlib


class ProductionSampler:
    def __init__(self, sample_rate: float) -> None:
        self._sample_rate = sample_rate

    def should_sample(self, interaction_id: str) -> bool:
        if self._sample_rate <= 0.0:
            return False
        if self._sample_rate >= 1.0:
            return True
        digest = hashlib.sha256(interaction_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        return bucket < self._sample_rate

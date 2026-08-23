"""Drift Monitor (LLD §2.2, differentiator: "intent drift monitoring").
Off the hot path — a scheduled batch job comparing the distribution of
real classification traffic against the taxonomy's trained baseline
(approximated here by each intent's labelled-example share, since this
module doesn't have a separate "training set" artifact). Population
Stability Index is the LLD's suggested statistic; implemented directly
rather than pulling in a stats library for one formula.
"""
from __future__ import annotations

import math

from intent_detection.core.domain import (
    ClassificationLogRecord,
    DriftReportRecord,
    IntentTaxonomyRecord,
    new_id,
)

_EPSILON = 1e-6  # avoids log(0)/div-by-0 for an intent with zero observed or expected share


def _psi(expected: dict[str, float], observed: dict[str, float]) -> float:
    all_intents = set(expected) | set(observed)
    total = 0.0
    for intent in all_intents:
        e = max(expected.get(intent, 0.0), _EPSILON)
        o = max(observed.get(intent, 0.0), _EPSILON)
        total += (o - e) * math.log(o / e)
    return total


def _per_intent_contribution(expected: dict[str, float], observed: dict[str, float]) -> dict[str, float]:
    all_intents = set(expected) | set(observed)
    contributions = {}
    for intent in all_intents:
        e = max(expected.get(intent, 0.0), _EPSILON)
        o = max(observed.get(intent, 0.0), _EPSILON)
        contributions[intent] = (o - e) * math.log(o / e)
    return contributions


class DriftMonitor:
    def compute_report(
        self, tenant_id: str, taxonomy: IntentTaxonomyRecord, logs: list[ClassificationLogRecord], alert_threshold: float
    ) -> DriftReportRecord:
        if not logs:
            # No observed traffic yet is "nothing to compare", not "total
            # drift" — treating it as maximal drift would page someone for
            # a brand-new taxonomy that simply hasn't seen traffic.
            return DriftReportRecord(
                id=new_id(), tenant_id=tenant_id, taxonomy_version=taxonomy.version, drift_score=0.0, flagged_intents=[]
            )

        expected = self._baseline_distribution(taxonomy)
        observed = self._observed_distribution(logs)
        drift_score = _psi(expected, observed)
        contributions = _per_intent_contribution(expected, observed)
        flagged = sorted(
            (intent for intent, c in contributions.items() if c > alert_threshold),
            key=lambda name: -contributions[name],
        )
        return DriftReportRecord(
            id=new_id(), tenant_id=tenant_id, taxonomy_version=taxonomy.version,
            drift_score=drift_score, flagged_intents=flagged,
        )

    def _baseline_distribution(self, taxonomy: IntentTaxonomyRecord) -> dict[str, float]:
        counts = {intent.name: max(len(intent.examples), 1) for intent in taxonomy.intents}
        total = sum(counts.values()) or 1
        return {name: count / total for name, count in counts.items()}

    def _observed_distribution(self, logs: list[ClassificationLogRecord]) -> dict[str, float]:
        counts: dict[str, int] = {}
        for log in logs:
            for intent in log.intents_detected:
                counts[intent.name] = counts.get(intent.name, 0) + 1
        total = sum(counts.values()) or 1
        return {name: count / total for name, count in counts.items()}

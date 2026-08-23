"""Bundled default crosswalk mapping table (LLD §Level 1 "living regulatory
feed": "the mapping is config-driven, not hardcoded logic").

This is the file that makes the living-regulatory-feed claim real: a new
EU AI Act delegated act, or a new framework entirely, becomes an edit to
this table (or a YAML file pointed to by `mapping_table_path`), not a code
change to the Crosswalk Engine itself. `RegulatoryFeedManager.load()` reads
whichever source is configured and upserts the shipped default when none
is.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MAPPINGS: list[dict[str, Any]] = [
    {
        "control_name": "human_oversight",
        "framework_name": "eu_ai_act",
        "framework_version": "2024",
        "clause_references": ["Art.14"],
        "mapping_rationale": "Human Oversight's approval queue and override log satisfy the Article 14 "
        "human-oversight-of-high-risk-systems requirement.",
    },
    {
        "control_name": "human_oversight",
        "framework_name": "nist_ai_rmf",
        "framework_version": "1.0",
        "clause_references": ["GOVERN-3.2"],
        "mapping_rationale": "Maps to NIST AI RMF's human-AI configuration and oversight governance function.",
    },
    {
        "control_name": "human_oversight",
        "framework_name": "iso_42001",
        "framework_version": "2023",
        "clause_references": ["A.6.2"],
        "mapping_rationale": "Maps to ISO 42001 Annex A.6.2 (human oversight of AI system operation).",
    },
    {
        "control_name": "guardrails_policy_check",
        "framework_name": "eu_ai_act",
        "framework_version": "2024",
        "clause_references": ["Art.15"],
        "mapping_rationale": "Guardrails' input/output policy enforcement satisfies Article 15's "
        "accuracy-robustness-cybersecurity requirement.",
    },
    {
        "control_name": "guardrails_policy_check",
        "framework_name": "nist_ai_rmf",
        "framework_version": "1.0",
        "clause_references": ["MANAGE-2.3"],
        "mapping_rationale": "Maps to NIST AI RMF's risk-response and mitigation management function.",
    },
    {
        "control_name": "sentinel_monitoring",
        "framework_name": "eu_ai_act",
        "framework_version": "2024",
        "clause_references": ["Art.72"],
        "mapping_rationale": "Sentinel Agents' post-market monitoring of deployed agent behaviour satisfies "
        "Article 72's post-market monitoring requirement.",
    },
    {
        "control_name": "sentinel_monitoring",
        "framework_name": "dora",
        "framework_version": "2022",
        "clause_references": ["Art.9"],
        "mapping_rationale": "Maps to DORA Article 9 (detection of ICT-related incidents and anomalies).",
    },
    {
        "control_name": "audit_logging",
        "framework_name": "eu_ai_act",
        "framework_version": "2024",
        "clause_references": ["Art.12"],
        "mapping_rationale": "Auditability's immutable event log satisfies Article 12's record-keeping "
        "requirement.",
    },
    {
        "control_name": "audit_logging",
        "framework_name": "iso_42001",
        "framework_version": "2023",
        "clause_references": ["A.7.4"],
        "mapping_rationale": "Maps to ISO 42001 Annex A.7.4 (documented information / record retention).",
    },
    {
        "control_name": "audit_logging",
        "framework_name": "dora",
        "framework_version": "2022",
        "clause_references": ["Art.15"],
        "mapping_rationale": "Maps to DORA Article 15 (ICT-related incident record-keeping).",
    },
    {
        "control_name": "workflow_confidence_gating",
        "framework_name": "eu_ai_act",
        "framework_version": "2024",
        "clause_references": ["Art.14"],
        "mapping_rationale": "Workflow Engine's confidence-gated autonomy routes low-confidence decisions to "
        "human review, itself part of satisfying Article 14.",
    },
    {
        "control_name": "workflow_confidence_gating",
        "framework_name": "nist_ai_rmf",
        "framework_version": "1.0",
        "clause_references": ["MANAGE-1.3"],
        "mapping_rationale": "Maps to NIST AI RMF's risk-prioritisation-and-response management function.",
    },
    # GDPR (Regulation (EU) 2016/679) — added after review: an AI platform handling
    # personal data needs this crosswalked regardless of whether a deployment is
    # in-scope for the EU AI Act, and this platform already implements controls that
    # map to it cleanly (Long-Term Memory's provable right-to-erasure flow chief among
    # them), so leaving it out of the default table was a real gap, not a deliberate
    # scoping decision.
    {
        "control_name": "right_to_erasure",
        "framework_name": "gdpr",
        "framework_version": "2016",
        "clause_references": ["Art.17"],
        "mapping_rationale": "Long-Term Memory's cryptographically provable forgetting flow satisfies "
        "Article 17's right to erasure ('right to be forgotten').",
    },
    {
        "control_name": "pii_redaction",
        "framework_name": "gdpr",
        "framework_version": "2016",
        "clause_references": ["Art.5(1)(c)", "Art.25"],
        "mapping_rationale": "Guardrails' PII detection-and-redaction satisfies Article 5(1)(c)'s data "
        "minimisation principle and Article 25's data-protection-by-design-and-by-default requirement.",
    },
    {
        "control_name": "human_oversight",
        "framework_name": "gdpr",
        "framework_version": "2016",
        "clause_references": ["Art.22"],
        "mapping_rationale": "Human Oversight's approval queue satisfies Article 22's safeguard against "
        "solely-automated decisions with legal or similarly significant effects.",
    },
    {
        "control_name": "audit_logging",
        "framework_name": "gdpr",
        "framework_version": "2016",
        "clause_references": ["Art.30", "Art.5(2)"],
        "mapping_rationale": "Auditability's immutable event log satisfies Article 30's records-of-processing "
        "requirement and Article 5(2)'s accountability principle.",
    },
]

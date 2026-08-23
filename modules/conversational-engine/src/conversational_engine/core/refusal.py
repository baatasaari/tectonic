"""Explainable Refusal Composer (LLD §2.2, differentiator: "explainable
refusal"). Turns a violation category — from Guardrails, or from the Persona
Engine's own denied-topic check — into a user-facing message that traces to
a specific rule, useful for both UX and audit.
"""
from __future__ import annotations

_TEMPLATES: dict[str, str] = {
    "denied_topic": "I'm not able to help with that topic here — {detail}. If this is urgent, I can connect you with a person.",
    "policy_violation": "I can't do that: it falls under our {detail} policy. Let me know if there's something else I can help with.",
    "out_of_scope": "That's outside what I can help with in this conversation ({detail}). I can hand you off to someone who can.",
    "pii_risk": "I can't include that kind of information ({detail}) in a response here, for privacy reasons.",
}
_DEFAULT_TEMPLATE = "I'm not able to help with that request ({detail})."


class RefusalComposer:
    def compose(self, violation_category: str, detail: str = "") -> str:
        template = _TEMPLATES.get(violation_category, _DEFAULT_TEMPLATE)
        return template.format(detail=detail or violation_category)

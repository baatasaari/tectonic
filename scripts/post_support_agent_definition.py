#!/usr/bin/env python3
"""Posts the `support-agent-v1` workflow definition (ticket #82,
docs/phase2-product-slice-01-support-agent.md) to Workflow Engine's real
`POST /definitions` -- real configuration (a `WorkflowDefinitionRecord
.graph_schema` document), not new Workflow Engine code: the module's own
symbolic/neural step routing, confidence-gated autonomy, and (ticket
#82's own new symbolic_rulesets field) rule registration already do
everything this definition needs.

The DAG (intent -> retrieve-or-tool-call -> guardrail -> respond-or-
escalate), matching the design doc's own sequence diagrams:

    intent_step --policy_question--> rag_step ------------------\
        |--order_status--> order_lookup_step -------------------> respond
        \--refund_request--> extract_refund_step -> threshold_step
                                  |--escalate--> escalate_step --/
                                  \--auto_resolve-----------------/

`threshold_step`'s own refund-threshold escalation rule is this ticket's
own "first symbolic rule this platform actually configures end-to-end"
(see the design doc's own "New integration glue" section) -- a business
rule on the *extracted refund amount*, not a confidence score, per the
design doc's own explanation of why this is a deliberately different
escalation path than Workflow Engine's confidence-gated one.

Guardrails screens every neural step's own input/output automatically
(NeuralStepExecutor's own existing, unconditional behavior) -- nothing
extra to configure here for that.

Usage: python3 scripts/post_support_agent_definition.py
Expects Workflow Engine already running and
scripts/seed_support_agent_demo.py phase1 already run (for the real
tool_id in /tmp/support_agent_seed_output.json).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

OUTPUT_PATH = Path(os.environ.get("SUPPORT_AGENT_SEED_OUTPUT", "/tmp/support_agent_seed_output.json"))
WORKFLOW_ENGINE_URL = os.environ.get("WORKFLOW_ENGINE_URL", "http://localhost:8080")
JWT_SHARED_SECRET = os.environ.get("TECTONIC_JWT_SHARED_SECRET", "dev-insecure-shared-secret-change-me")
ISSUER = "post-support-agent-definition"

REFUND_THRESHOLD_AMOUNT = 500.0

DEFINITION_ID = "support-agent-v1"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_service_token(*, audience: str, ttl_seconds: int = 300) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": audience, "iat": now, "exp": now + ttl_seconds}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(JWT_SHARED_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def build_graph_schema(tool_id: str) -> dict:
    return {
        "nodes": [
            {"id": "intent_step", "execution_mode": "neural", "config": {"intent_ref": "primary"}},
            {"id": "rag_step", "execution_mode": "neural", "config": {"rag_ref": "support-kb"}},
            {
                "id": "order_lookup_step", "execution_mode": "neural",
                "config": {"agent_ref": "order-lookup-agent", "tool_refs": [tool_id]},
            },
            {"id": "extract_refund_step", "execution_mode": "neural", "config": {"agent_ref": "refund-extractor-agent"}},
            {"id": "threshold_step", "execution_mode": "symbolic", "config": {"symbolic_rule_ref": "refund-threshold"}},
            {"id": "escalate_step", "execution_mode": "human", "config": {}},
            {"id": "respond", "execution_mode": "neural", "config": {"agent_ref": "compose-response-agent"}},
        ],
        "edges": [
            {"from": "intent_step", "to": "rag_step", "condition": "intent_step.intent == 'policy_question'"},
            {"from": "intent_step", "to": "order_lookup_step", "condition": "intent_step.intent == 'order_status'"},
            {"from": "intent_step", "to": "extract_refund_step", "condition": "intent_step.intent == 'refund_request'"},
            {"from": "rag_step", "to": "respond"},
            {"from": "order_lookup_step", "to": "respond"},
            {"from": "extract_refund_step", "to": "threshold_step"},
            {"from": "threshold_step", "to": "escalate_step", "condition": "threshold_step.decision == 'escalate'"},
            {"from": "threshold_step", "to": "respond", "condition": "threshold_step.decision == 'auto_resolve'"},
            {"from": "escalate_step", "to": "respond"},
        ],
        "entry_point": "intent_step",
        "termination_points": ["respond"],
    }


def build_symbolic_rulesets() -> dict:
    return {
        "refund-threshold": [
            {
                "id": "escalate-above-threshold",
                "when": f"extract_refund_step.refund_amount > {REFUND_THRESHOLD_AMOUNT}",
                "then": {"decision": "escalate"},
                "priority": 10,
            },
            {"id": "auto-resolve-below-threshold", "when": "True", "then": {"decision": "auto_resolve"}, "priority": 0},
        ]
    }


def main() -> int:
    seed = json.loads(OUTPUT_PATH.read_text())
    tool_id = seed["tool_id"]
    tenant_id = seed["tenant_id"]

    body = {
        "name": DEFINITION_ID,
        "graph_schema": build_graph_schema(tool_id),
        "symbolic_rulesets": build_symbolic_rulesets(),
    }
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        f"{WORKFLOW_ENGINE_URL}/v1/workflow-engine/definitions",
        data=data, method="POST",
        headers={
            "Authorization": f"Bearer {mint_service_token(audience='workflow-engine')}",
            "Content-Type": "application/json",
            # Real tenant scoping: the definition must be created under
            # Acme's own real tenant so Workflow Engine's own
            # get_definition_by_name(name, tenant_id) -- what Conversational
            # Engine's real /instances call resolves by name against --
            # finds it for that tenant, not the module's configured default.
            "X-Tenant-Id": tenant_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        print(f"FAILED: {exc.code}: {raw.decode(errors='replace')}")
        return 1

    print(f"Posted definition {result['id']} (name={DEFINITION_ID}, version={result['version']}, status={result['status']})")
    print(f"Real graph validation passed: {len(build_graph_schema(tool_id)['nodes'])} nodes, "
          f"{len(build_graph_schema(tool_id)['edges'])} edges, 1 symbolic ruleset registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

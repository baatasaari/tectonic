#!/usr/bin/env python3
"""Quick manual smoke test driving Workflow Engine's real /instances API
directly for the 3 scripted conversations, before writing the formal
pytest e2e test."""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

SECRET = "dev-insecure-shared-secret-change-me"
WE_URL = "http://localhost:8080"

with open("/tmp/support_agent_seed_output.json") as f:
    seed = json.load(f)
TENANT_ID = seed["tenant_id"]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint(audience: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": "smoke-test", "aud": audience, "iat": now, "exp": now + 300}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def start_instance(message: str) -> dict:
    body = {"definition_id": "support-agent-v1", "initial_context": {"message": message}}
    req = urllib.request.Request(
        f"{WE_URL}/v1/workflow-engine/instances", data=json.dumps(body).encode(), method="POST",
        headers={
            "Authorization": f"Bearer {mint('workflow-engine')}",
            "Content-Type": "application/json",
            "X-Tenant-Id": TENANT_ID,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print("FAILED", e.code, e.read().decode())
        raise


def get_instance(instance_id: str) -> dict:
    req = urllib.request.Request(
        f"{WE_URL}/v1/workflow-engine/instances/{instance_id}",
        headers={"Authorization": f"Bearer {mint('workflow-engine')}", "X-Tenant-Id": TENANT_ID},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


for label, message in [
    ("policy question", "What's your return policy?"),
    ("order status", "Where's my order #A1029?"),
    ("refund request", "I want a refund for order #A1029, it's $850."),
]:
    print(f"\n=== {label}: {message!r} ===")
    started = start_instance(message)
    print("start response:", started)
    detail = get_instance(started["id"])
    print("status:", detail["status"])
    print("context:", json.dumps(detail["context"], indent=2))
    print("steps:", [(s["step_id"], s["status"]) for s in detail["steps"]])

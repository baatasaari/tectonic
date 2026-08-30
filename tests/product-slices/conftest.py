"""Session-scoped fixture standing up the entire Phase 2 support-agent
slice (ticket #82, docs/phase2-product-slice-01-support-agent.md) as
real, separate module processes -- see
scripts/product-slice-stubs/stack.py's own module docstring for exactly
what "real" means here (no Docker in this sandbox; real per-module
Postgres databases, real Redis, real Qdrant-embedded Vector DB, a real
mock external-systems stub standing in only for the two things
genuinely outside this platform's own 34 modules: an LLM provider and a
merchant's order-status backend).

This is intentionally the only test tier in this repo that launches an
entire live multi-process stack itself, rather than testing one module in
isolation -- see this directory's own README for why that's a deliberate,
narrow exception to every other module's own unit/integration/contract
tiers, not a new house style.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STACK_DIR = REPO_ROOT / "scripts" / "product-slice-stubs"
sys.path.insert(0, str(STACK_DIR))

import stack  # noqa: E402  (needs the sys.path insert above)

JWT_SHARED_SECRET = stack.JWT_SECRET


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_service_token(*, audience: str, ttl_seconds: int = 300) -> str:
    """Same HS256 service-token scheme every module's own
    `ServiceAuthMiddleware` accepts (security/jwt_auth.py, every module) --
    duplicated here rather than imported since no one module "owns" this
    logic across process/venv boundaries the way scripts/ already assumes
    (scripts/seed_support_agent_demo.py's own `mint_service_token` is the
    same code, for the same reason)."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": "product-slice-test", "aud": audience, "iat": now, "exp": now + ttl_seconds}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(JWT_SHARED_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


@pytest.fixture(scope="session")
def live_stack():
    """Brings up all 15 modules + the mock external-systems stub, seeds
    Acme Corp (tenant, entitlements, identity, LLM Gateway provisioning,
    tool registration, intent taxonomy, indexed knowledge base, a real
    pricing plan) and posts the `support-agent-v1` workflow definition --
    once per test session, torn down at the end (or on a failure here)
    so no module's own unit/integration/contract tests run afterward
    against a polluted environment (ticket #82's own hard-won lesson:
    a leftover live stack from a previous manual run made an unrelated
    module's contract test fail against a real peer instead of the
    stub/no-op it expected)."""
    log_dir = Path(os.environ.get("SUPPORT_AGENT_SLICE_LOGS", "/tmp/support-agent-slice-logs"))
    try:
        seed = stack.up_all(log_dir=log_dir)
    except Exception:
        stack.down()
        raise
    try:
        yield seed
    finally:
        stack.down()


@pytest.fixture(scope="session")
def tenant_id(live_stack):
    return live_stack["tenant_id"]


@pytest.fixture(scope="session")
def end_user_identity_id(live_stack):
    return live_stack["end_user_identity_id"]


class ApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int, body) -> None:
        super().__init__(f"{method} {url} -> {status}: {body}")
        self.status = status
        self.body = body


def api_call(
    method: str, url: str, *, audience: str, json_body: dict | None = None,
    tenant_id: str | None = None, params: dict | None = None,
) -> object:
    """Real HTTP call against a real running module -- every test in this
    directory goes through this, never a mock of this platform's own
    code (CLAUDE.md's own established discipline, same reasoning that
    scripts/seed_support_agent_demo.py's own `call()` already documents)."""
    headers = {"Authorization": f"Bearer {mint_service_token(audience=audience)}"}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    resp = httpx.request(method, url, json=json_body, params=params, headers=headers, timeout=30.0)
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        raise ApiError(method, url, resp.status_code, body)
    return resp.json() if resp.content else None

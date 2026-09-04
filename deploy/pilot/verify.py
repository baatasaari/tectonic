#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

PHASE1 = {
    "identity-and-access": 8110,
    "multi-tenancy": 8109,
    "llm-gateway": 8082,
    "intent-detection": 8084,
    "knowledge-base": 8088,
    "tool-orchestration": 8083,
    "guardrails": 8093,
    "human-oversight": 8095,
    "billing-and-metering": 8112,
    "auditability": 8099,
    "observability": 8098,
    "conversational-engine": 8081,
}
PHASE2 = {"workflow-engine": 8080, "agentic-rag": 8085, "vector-db": 8089}


def wait_for(name: str, port: int, deadline: float) -> None:
    url = f"http://127.0.0.1:{port}/healthz"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    print(f"ok  {name:<28} {url}")
                    return
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                print(f"ok  {name:<28} {url} (degraded dependency)")
                return
            last_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"{name} did not become ready: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("phase1", "full"), default="full")
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    services = dict(PHASE1)
    if args.phase == "full":
        services.update(PHASE2)
    deadline = time.monotonic() + args.timeout
    for name, port in services.items():
        wait_for(name, port, deadline)

    if not args.health_only and args.phase == "full":
        seed_path = Path(__file__).with_name("state") / "seed.json"
        if not seed_path.exists():
            raise RuntimeError("pilot seed state is missing")
        seed = json.loads(seed_path.read_text())
        required = {
            "tenant_id",
            "end_user_token",
            "llm_gateway_virtual_key_id",
            "tool_id",
        }
        missing = sorted(required - seed.keys())
        if missing:
            raise RuntimeError(f"pilot seed state is incomplete: {', '.join(missing)}")
        print(f"ok  seeded tenant               {seed['tenant_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

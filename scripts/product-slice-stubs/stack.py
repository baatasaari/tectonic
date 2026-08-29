"""Launches every module in the Phase 2 support-agent product slice
(ticket #82, docs/phase2-product-slice-01-support-agent.md) as real,
separate uvicorn processes against real per-module Postgres databases on
this sandbox's own local Postgres cluster -- no Docker, matching
CLAUDE.md's own sandbox-infrastructure section. Each module's own
Dockerfile CMD (`uvicorn <pkg>.main:app --host 0.0.0.0 --port <port>`) is
run directly against that module's own `.venv`, with peer base-URL env
vars pointed at each other's real localhost ports instead of a
dependency-stub.

Three-phase startup, not because of module dependencies at the HTTP
level, but because LLM Gateway's `X-Virtual-Key` is a real,
server-generated UUID that only exists once seeded -- both Vector DB and
Workflow Engine need this same one real id baked into their own env
*before* they start (each reads its own `..._llm_gateway_virtual_key`
setting once at process startup):

  1. `up_phase1()` starts every module except Vector DB and Workflow
     Engine (neither needs the real virtual key to exist for any of the
     *other* seeding steps -- tenant/entitlements/identity/LLM Gateway's
     own provider+budget+virtual-key provisioning/tool registration/
     intent taxonomy all only need modules already in this phase).
  2. The caller runs `scripts/seed_support_agent_demo.py phase1`, which
     creates the real virtual key (among other things) and writes it to
     the seed-output JSON.
  3. `up_phase2(virtual_key_id)` starts Vector DB and Workflow Engine
     with that id baked into their own env.
  4. The caller runs `scripts/seed_support_agent_demo.py phase2` (needs
     Vector DB up, for real document indexing) and
     `scripts/post_support_agent_definition.py` (needs Workflow Engine
     up, and the real tool id phase1 registered).

Importable (used by tests/product-slices/conftest.py) or runnable
directly for a manual/exploratory run:
    python3 scripts/product-slice-stubs/stack.py up
    python3 scripts/product-slice-stubs/stack.py down
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULES_DIR = REPO_ROOT / "modules"
MOCK_STUB_PORT = 9200

PG_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/{db}"
JWT_SECRET = "dev-insecure-shared-secret-change-me"  # every module's own insecure zero-config default


@dataclass
class ModuleSpec:
    name: str  # directory under modules/
    package: str  # importable package name
    port: int
    db: str
    env_prefix: str  # this module's own config.py env_prefix -- NOT always package.upper() (e.g. identity_and_access -> IDENTITY_ACCESS_, billing_and_metering -> BILLING_)
    extra_env: dict[str, str] = field(default_factory=dict)


# Every module in the slice's own critical path (docs/phase2-product-slice-01-support-agent.md's
# own module table), minus Workflow Engine (started separately -- see module docstring above).
# Ports/DB names match each module's own deploy/docker-compose.yml.
MODULE_SPECS: list[ModuleSpec] = [
    ModuleSpec(
        "identity-and-access", "identity_and_access", 8110, "identity_and_access", "IDENTITY_ACCESS",
        {"IDENTITY_ACCESS_AUDITABILITY_BASE_URL": "http://localhost:8099"},
    ),
    ModuleSpec(
        "multi-tenancy", "multi_tenancy", 8109, "multi_tenancy", "MULTI_TENANCY",
        {
            "MULTI_TENANCY_KAFKA_BOOTSTRAP_SERVERS": "localhost:19999",  # unreachable on purpose -- degrades, doesn't block (ticket #82)
            "MULTI_TENANCY_AUDITABILITY_BASE_URL": "http://localhost:8099",
            "MULTI_TENANCY_PROBE_TARGETS": "[]",
        },
    ),
    ModuleSpec(
        "llm-gateway", "llm_gateway", 8082, "llm_gateway", "LLM_GATEWAY",
        {
            "LLM_GATEWAY_REDIS_URL": "redis://localhost:6379/1",
            "LLM_GATEWAY_SECRETS_AND_CREDENTIAL_MANAGEMENT_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "LLM_GATEWAY_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        },
    ),
    ModuleSpec(
        "intent-detection", "intent_detection", 8084, "intent_detection", "INTENT_DETECTION",
        {"INTENT_DETECTION_LLM_GATEWAY_BASE_URL": "http://localhost:8082", "INTENT_DETECTION_MULTI_TENANCY_BASE_URL": "http://localhost:8109"},
    ),
    ModuleSpec(
        "knowledge-base", "knowledge_base", 8088, "knowledge_base", "KNOWLEDGE_BASE",
        {
            "KNOWLEDGE_BASE_VECTOR_DB_BASE_URL": "http://localhost:8089",
            "KNOWLEDGE_BASE_GRAPH_DB_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "KNOWLEDGE_BASE_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        },
    ),
    ModuleSpec(
        "tool-orchestration", "tool_orchestration", 8083, "tool_orchestration", "TOOL_ORCHESTRATION",
        {
            "TOOL_ORCHESTRATION_REDIS_URL": "redis://localhost:6379/2",
            "TOOL_ORCHESTRATION_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
            "TOOL_ORCHESTRATION_GUARDRAILS_BASE_URL": "http://localhost:8093",
            "TOOL_ORCHESTRATION_SENTINEL_AGENTS_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "TOOL_ORCHESTRATION_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        },
    ),
    ModuleSpec(
        "guardrails", "guardrails", 8093, "guardrails", "GUARDRAILS",
        {
            "GUARDRAILS_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
            "GUARDRAILS_SENTINEL_AGENTS_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "GUARDRAILS_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        },
    ),
    ModuleSpec(
        "human-oversight", "human_oversight", 8095, "human_oversight", "HUMAN_OVERSIGHT",
        {
            "HUMAN_OVERSIGHT_AUDITABILITY_BASE_URL": "http://localhost:8099",
            "HUMAN_OVERSIGHT_NOTIFICATION_STUB_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "HUMAN_OVERSIGHT_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
            # The one real callback route this module's own dispatcher already
            # documents (clients/http_clients.py) -- resumes a real Workflow
            # Engine instance for real on a real reviewer decision.
            "HUMAN_OVERSIGHT_SERVICE_URLS": '{"workflow-engine": "http://localhost:8080"}',
        },
    ),
    ModuleSpec(
        "billing-and-metering", "billing_and_metering", 8112, "billing_and_metering", "BILLING",
        {
            "BILLING_FINOPS_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "BILLING_AUDITABILITY_BASE_URL": "http://localhost:8099",
            "BILLING_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        },
    ),
    ModuleSpec(
        "auditability", "auditability", 8099, "auditability", "AUDITABILITY",
        {"AUDITABILITY_LLM_GATEWAY_BASE_URL": "http://localhost:8082"},
    ),
    ModuleSpec(
        "observability", "observability", 8098, "observability", "OBSERVABILITY",
        {"OBSERVABILITY_LLM_GATEWAY_BASE_URL": "http://localhost:8082", "OBSERVABILITY_MULTI_TENANCY_BASE_URL": "http://localhost:8109"},
    ),
    ModuleSpec(
        "conversational-engine", "conversational_engine", 8081, "conversational_engine", "CONVERSATIONAL_ENGINE",
        {
            "CONVERSATIONAL_ENGINE_REDIS_URL": "redis://localhost:6379/3",
            "CONVERSATIONAL_ENGINE_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
            "CONVERSATIONAL_ENGINE_GUARDRAILS_BASE_URL": "http://localhost:8093",
            "CONVERSATIONAL_ENGINE_LONG_TERM_MEMORY_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
            "CONVERSATIONAL_ENGINE_HUMAN_OVERSIGHT_BASE_URL": "http://localhost:8095",
            "CONVERSATIONAL_ENGINE_OBSERVABILITY_BASE_URL": "http://localhost:8098",
            "CONVERSATIONAL_ENGINE_AUDITABILITY_BASE_URL": "http://localhost:8099",
            "CONVERSATIONAL_ENGINE_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
            "CONVERSATIONAL_ENGINE_WORKFLOW_ENGINE_BASE_URL": "http://localhost:8080",
            "CONVERSATIONAL_ENGINE_WORKFLOW_ROUTING__ENABLED": "true",
            "CONVERSATIONAL_ENGINE_WORKFLOW_ROUTING__DEFINITION_ID": "support-agent-v1",
        },
    ),
]

# Started in phase 2 (see module docstring) -- both need the real, seeded
# LLM Gateway virtual key id baked into their own env before they start.
WORKFLOW_ENGINE_SPEC = ModuleSpec(
    "workflow-engine", "workflow_engine", 8080, "workflow_engine", "WORKFLOW_ENGINE",
    {
        "WORKFLOW_ENGINE_KAFKA_BOOTSTRAP_SERVERS": "localhost:19999",  # unreachable on purpose -- degrades, doesn't block (ticket #82)
        "WORKFLOW_ENGINE_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
        "WORKFLOW_ENGINE_TOOL_ORCHESTRATION_BASE_URL": "http://localhost:8083",
        "WORKFLOW_ENGINE_GUARDRAILS_BASE_URL": "http://localhost:8093",
        "WORKFLOW_ENGINE_HUMAN_OVERSIGHT_BASE_URL": "http://localhost:8095",
        "WORKFLOW_ENGINE_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        "WORKFLOW_ENGINE_INTENT_DETECTION_BASE_URL": "http://localhost:8084",
        "WORKFLOW_ENGINE_AGENTIC_RAG_BASE_URL": "http://localhost:8085",
    },
)

AGENTIC_RAG_SPEC = ModuleSpec(
    "agentic-rag", "agentic_rag", 8085, "agentic_rag", "AGENTIC_RAG",
    {
        "AGENTIC_RAG_VECTOR_DB_BASE_URL": "http://localhost:8089",
        "AGENTIC_RAG_GRAPH_DB_BASE_URL": f"http://localhost:{MOCK_STUB_PORT}",
        "AGENTIC_RAG_KNOWLEDGE_BASE_BASE_URL": "http://localhost:8088",
        "AGENTIC_RAG_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
        "AGENTIC_RAG_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
        # Knowledge Base's own real symbolic lookup endpoint and Graph DB
        # (legitimately out-of-this-slice's-scope infra) don't exist for
        # real -- ticket #82 disables hybrid fan-out rather than inventing
        # either. Vector DB alone already carries this slice's own real
        # indexed return-policy document.
        "AGENTIC_RAG_RETRIEVAL__HYBRID_RETRIEVAL_ENABLED": "false",
    },
)

VECTOR_DB_SPEC = ModuleSpec(
    "vector-db", "vector_db", 8089, "vector_db", "VECTOR_DB",
    {
        "VECTOR_DB_QDRANT__EMBEDDED_IN_MEMORY": "true",
        "VECTOR_DB_LLM_GATEWAY_BASE_URL": "http://localhost:8082",
        "VECTOR_DB_MULTI_TENANCY_BASE_URL": "http://localhost:8109",
    },
)

_processes: dict[str, subprocess.Popen] = {}


def _venv_python(module_dir: str) -> Path:
    return MODULES_DIR / module_dir / ".venv" / "bin" / "python3"


def migrate_module(spec: ModuleSpec) -> None:
    env = dict(os.environ)
    db_url = PG_URL.format(db=spec.db)
    env[f"{spec.env_prefix}_DATABASE_URL"] = db_url
    result = subprocess.run(
        [str(_venv_python(spec.name)), "-m", "alembic", "upgrade", "head"],
        cwd=str(MODULES_DIR / spec.name), env=env, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed for {spec.name}:\n{result.stdout}\n{result.stderr}")


def start_module(spec: ModuleSpec, *, log_dir: Path) -> None:
    env = dict(os.environ)
    env[f"{spec.env_prefix}_DATABASE_URL"] = PG_URL.format(db=spec.db)
    env[f"{spec.env_prefix}_HTTP_PORT"] = str(spec.port)
    env["TECTONIC_JWT_SHARED_SECRET"] = JWT_SECRET
    env.update(spec.extra_env)

    log_path = log_dir / f"{spec.name}.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [str(_venv_python(spec.name)), "-m", "uvicorn", f"{spec.package}.main:app", "--host", "127.0.0.1", "--port", str(spec.port)],
        cwd=str(MODULES_DIR / spec.name), env=env, stdout=log_file, stderr=subprocess.STDOUT,
        start_new_session=True,  # detach from this launcher's own process group/session (setsid-equivalent) --
        # this launcher is often itself run as a backgrounded shell command whose own process group gets
        # reaped once that one shell invocation is considered "done"; without this every module process
        # dies with it even though the modules are meant to keep serving independently until `down()`.
    )
    _processes[spec.name] = proc


def start_mock_stub(*, log_dir: Path) -> None:
    stub_dir = Path(__file__).resolve().parent
    # Any module's own venv has fastapi/uvicorn; tool-orchestration's is as good as any.
    python = str(_venv_python("tool-orchestration"))
    log_path = log_dir / "external-mocks.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "external_mocks:app", "--host", "127.0.0.1", "--port", str(MOCK_STUB_PORT)],
        cwd=str(stub_dir), stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
    )
    _processes["external-mocks"] = proc


def wait_healthy(port: int, *, timeout: float = 30.0, path: str = "/healthz") -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=2) as resp:
                return  # any response at all means the process is up and serving
        except urllib.error.HTTPError as exc:
            # 503 = degraded-but-up (e.g. Kafka unreachable) -- still a real,
            # serving process, exactly what /healthz is designed to report
            # (see e.g. workflow-engine's own main.py healthz()).
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(f"port {port} never became healthy: {last_error}")


def up_phase1(*, log_dir: Path) -> None:
    """Starts everything except Vector DB, Agentic RAG and Workflow Engine
    -- see the module docstring for why those three wait for phase 2 (all
    three need the real, seeded LLM Gateway virtual key id baked into
    their own env before they start)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    print("Running migrations...")
    for spec in [*MODULE_SPECS, VECTOR_DB_SPEC, AGENTIC_RAG_SPEC, WORKFLOW_ENGINE_SPEC]:
        migrate_module(spec)

    print("Starting mock external-systems stub...")
    start_mock_stub(log_dir=log_dir)
    wait_healthy(MOCK_STUB_PORT)

    print("Starting phase 1 modules (everything except Vector DB, Agentic RAG and Workflow Engine)...")
    for spec in MODULE_SPECS:
        start_module(spec, log_dir=log_dir)
    for spec in MODULE_SPECS:
        wait_healthy(spec.port)
    print("Phase 1 modules healthy. Run scripts/seed_support_agent_demo.py phase1 next.")


def up_phase2(*, log_dir: Path, llm_gateway_virtual_key: str) -> None:
    """Starts Vector DB, Agentic RAG and Workflow Engine with the real,
    seeded LLM Gateway virtual key id baked into their own env."""
    VECTOR_DB_SPEC.extra_env["VECTOR_DB_LLM_GATEWAY_VIRTUAL_KEY"] = llm_gateway_virtual_key
    AGENTIC_RAG_SPEC.extra_env["AGENTIC_RAG_LLM_GATEWAY_VIRTUAL_KEY"] = llm_gateway_virtual_key
    WORKFLOW_ENGINE_SPEC.extra_env["WORKFLOW_ENGINE_LLM_GATEWAY_VIRTUAL_KEY"] = llm_gateway_virtual_key
    start_module(VECTOR_DB_SPEC, log_dir=log_dir)
    start_module(AGENTIC_RAG_SPEC, log_dir=log_dir)
    start_module(WORKFLOW_ENGINE_SPEC, log_dir=log_dir)
    wait_healthy(VECTOR_DB_SPEC.port)
    wait_healthy(AGENTIC_RAG_SPEC.port)
    wait_healthy(WORKFLOW_ENGINE_SPEC.port)
    print("Vector DB, Agentic RAG and Workflow Engine healthy. Run scripts/seed_support_agent_demo.py phase2 "
          "and scripts/post_support_agent_definition.py next.")


def down() -> None:
    for name, proc in _processes.items():
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    for name, proc in _processes.items():
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
    _processes.clear()


def down_by_port_scan() -> None:
    """`down()` only works within the same Python process that called `up()`
    (`_processes` is in-memory). For a standalone `stack.py down` invocation
    (a separate process), find and kill by port instead."""
    all_ports = [s.port for s in MODULE_SPECS] + [
        VECTOR_DB_SPEC.port, AGENTIC_RAG_SPEC.port, WORKFLOW_ENGINE_SPEC.port, MOCK_STUB_PORT,
    ]
    for port in all_ports:
        subprocess.run(["pkill", "-f", f"port {port}$"], check=False)


def run_seed_script(script_name: str, *extra_args: str) -> dict:
    """Runs one of this slice's own standalone seed scripts as a real
    subprocess (matching this repo's established "seed against real
    running module APIs, as a real runnable script" convention -- see
    scripts/seed_subscription_tiers.py) and returns the seed-output JSON
    it leaves behind."""
    output_path = Path(os.environ.get("SUPPORT_AGENT_SEED_OUTPUT", "/tmp/support_agent_seed_output.json"))
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script_name), *extra_args],
        capture_output=True, text=True, timeout=120,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(output_path.read_text())


def up_all(*, log_dir: Path) -> dict:
    """Full end-to-end orchestration: phase 1 -> seed phase1 -> phase 2 ->
    seed phase2 -> post the workflow definition. Returns the final
    seed-output dict (tenant_id, tool_id, end_user_token, etc.)."""
    up_phase1(log_dir=log_dir)
    seed = run_seed_script("seed_support_agent_demo.py", "phase1")
    up_phase2(log_dir=log_dir, llm_gateway_virtual_key=seed["llm_gateway_virtual_key_id"])
    seed = run_seed_script("seed_support_agent_demo.py", "phase2")
    run_seed_script("post_support_agent_definition.py")
    return seed


if __name__ == "__main__":
    log_dir = Path("/tmp/support-agent-slice-logs")
    if len(sys.argv) > 1 and sys.argv[1] == "down":
        down_by_port_scan()
    else:
        seed = up_all(log_dir=log_dir)
        print(f"Stack fully up and seeded. Logs in {log_dir}. tenant_id={seed['tenant_id']}")

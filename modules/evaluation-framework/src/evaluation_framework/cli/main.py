"""CLI for CI/CD pipeline integration (LLD §Level 1 "chosen stack": "plus
a CLI (reusing AgentEval's existing CLI pattern) for CI/CD pipeline
integration" — AgentEval's own source isn't available in this build
environment, so this reimplements the same `agenteval run --gate`
entrypoint shape against this module's own HTTP API).

    agenteval run --config path/to/eval-config.json --gate

Exits 1 (blocking the CI/CD pipeline) when the gate fails, mirroring the
LLD's own sequence diagram ("CLI-->>CI: exit code 1, deployment blocked").
"""
from __future__ import annotations

import json
import sys

import click
import httpx


@click.group()
def cli() -> None:
    """Evaluation Framework CLI."""


@cli.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True), help="JSON eval-run config file.")
@click.option("--api-url", default="http://localhost:8097", show_default=True, help="Evaluation Framework base URL.")
@click.option("--gate", "run_gate", is_flag=True, default=False, help="Also run the CI/CD gate check after evaluating.")
@click.option("--environment", default="production", show_default=True, help="Gate environment label.")
def run(config_path: str, api_url: str, run_gate: bool, environment: str) -> None:
    """Runs POST /evaluate (and optionally POST /gate) against a config file shaped like:

    \b
    {
      "tenant_id": "acme", "agent_ref": "support-agent-v3",
      "agent_output": "...", "reference_data": {"context": "..."},
      "metric_set": ["faithfulness", "tool_trace_correctness"], "trigger_source": "ci_cd"
    }
    """
    with open(config_path) as f:
        payload = json.load(f)

    with httpx.Client(base_url=api_url, timeout=30.0) as client:
        resp = client.post("/v1/evaluation-framework/evaluate", json=payload)
        resp.raise_for_status()
        eval_run = resp.json()
        click.echo(json.dumps(eval_run, indent=2))

        if not run_gate:
            return

        gate_resp = client.post(
            "/v1/evaluation-framework/gate",
            json={"tenant_id": payload["tenant_id"], "eval_run_id": eval_run["id"], "environment": environment},
        )
        gate_resp.raise_for_status()
        gate_result = gate_resp.json()
        click.echo(json.dumps(gate_result, indent=2))

        if not gate_result["overall_passed"]:
            click.echo(f"GATE FAILED: {gate_result['blocking_failures']}", err=True)
            sys.exit(1)
        click.echo("GATE PASSED")


if __name__ == "__main__":
    cli()

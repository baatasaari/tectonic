import json

import httpx
import respx
from click.testing import CliRunner

from evaluation_framework.cli.main import cli


def _write_config(tmp_path, **overrides):
    payload = {
        "tenant_id": "t1", "agent_ref": "agent-1", "agent_output": "hello world",
        "reference_data": {"context": "hello world today"}, "metric_set": ["faithfulness"], "trigger_source": "ci_cd",
    }
    payload.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    return str(path)


@respx.mock
def test_cli_run_without_gate_prints_eval_run(tmp_path):
    respx.post("http://api.local/v1/evaluation-framework/evaluate").mock(
        return_value=httpx.Response(201, json={"id": "run-1", "status": "completed", "scores": []})
    )
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", config_path, "--api-url", "http://api.local"])

    assert result.exit_code == 0
    assert "run-1" in result.output


@respx.mock
def test_cli_run_with_gate_passing_exits_zero(tmp_path):
    respx.post("http://api.local/v1/evaluation-framework/evaluate").mock(
        return_value=httpx.Response(201, json={"id": "run-1", "status": "completed", "scores": []})
    )
    respx.post("http://api.local/v1/evaluation-framework/gate").mock(
        return_value=httpx.Response(200, json={"id": "gate-1", "overall_passed": True, "blocking_failures": []})
    )
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", config_path, "--api-url", "http://api.local", "--gate"])

    assert result.exit_code == 0
    assert "GATE PASSED" in result.output


@respx.mock
def test_cli_run_with_gate_failing_exits_one(tmp_path):
    respx.post("http://api.local/v1/evaluation-framework/evaluate").mock(
        return_value=httpx.Response(201, json={"id": "run-1", "status": "completed", "scores": []})
    )
    respx.post("http://api.local/v1/evaluation-framework/gate").mock(
        return_value=httpx.Response(200, json={"id": "gate-1", "overall_passed": False, "blocking_failures": ["faithfulness"]})
    )
    config_path = _write_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", config_path, "--api-url", "http://api.local", "--gate"])

    assert result.exit_code == 1
    assert "GATE FAILED" in result.output

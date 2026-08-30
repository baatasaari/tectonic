"""Tests for clients/finops_client.py -- calls FinOps's real
GET /cost-reports/{tenant_id} endpoint shape, and treats a 404 (unknown
budget_policy_id) as "not configured", not an error."""
from __future__ import annotations

import httpx
import respx

from deployment_strategy.clients.finops_client import HTTPFinOpsClient


@respx.mock
async def test_cost_report_utilisation_returns_the_ratio():
    respx.get("http://finops.local/v1/finops/cost-reports/acme").mock(
        return_value=httpx.Response(200, json={
            "tenant_id": "acme", "period": "monthly", "llm_gateway_spend": 10.0, "other_usage_cost": 0.0,
            "total_cost": 10.0, "forecast_amount": None, "budget_policy": None, "utilisation_ratio": 0.42,
            "alert": False,
        })
    )
    client = HTTPFinOpsClient("http://finops.local")

    ratio = await client.cost_report_utilisation(tenant_id="acme", period="monthly", budget_policy_id="bp1")

    assert ratio == 0.42


@respx.mock
async def test_cost_report_utilisation_returns_none_on_unknown_budget_policy():
    respx.get("http://finops.local/v1/finops/cost-reports/acme").mock(return_value=httpx.Response(404))
    client = HTTPFinOpsClient("http://finops.local")

    ratio = await client.cost_report_utilisation(tenant_id="acme", period="monthly", budget_policy_id="does-not-exist")

    assert ratio is None

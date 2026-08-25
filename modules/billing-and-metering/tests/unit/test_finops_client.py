"""Tests for clients/finops_client.py -- calls FinOps's real GET
/v1/finops/cost-reports/{tenant_id} endpoint shape."""
from __future__ import annotations

import httpx
import respx

from billing_and_metering.clients.finops_client import HTTPFinOpsClient


@respx.mock
async def test_get_total_cost_reads_the_real_cost_report_shape():
    route = respx.get("http://finops.local/v1/finops/cost-reports/acme").mock(
        return_value=httpx.Response(200, json={
            "tenant_id": "acme", "period": "monthly", "llm_gateway_spend": 80.0, "other_usage_cost": 20.0,
            "total_cost": 100.0, "forecast_amount": None, "budget_policy": None,
            "utilisation_ratio": None, "alert": False,
        })
    )
    client = HTTPFinOpsClient("http://finops.local")

    total = await client.get_total_cost(tenant_id="acme", period="monthly")

    assert total == 100.0
    assert route.called
    assert route.calls.last.request.url.params["period"] == "monthly"

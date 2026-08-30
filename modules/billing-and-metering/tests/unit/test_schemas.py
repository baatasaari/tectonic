"""NUL-byte rejection on request schemas whose string fields land in a
Postgres `text`/`json` column -- the real bug the contract-test tier
(`tests/contract/test_openapi_contract.py`) caught: schema-valid `str`
input (OpenAPI's `type: string` says nothing about NUL) that crashed the
database with an unhandled `CharacterNotInRepertoireError` instead of a
clean `422`.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from billing_and_metering.schemas.billing_and_metering import (
    CreatePricingPlanRequest,
    GenerateInvoiceRequest,
)


def test_pricing_plan_name_with_null_byte_is_rejected():
    with pytest.raises(ValidationError):
        CreatePricingPlanRequest(tenant_id="tenant-a", name="bad\x00name", unit_prices={})


def test_pricing_plan_tenant_id_with_null_byte_is_rejected():
    with pytest.raises(ValidationError):
        CreatePricingPlanRequest(tenant_id="bad\x00tenant", name="ok", unit_prices={})


def test_pricing_plan_unit_price_key_with_null_byte_is_rejected():
    with pytest.raises(ValidationError):
        CreatePricingPlanRequest(tenant_id="tenant-a", name="ok", unit_prices={"bad\x00key": 1.0})


def test_pricing_plan_without_null_bytes_is_accepted():
    request = CreatePricingPlanRequest(tenant_id="tenant-a", name="ok", unit_prices={"tokens": 0.01})
    assert request.name == "ok"


def test_generate_invoice_tenant_id_with_null_byte_is_rejected():
    with pytest.raises(ValidationError):
        GenerateInvoiceRequest(tenant_id="bad\x00tenant", period="monthly")


def test_generate_invoice_without_null_bytes_is_accepted():
    request = GenerateInvoiceRequest(tenant_id="tenant-a", period="monthly")
    assert request.tenant_id == "tenant-a"

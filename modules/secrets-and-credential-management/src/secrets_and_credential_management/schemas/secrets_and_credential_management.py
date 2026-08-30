"""Request/response models for `/v1/secrets/*` (LLD §3).

Every metadata schema here (`SecretSchema`, `SecretListResponse`,
`AccessRecordSchema`) deliberately carries no ciphertext and no
plaintext value -- `RetrieveSecretResponse` is the one, single response
shape in this module allowed to carry a plaintext `value`, and only
when `allowed` is true.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateSecretRequest(BaseModel):
    tenant_id: str
    namespace: str
    key_name: str
    value: str
    rotation_interval_days: int = 90


class SecretSchema(BaseModel):
    id: str
    tenant_id: str
    namespace: str
    key_name: str
    status: str
    rotation_interval_days: int
    last_rotated_at: datetime
    next_rotation_due_at: datetime
    current_version: int
    created_at: datetime
    updated_at: datetime


class SecretListResponse(BaseModel):
    items: list[SecretSchema]
    total: int
    limit: int
    offset: int


class RetrieveSecretRequest(BaseModel):
    token: str


class RetrieveSecretResponse(BaseModel):
    allowed: bool
    reason: str
    value: str | None = None


class RotateSecretRequest(BaseModel):
    new_value: str


class AccessRecordSchema(BaseModel):
    id: str
    secret_id: str
    tenant_id: str
    allowed: bool
    reason: str
    accessed_at: datetime


class AccessRecordListResponse(BaseModel):
    items: list[AccessRecordSchema]
    total: int
    limit: int
    offset: int


class ComplianceReportSchema(BaseModel):
    tenant_id: str | None
    total_active: int
    overdue: int
    compliance_rate: float | None

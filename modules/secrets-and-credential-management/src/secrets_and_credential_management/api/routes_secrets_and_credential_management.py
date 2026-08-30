"""`/v1/secrets/*` routes (LLD §3).

Route ordering matters: the fixed-path collection routes
(`/due-for-rotation`, `/compliance`) are declared before the
`/{secret_id}` parameterized routes, so FastAPI never mistakes
"due-for-rotation" or "compliance" for a secret id.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from secrets_and_credential_management.api.deps import (
    build_rotation_service,
    build_secret_access_service,
    build_secret_registry_service,
    get_ctx,
    get_repository,
)
from secrets_and_credential_management.app_context import AppContext
from secrets_and_credential_management.core.domain import (
    InvalidTransitionError,
    SecretNotFoundError,
    SecretRevokedError,
    SecretStatus,
)
from secrets_and_credential_management.core.ports import SecretsRepository
from secrets_and_credential_management.schemas.secrets_and_credential_management import (
    AccessRecordListResponse,
    AccessRecordSchema,
    ComplianceReportSchema,
    CreateSecretRequest,
    RetrieveSecretRequest,
    RetrieveSecretResponse,
    RotateSecretRequest,
    SecretListResponse,
    SecretSchema,
)

router = APIRouter(prefix="/v1/secrets", tags=["secrets"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _secret_schema(secret) -> SecretSchema:
    return SecretSchema(
        id=secret.id, tenant_id=secret.tenant_id, namespace=secret.namespace, key_name=secret.key_name,
        status=secret.status.value, rotation_interval_days=secret.rotation_interval_days,
        last_rotated_at=secret.last_rotated_at, next_rotation_due_at=secret.next_rotation_due_at,
        current_version=secret.current_version, created_at=secret.created_at, updated_at=secret.updated_at,
    )


def _access_schema(record) -> AccessRecordSchema:
    return AccessRecordSchema(
        id=record.id, secret_id=record.secret_id, tenant_id=record.tenant_id, allowed=record.allowed,
        reason=record.reason, accessed_at=record.accessed_at,
    )


@router.post("", response_model=SecretSchema, status_code=201)
async def create_secret(
    body: CreateSecretRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretSchema:
    service = build_secret_registry_service(repository, ctx)
    secret = await service.create_secret(
        tenant_id=body.tenant_id, namespace=body.namespace, key_name=body.key_name, value=body.value,
        rotation_interval_days=body.rotation_interval_days,
    )
    return _secret_schema(secret)


@router.get("", response_model=SecretListResponse)
async def list_secrets(
    tenant_id: str | None = Query(None),
    namespace: str | None = Query(None),
    status: SecretStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, namespace=namespace)
    service = build_secret_registry_service(repository, ctx)
    secrets, total = await service.list_secrets(
        tenant_id=tenant_id, namespace=namespace, status=status, limit=limit, offset=offset,
    )
    return SecretListResponse(items=[_secret_schema(s) for s in secrets], total=total, limit=limit, offset=offset)


@router.get("/due-for-rotation", response_model=SecretListResponse)
async def list_due_for_rotation(
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_rotation_service(repository, ctx)
    secrets, total = await service.list_due_for_rotation(tenant_id=tenant_id, limit=limit, offset=offset)
    return SecretListResponse(items=[_secret_schema(s) for s in secrets], total=total, limit=limit, offset=offset)


@router.get("/compliance", response_model=ComplianceReportSchema)
async def get_compliance(
    tenant_id: str | None = Query(None),
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> ComplianceReportSchema:
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_rotation_service(repository, ctx)
    report = await service.compliance_rate(tenant_id=tenant_id)
    return ComplianceReportSchema(
        tenant_id=report.tenant_id, total_active=report.total_active, overdue=report.overdue,
        compliance_rate=report.compliance_rate,
    )


@router.get("/{secret_id}", response_model=SecretSchema)
async def get_secret(
    secret_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretSchema:
    service = build_secret_registry_service(repository, ctx)
    try:
        secret = await service.get_secret(secret_id)
    except SecretNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _secret_schema(secret)


@router.post("/{secret_id}/revoke", response_model=SecretSchema)
async def revoke_secret(
    secret_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretSchema:
    service = build_secret_registry_service(repository, ctx)
    try:
        secret = await service.revoke_secret(secret_id)
    except SecretNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _secret_schema(secret)


@router.post("/{secret_id}/rotate", response_model=SecretSchema)
async def rotate_secret(
    secret_id: str,
    body: RotateSecretRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> SecretSchema:
    service = build_rotation_service(repository, ctx)
    try:
        secret = await service.rotate(secret_id=secret_id, new_value=body.new_value)
    except SecretNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecretRevokedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _secret_schema(secret)


@router.post("/{secret_id}/retrieve", response_model=RetrieveSecretResponse)
async def retrieve_secret(
    secret_id: str,
    body: RetrieveSecretRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: SecretsRepository = Depends(get_repository),
) -> RetrieveSecretResponse:
    service = build_secret_access_service(repository, ctx)
    result = await service.retrieve(secret_id=secret_id, token=body.token)
    return RetrieveSecretResponse(allowed=result.allowed, reason=result.reason, value=result.value)


@router.get("/{secret_id}/access-log", response_model=AccessRecordListResponse)
async def list_access_log(
    secret_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: SecretsRepository = Depends(get_repository),
) -> AccessRecordListResponse:
    records, total = await repository.list_access_records(secret_id=secret_id, limit=limit, offset=offset)
    return AccessRecordListResponse(
        items=[_access_schema(r) for r in records], total=total, limit=limit, offset=offset,
    )

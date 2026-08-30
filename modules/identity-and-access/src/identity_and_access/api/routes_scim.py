"""SCIM 2.0 provisioning endpoints (RFC 7644), mounted outside
`/v1/identity-access` at the SCIM-conventional `/scim/v2/{tenant_id}/...`
path shape. Authenticated by `security/scim_auth.py`'s own per-tenant
bearer token, not the platform's `ServiceAuthMiddleware` -- see that
middleware's own docstring (`security/jwt_auth.py`) for why, and
`security/openapi_security.py` for how the generated OpenAPI document
reflects it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from identity_and_access.api.deps import get_repository
from identity_and_access.core.domain import (
    GroupNotFoundError,
    GroupRecord,
    IdentityNotFoundError,
    IdentityRecord,
    IdentityStatus,
    InvalidTransitionError,
    ScimConflictError,
)
from identity_and_access.core.ports import IdentityAccessRepository
from identity_and_access.core.scim_service import (
    ScimGroupService,
    ScimUserService,
    parse_username_filter,
)
from identity_and_access.schemas.scim import (
    GROUP_SCHEMA,
    LIST_RESPONSE_SCHEMA,
    USER_SCHEMA,
    ScimListResponse,
    ScimMeta,
    ScimName,
    ScimPatchOp,
    ScimUser,
)
from identity_and_access.security.scim_auth import require_scim_token

router = APIRouter(prefix="/scim/v2/{tenant_id}", tags=["scim"])


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


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _user_dict(identity: IdentityRecord, *, tenant_id: str) -> dict[str, Any]:
    return ScimUser(
        id=identity.id, userName=identity.email or identity.name, name=ScimName(formatted=identity.name),
        displayName=identity.name, active=identity.status == IdentityStatus.ACTIVE,
        meta=ScimMeta(
            resourceType="User", created=_iso(identity.created_at), lastModified=_iso(identity.updated_at),
            location=f"/scim/v2/{tenant_id}/Users/{identity.id}",
        ),
    ).model_dump()


def _group_dict(group: GroupRecord, *, tenant_id: str) -> dict[str, Any]:
    from identity_and_access.schemas.scim import ScimGroup, ScimGroupMember

    return ScimGroup(
        id=group.id, displayName=group.name,
        members=[ScimGroupMember(value=m) for m in group.member_identity_ids],
        meta=ScimMeta(
            resourceType="Group", created=_iso(group.created_at), lastModified=_iso(group.created_at),
            location=f"/scim/v2/{tenant_id}/Groups/{group.id}",
        ),
    ).model_dump()


# -- Users --

@router.post("/Users", status_code=201)
async def create_user(
    body: dict[str, Any],
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimUserService(repository)
    try:
        identity = await service.create(
            tenant_id=tenant_id, user_name=body.get("userName", ""),
            display_name=body.get("displayName") or (body.get("name") or {}).get("formatted", ""),
            active=body.get("active", True),
        )
    except ScimConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _user_dict(identity, tenant_id=tenant_id)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimUserService(repository)
    try:
        identity = await service.get(tenant_id=tenant_id, identity_id=user_id)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _user_dict(identity, tenant_id=tenant_id)


@router.get("/Users")
async def list_users(
    filter: str | None = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(50, ge=1, le=200),
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    _reject_null_byte_query(filter=filter)
    service = ScimUserService(repository)
    user_name = parse_username_filter(filter)
    identities, total = await service.list(
        tenant_id=tenant_id, user_name=user_name, limit=count, offset=startIndex - 1,
    )
    return ScimListResponse(
        totalResults=total, startIndex=startIndex, itemsPerPage=len(identities),
        Resources=[_user_dict(i, tenant_id=tenant_id) for i in identities],
    ).model_dump()


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    body: dict[str, Any],
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimUserService(repository)
    try:
        identity = await service.replace(
            tenant_id=tenant_id, identity_id=user_id, user_name=body.get("userName", ""),
            display_name=body.get("displayName") or (body.get("name") or {}).get("formatted", ""),
            active=body.get("active", True),
        )
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _user_dict(identity, tenant_id=tenant_id)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    body: ScimPatchOp,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimUserService(repository)
    try:
        identity = await service.patch(
            tenant_id=tenant_id, identity_id=user_id,
            operations=[op.model_dump() for op in body.Operations],
        )
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _user_dict(identity, tenant_id=tenant_id)


@router.delete("/Users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> None:
    service = ScimUserService(repository)
    try:
        await service.deactivate(tenant_id=tenant_id, identity_id=user_id)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -- Groups --

@router.post("/Groups", status_code=201)
async def create_group(
    body: dict[str, Any],
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimGroupService(repository)
    member_ids = [m.get("value") for m in body.get("members", []) if m.get("value")]
    group = await service.create(tenant_id=tenant_id, display_name=body.get("displayName", ""), member_ids=member_ids)
    return _group_dict(group, tenant_id=tenant_id)


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimGroupService(repository)
    try:
        group = await service.get(tenant_id=tenant_id, group_id=group_id)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _group_dict(group, tenant_id=tenant_id)


@router.get("/Groups")
async def list_groups(
    startIndex: int = Query(1, ge=1),
    count: int = Query(50, ge=1, le=200),
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimGroupService(repository)
    groups, total = await service.list(tenant_id=tenant_id, limit=count, offset=startIndex - 1)
    return ScimListResponse(
        totalResults=total, startIndex=startIndex, itemsPerPage=len(groups),
        Resources=[_group_dict(g, tenant_id=tenant_id) for g in groups],
    ).model_dump()


@router.put("/Groups/{group_id}")
async def replace_group(
    group_id: str,
    body: dict[str, Any],
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimGroupService(repository)
    member_ids = [m.get("value") for m in body.get("members", []) if m.get("value")]
    try:
        group = await service.replace(
            tenant_id=tenant_id, group_id=group_id, display_name=body.get("displayName", ""), member_ids=member_ids,
        )
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _group_dict(group, tenant_id=tenant_id)


@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: str,
    body: ScimPatchOp,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> dict[str, Any]:
    service = ScimGroupService(repository)
    try:
        group = await service.patch(
            tenant_id=tenant_id, group_id=group_id,
            operations=[op.model_dump() for op in body.Operations],
        )
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _group_dict(group, tenant_id=tenant_id)


@router.delete("/Groups/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    tenant_id: str = Depends(require_scim_token),
    repository: IdentityAccessRepository = Depends(get_repository),
) -> None:
    service = ScimGroupService(repository)
    try:
        await service.delete(tenant_id=tenant_id, group_id=group_id)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["GROUP_SCHEMA", "LIST_RESPONSE_SCHEMA", "USER_SCHEMA", "router"]

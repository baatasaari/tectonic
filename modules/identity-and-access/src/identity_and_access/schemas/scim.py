"""SCIM 2.0 (RFC 7643 §4, RFC 7644 §3.4) wire shapes: real `schemas`
arrays, `meta`, `ListResponse`, `PatchOp` -- not an ad hoc subset. Kept
separate from `schemas/identity_and_access.py` (this module's own,
non-standard REST shapes) since SCIM's field names (`userName`,
`displayName`, camelCase throughout) are dictated by the spec, not this
module's usual snake_case convention.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class ScimMeta(BaseModel):
    resourceType: str
    created: str
    lastModified: str
    location: str = ""


class ScimName(BaseModel):
    formatted: str = ""


class ScimUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = [USER_SCHEMA]
    id: str
    userName: str
    name: ScimName = ScimName()
    displayName: str = ""
    active: bool
    meta: ScimMeta


class ScimGroupMember(BaseModel):
    value: str
    display: str = ""


class ScimGroup(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schemas: list[str] = [GROUP_SCHEMA]
    id: str
    displayName: str
    members: list[ScimGroupMember] = []
    meta: ScimMeta


class ScimListResponse(BaseModel):
    schemas: list[str] = [LIST_RESPONSE_SCHEMA]
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[dict[str, Any]]


class ScimPatchOperation(BaseModel):
    op: str
    path: str | None = None
    value: Any = None


class ScimPatchOp(BaseModel):
    schemas: list[str] = [PATCH_OP_SCHEMA]
    Operations: list[ScimPatchOperation] = Field(default_factory=list)


class ScimError(BaseModel):
    schemas: list[str] = [ERROR_SCHEMA]
    status: str
    detail: str

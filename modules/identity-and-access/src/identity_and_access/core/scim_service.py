"""SCIM 2.0 (RFC 7643/7644) resource lifecycle for Users and Groups --
the business logic behind `api/routes_scim.py`. Maps this module's
existing `IdentityRecord`/`GroupRecord` onto the SCIM resource model
rather than introducing parallel storage: a SCIM User *is* an
`IdentityRecord` (`type=USER`), correlated by `email` (SCIM's
`userName`, since this module has no separate "SCIM external ID" field
-- `external_provider_id`/`external_subject` are OIDC's own correlation
key, deliberately not reused here so a SCIM-provisioned user and an
OIDC-federated login for the same person don't silently collide on a
field neither of them agrees on the meaning of); a SCIM Group is a
`GroupRecord` with `provider_id="scim"` (a plain string field, not a
foreign key to `IdentityProviderRecord` -- SCIM provisioning needs no
registered OIDC/SAML provider at all).

**Deliberately bounded, not the full SCIM grammar.** Two real
simplifications, both because most SCIM clients in practice only ever
need the common case:

- `filter=` query parsing supports exactly `userName eq "value"`
  (the load-bearing case every IdP uses to check for an existing user
  before POSTing a duplicate) and nothing else -- no `and`/`or`, no
  other operators, no other attributes. A more complete filter grammar
  is real, separate work.
- `PATCH` on a User supports `replace` of `active`, `userName`, and
  `name`/`displayName`-shaped paths; on a Group, `add`/`remove`/`replace`
  of `members`. Any other op/path is accepted but ignored rather than
  rejected -- SCIM clients routinely send attributes (`meta`,
  `schemas`) inside patch bodies that aren't meant to change anything;
  rejecting the whole request over an attribute we don't act on would
  break real IdPs.
"""
from __future__ import annotations

import re
from typing import Any

from identity_and_access.core.domain import (
    GroupNotFoundError,
    GroupRecord,
    IdentityNotFoundError,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    InvalidTransitionError,
    ScimConflictError,
    is_legal_transition,
    new_id,
    now,
)
from identity_and_access.core.ports import IdentityAccessRepository

SCIM_PROVIDER_ID = "scim"

_USERNAME_EQ_RE = re.compile(r'userName\s+eq\s+"([^"]*)"', re.IGNORECASE)


def parse_username_filter(filter_expr: str | None) -> str | None:
    """Returns the filtered userName value, or None if `filter_expr`
    isn't the one supported shape -- see module docstring."""
    if not filter_expr:
        return None
    match = _USERNAME_EQ_RE.search(filter_expr)
    return match.group(1) if match else None


class ScimUserService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def create(self, *, tenant_id: str, user_name: str, display_name: str, active: bool = True) -> IdentityRecord:
        existing, _ = await self._repository.list_identities(tenant_id=tenant_id, limit=10_000)
        if any(i.email == user_name for i in existing):
            raise ScimConflictError(f"userName already provisioned: {user_name}")

        record = IdentityRecord(
            id=new_id(), tenant_id=tenant_id, name=display_name or user_name, type=IdentityType.USER,
            status=IdentityStatus.ACTIVE if active else IdentityStatus.REVOKED, email=user_name,
        )
        return await self._repository.create_identity(record)

    async def get(self, *, tenant_id: str, identity_id: str) -> IdentityRecord:
        record = await self._repository.get_identity(identity_id)
        if record is None or record.tenant_id != tenant_id:
            raise IdentityNotFoundError(identity_id)
        return record

    async def list(
        self, *, tenant_id: str, user_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IdentityRecord], int]:
        results, _ = await self._repository.list_identities(tenant_id=tenant_id, limit=10_000)
        results = [r for r in results if r.type == IdentityType.USER]
        if user_name is not None:
            results = [r for r in results if r.email == user_name]
        return results[offset:offset + limit], len(results)

    async def replace(
        self, *, tenant_id: str, identity_id: str, user_name: str, display_name: str, active: bool,
    ) -> IdentityRecord:
        record = await self.get(tenant_id=tenant_id, identity_id=identity_id)
        record.email = user_name
        record.name = display_name or user_name
        await self._apply_active(record, active)
        record.updated_at = now()
        return await self._repository.update_identity(record)

    async def patch(self, *, tenant_id: str, identity_id: str, operations: list[dict[str, Any]]) -> IdentityRecord:
        record = await self.get(tenant_id=tenant_id, identity_id=identity_id)
        for op in operations:
            path = (op.get("path") or "").strip().lower()
            value = op.get("value")
            if path == "active" and isinstance(value, bool):
                await self._apply_active(record, value)
            elif path == "username" and isinstance(value, str):
                record.email = value
            elif path in ("displayname", "name.formatted", "") and isinstance(value, str):
                record.name = value
            elif path == "" and isinstance(value, dict):
                if "active" in value and isinstance(value["active"], bool):
                    await self._apply_active(record, value["active"])
                if "userName" in value:
                    record.email = value["userName"]
                if "displayName" in value:
                    record.name = value["displayName"]
        record.updated_at = now()
        return await self._repository.update_identity(record)

    async def _apply_active(self, record: IdentityRecord, active: bool) -> None:
        target = IdentityStatus.ACTIVE if active else IdentityStatus.REVOKED
        if record.status == target:
            return
        if not is_legal_transition(record.status, target):
            raise InvalidTransitionError(record.status, target)
        record.status = target

    async def deactivate(self, *, tenant_id: str, identity_id: str) -> IdentityRecord:
        """SCIM's `DELETE /Users/{id}` -- deprovisioning. Deactivates
        rather than hard-deletes, the same revoke-don't-erase posture
        `IdentityRegistryService.revoke` already takes: an identity's
        audit trail (auth_decisions, group membership history) must
        survive an IdP unassigning someone."""
        record = await self.get(tenant_id=tenant_id, identity_id=identity_id)
        await self._apply_active(record, False)
        record.updated_at = now()
        return await self._repository.update_identity(record)


class ScimGroupService:
    def __init__(self, repository: IdentityAccessRepository) -> None:
        self._repository = repository

    async def create(self, *, tenant_id: str, display_name: str, member_ids: list[str] | None = None) -> GroupRecord:
        record = GroupRecord(
            id=new_id(), tenant_id=tenant_id, provider_id=SCIM_PROVIDER_ID, external_id=new_id(), name=display_name,
            member_identity_ids=member_ids or [],
        )
        return await self._repository.create_group(record)

    async def get(self, *, tenant_id: str, group_id: str) -> GroupRecord:
        record = await self._repository.get_group(group_id)
        if record is None or record.tenant_id != tenant_id:
            raise GroupNotFoundError(group_id)
        return record

    async def list(self, *, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[list[GroupRecord], int]:
        return await self._repository.list_groups(tenant_id=tenant_id, limit=limit, offset=offset)

    async def replace(self, *, tenant_id: str, group_id: str, display_name: str, member_ids: list[str]) -> GroupRecord:
        from identity_and_access.core.group_service import GroupService

        record = await self.get(tenant_id=tenant_id, group_id=group_id)
        record.name = display_name
        group_service = GroupService(self._repository)
        await self._repository.update_group(record)
        return await group_service.set_members(group_id, member_ids)

    async def patch(self, *, tenant_id: str, group_id: str, operations: list[dict[str, Any]]) -> GroupRecord:
        from identity_and_access.core.group_service import GroupService

        record = await self.get(tenant_id=tenant_id, group_id=group_id)
        members = set(record.member_identity_ids)
        group_service = GroupService(self._repository)

        for op in operations:
            action = (op.get("op") or "").strip().lower()
            path = (op.get("path") or "").strip()
            value = op.get("value")

            if action == "add" and path.startswith("members") or (action == "add" and not path):
                for entry in value or []:
                    member_id = entry.get("value") if isinstance(entry, dict) else entry
                    if member_id:
                        members.add(member_id)
            elif action == "remove":
                single = re.search(r'members\[value\s+eq\s+"([^"]*)"\]', path, re.IGNORECASE)
                if single:
                    members.discard(single.group(1))
                elif path in ("members", ""):
                    if value:
                        for entry in value:
                            member_id = entry.get("value") if isinstance(entry, dict) else entry
                            members.discard(member_id)
                    else:
                        members.clear()
            elif action == "replace" and path in ("members", ""):
                members = set()
                for entry in value or []:
                    member_id = entry.get("value") if isinstance(entry, dict) else entry
                    if member_id:
                        members.add(member_id)
            elif action == "replace" and path == "displayname" and isinstance(value, str):
                record.name = value
                await self._repository.update_group(record)

        return await group_service.set_members(group_id, sorted(members))

    async def delete(self, *, tenant_id: str, group_id: str) -> None:
        """SCIM's `DELETE /Groups/{id}`. Clears membership (so every
        affected identity's `federated_role_names` recomputes correctly,
        losing whatever this group granted) but does not hard-delete the
        `GroupRecord` row -- IdentityAccessRepository has no delete_group
        method, the same soft-delete-only posture this module already
        takes for identities (revoke, never erase). The empty, orphaned
        group record is a real, small, documented gap rather than
        silently one this endpoint can't actually satisfy per spec."""
        from identity_and_access.core.group_service import GroupService

        await self.get(tenant_id=tenant_id, group_id=group_id)
        group_service = GroupService(self._repository)
        await group_service.set_members(group_id, [])

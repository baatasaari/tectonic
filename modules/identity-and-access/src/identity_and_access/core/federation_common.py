"""JIT-provisioning logic shared between OIDC and SAML federation.

Once a protocol-specific verifier has produced a trusted
`(subject, email, name, group_external_ids)` tuple, provisioning or
updating the matching `IdentityRecord` is identical either way -- look
up by `(tenant_id, provider_id, external_subject)`, never by email;
resolve the token/assertion's current group membership to a
`federated_role_names` list; create on first login, refresh on every
subsequent one. Extracted here once rather than duplicated between
`core/oidc_federation_service.py` and `core/saml_federation_service.py`,
so a fix to this logic never has to land in two places.
"""
from __future__ import annotations

from identity_and_access.core.domain import IdentityRecord, IdentityType, new_id, now
from identity_and_access.core.ports import IdentityAccessRepository


async def resolve_group_roles(
    repository: IdentityAccessRepository, *, tenant_id: str, provider_id: str, group_external_ids: list[str],
) -> list[str]:
    role_names: set[str] = set()
    for external_id in group_external_ids:
        group = await repository.find_group_by_external_id(
            tenant_id=tenant_id, provider_id=provider_id, external_id=external_id,
        )
        if group is not None:
            role_names.update(group.default_role_names)
    return sorted(role_names)


async def jit_provision_or_update_identity(
    repository: IdentityAccessRepository,
    *,
    tenant_id: str,
    provider_id: str,
    subject: str,
    email: str | None,
    name: str,
    federated_role_names: list[str],
) -> IdentityRecord:
    existing = await repository.find_identity_by_external_subject(
        tenant_id=tenant_id, provider_id=provider_id, external_subject=subject,
    )
    if existing is None:
        record = IdentityRecord(
            id=new_id(), tenant_id=tenant_id, name=name, type=IdentityType.USER, email=email,
            external_provider_id=provider_id, external_subject=subject,
            federated_role_names=federated_role_names,
        )
        return await repository.create_identity(record)

    existing.name = name
    existing.email = email
    existing.federated_role_names = federated_role_names
    existing.updated_at = now()
    return await repository.update_identity(existing)

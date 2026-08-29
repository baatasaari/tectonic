"""Event topic name and CloudEvents-shaped envelope builders for this
module's Tenant lifecycle events (independent architecture assessment
§3.3 "Add an event backbone"). This is the rollout of Workflow Engine's
own reference implementation (Module 1, `core/events.py`) to a second
module -- see that module's own docstring for the full CloudEvents v1.0
reasoning (`specversion`/`id`/`source`/`type`/`subject`/`time`/
`datacontenttype`/`data` core attributes plus `tenant_id`/
`environment_id`/`correlation_id`/`causation_id` extension attributes,
`id` doubling as the delivery idempotency key, `type` namespaced
`com.tectonic.<event>`).

Both events here -- `tenant.registered` and `tenant.status_changed` --
get real outbox-grade guaranteed delivery: `TenantRegistryService`
writes each envelope to `event_outbox` in the same DB transaction as
the tenant row's own create/update (see
`MultiTenancyRepository.create_tenant_and_enqueue_event`/
`.update_tenant_and_enqueue_event`), and `OutboxRelayWorker`
(core/outbox_worker.py) actually delivers them. Organisation/Workspace/
Environment lifecycle transitions deliberately stay on the pre-existing
best-effort `HTTPAuditabilityClient.emit` path -- Tenant is this
module's own top-level instance-lifecycle analogue (the entity other
modules -- Billing and Metering, SDK and Developer Portal,
Observability -- most need a durability guarantee on), the identical
scoped-not-oversight choice Workflow Engine's own step/approval/replan
events already made. Extending outbox-grade delivery to the hierarchy
levels below Tenant is separate, unbuilt follow-up work -- see this
module's README.
"""
from __future__ import annotations

import uuid
from typing import Any

from multi_tenancy.core.domain import now

CLOUDEVENTS_SPECVERSION = "1.0"
SOURCE = "tectonic://multi-tenancy"

TOPIC_TENANT = "tenant.lifecycle"


def envelope(
    event_type: str, *, tenant_id: str, subject: str, causation_id: str | None = None, data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "specversion": CLOUDEVENTS_SPECVERSION,
        "id": str(uuid.uuid4()),
        "source": SOURCE,
        "type": f"com.tectonic.{event_type}",
        "subject": subject,
        "time": now().isoformat(),
        "datacontenttype": "application/json",
        "tenant_id": tenant_id,
        "environment_id": None,
        "correlation_id": None,
        "causation_id": causation_id,
        "data": data,
    }


def tenant_registered(tenant_id: str, name: str, tier: str, organisation_id: str | None) -> dict[str, Any]:
    return envelope(
        "tenant.registered", tenant_id=tenant_id, subject=tenant_id,
        data={"tenant_id": tenant_id, "name": name, "tier": tier, "organisation_id": organisation_id},
    )


def tenant_status_changed(tenant_id: str, from_status: str, to_status: str) -> dict[str, Any]:
    return envelope(
        "tenant.status_changed", tenant_id=tenant_id, subject=tenant_id,
        data={"tenant_id": tenant_id, "from_status": from_status, "to_status": to_status},
    )

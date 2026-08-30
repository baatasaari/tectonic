"""Audit Pack Generator (LLD §2 sub-components): renders a filtered,
chronologically ordered export of this module's own event log as a
PDF/JSON artifact, plus its own chain-verification result -- a generic,
framework-agnostic evidentiary export, distinct from Module 17's
framework-specific evidence pack (see the module README).

Real PDF bytes via `fpdf2`, the same library Module 17's evidence packs
already use -- no deviation needed here, unlike most of this platform's
document-shaped features.
"""
from __future__ import annotations

import base64
import json as jsonlib

from auditability.core.chain_verifier import verify_chain
from auditability.core.domain import (
    AuditEventFilter,
    AuditEventRecord,
    AuditPackNotFoundError,
    AuditPackRecord,
    AuditPackStatus,
    now,
)
from auditability.core.ports import AuditabilityRepository
from auditability.telemetry.logging import get_logger

logger = get_logger(component="audit_pack_generator")

_UNBOUNDED_PAGE_SIZE = 10_000  # internal caller needing the *complete* filtered set, not one API page


class AuditPackGenerator:
    def __init__(self, repository: AuditabilityRepository, output_format: str = "pdf") -> None:
        self._repository = repository
        self._output_format = output_format

    async def generate(self, pack_id: str, tenant_id: str) -> AuditPackRecord:
        pack = await self._repository.get_audit_pack(tenant_id, pack_id)
        if pack is None:
            raise AuditPackNotFoundError(pack_id)

        try:
            event_filter = AuditEventFilter(
                tenant_id=tenant_id, event_type=pack.filter_event_type, source_module=pack.filter_source_module,
                control_name=pack.filter_control_name, occurred_after=pack.filter_occurred_after,
                occurred_before=pack.filter_occurred_before, limit=_UNBOUNDED_PAGE_SIZE,
            )
            events, _total = await self._repository.list_events(event_filter)
            # This pack's own integrity proof: the *tenant's full chain* must verify, not
            # just the filtered subset in this pack -- a filtered slice's own hashes still
            # reference entries outside it via prev_hash, so verifying only the slice would
            # report false breaks at its own boundaries.
            chain_events = await self._repository.list_events_for_chain(tenant_id)
            chain_result = verify_chain(chain_events)

            document_bytes, ext = self._render(tenant_id, events, chain_result.valid)
            pack.status = AuditPackStatus.COMPLETED
            pack.generated_at = now()
            pack.event_count = len(events)
            pack.chain_valid = chain_result.valid
            pack.document_format = ext
            pack.document_ref = f"audit-packs/{pack.id}.{ext}"
            pack.document_bytes_b64 = base64.b64encode(document_bytes).decode("ascii")
            pack.last_error = None
        except Exception as exc:
            pack.status = AuditPackStatus.FAILED
            pack.last_error = str(exc) or exc.__class__.__name__
            logger.exception("audit_pack_generation_failed", pack_id=pack_id)

        return await self._repository.update_audit_pack(pack)

    def _render(self, tenant_id: str, events: list[AuditEventRecord], chain_valid: bool) -> tuple[bytes, str]:
        if self._output_format == "json":
            payload = {
                "tenant_id": tenant_id, "chain_valid": chain_valid, "event_count": len(events),
                "events": [
                    {
                        "sequence_number": e.sequence_number, "source_module": e.source_module,
                        "event_type": e.event_type, "payload": e.payload, "occurred_at": e.occurred_at.isoformat(),
                        "entry_hash": e.entry_hash,
                    }
                    for e in events
                ],
            }
            return jsonlib.dumps(payload, indent=2).encode("utf-8"), "json"
        return self._render_pdf(tenant_id, events, chain_valid), "pdf"

    def _render_pdf(self, tenant_id: str, events: list[AuditEventRecord], chain_valid: bool) -> bytes:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Audit Pack", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        pdf.cell(0, 8, f"Tenant: {tenant_id}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Events included: {len(events)}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Chain integrity: {'VALID' if chain_valid else 'BROKEN'}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Events", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        if events:
            for e in events:
                pdf.multi_cell(
                    0, 6,
                    f"#{e.sequence_number} [{e.event_type}] source={e.source_module} "
                    f"at={e.occurred_at.isoformat()} hash={e.entry_hash[:16]}...",
                    new_x="LMARGIN", new_y="NEXT",
                )
        else:
            pdf.cell(0, 6, "(none matching filter)", new_x="LMARGIN", new_y="NEXT")

        return bytes(pdf.output())

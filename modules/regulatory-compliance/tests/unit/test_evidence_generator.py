import base64
import json

from regulatory_compliance.core.domain import EvidencePackRecord, EvidencePackStatus, new_id
from regulatory_compliance.core.evidence_generator import EvidencePackGenerator


async def _seeded_harness(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")
    await harness.crosswalk_engine.map_control("t1", "human_oversight", "human_oversight", "ref-1")
    return harness


async def test_generate_json_pack_completes_with_coverage_and_content(harness):
    await _seeded_harness(harness)
    pack = await harness.repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )

    result = await harness.evidence_generator.generate(pack.id, "t1", "eu_ai_act")

    assert result.status == EvidencePackStatus.COMPLETED
    assert result.generated_at is not None
    assert 0.0 < result.coverage_percentage < 100.0
    assert result.document_format == "json"
    assert result.document_ref == f"evidence-packs/{pack.id}.json"

    payload = json.loads(base64.b64decode(result.document_bytes_b64))
    assert payload["framework_name"] == "eu_ai_act"
    assert payload["control_events"][0]["control_name"] == "human_oversight"


async def test_generate_pdf_pack_produces_valid_pdf_bytes(harness_factory):
    h = harness_factory(output_format="pdf")
    await _seeded_harness(h)
    pack = await h.repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )

    result = await h.evidence_generator.generate(pack.id, "t1", "eu_ai_act")

    assert result.status == EvidencePackStatus.COMPLETED
    assert result.document_format == "pdf"
    document_bytes = base64.b64decode(result.document_bytes_b64)
    assert document_bytes.startswith(b"%PDF")


async def test_generate_missing_pack_raises(harness):
    import pytest

    from regulatory_compliance.core.domain import EvidencePackNotFoundError

    with pytest.raises(EvidencePackNotFoundError):
        await harness.evidence_generator.generate("does-not-exist", "t1", "eu_ai_act")


async def test_generate_enriches_from_auditability_best_effort(harness):
    await _seeded_harness(harness)
    pack = await harness.repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )

    await harness.evidence_generator.generate(pack.id, "t1", "eu_ai_act")

    assert len(harness.auditability.calls) == 1
    assert harness.auditability.calls[0]["control_name"] == "human_oversight"


async def test_generate_failure_marks_pack_failed_without_raising():
    class BoomAuditabilityClient:
        async def query_control_events(self, tenant_id, control_name, date_range=None):
            raise RuntimeError("should not block generation")

    from regulatory_compliance.core.fakes import InMemoryRegulatoryComplianceRepository

    class BoomRepository(InMemoryRegulatoryComplianceRepository):
        async def list_control_mappings(self, *, control_name=None, framework_name=None, limit=50, offset=0):
            raise RuntimeError("boom")

    repository = BoomRepository()
    pack = await repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )
    generator = EvidencePackGenerator(repository, BoomAuditabilityClient(), "json")

    result = await generator.generate(pack.id, "t1", "eu_ai_act")

    assert result.status == EvidencePackStatus.FAILED

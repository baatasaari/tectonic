"""SQLAlchemy-backed implementation of GuardrailsRepository (LLD §3)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from guardrails.core.domain import (
    BypassIncidentRecord,
    CheckStage,
    Decision,
    InterventionLogRecord,
    PolicyProfileRecord,
    RedTeamRunRecord,
)
from guardrails.db import models


def _profile_to_domain(m: models.PolicyProfile) -> PolicyProfileRecord:
    return PolicyProfileRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, enabled_checks=list(m.enabled_checks or []),
        pii_entity_types=list(m.pii_entity_types or []), denied_topics=list(m.denied_topics or []),
        groundedness_threshold=m.groundedness_threshold, status=m.status, created_at=m.created_at,
    )


def _log_to_domain(m: models.InterventionLog) -> InterventionLogRecord:
    return InterventionLogRecord(
        id=str(m.id), tenant_id=m.tenant_id, policy_profile_id=str(m.policy_profile_id), stage=CheckStage(m.stage),
        check_type=m.check_type, decision=Decision(m.decision), violation_category=m.violation_category,
        latency_ms=m.latency_ms, created_at=m.created_at,
    )


def _run_to_domain(m: models.RedTeamRun) -> RedTeamRunRecord:
    return RedTeamRunRecord(
        id=str(m.id), tenant_id=m.tenant_id, attempts_generated=m.attempts_generated,
        successful_bypasses=m.successful_bypasses, run_at=m.run_at,
    )


def _incident_to_domain(m: models.BypassIncident) -> BypassIncidentRecord:
    return BypassIncidentRecord(
        id=str(m.id), red_team_run_id=str(m.red_team_run_id), attack_pattern=m.attack_pattern,
        target_check=m.target_check, severity=m.severity, resolved=m.resolved,
    )


class SQLAlchemyGuardrailsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_policy_profile(self, record: PolicyProfileRecord) -> PolicyProfileRecord:
        m = models.PolicyProfile(
            id=record.id, tenant_id=record.tenant_id, name=record.name, enabled_checks=record.enabled_checks,
            pii_entity_types=record.pii_entity_types, denied_topics=record.denied_topics,
            groundedness_threshold=record.groundedness_threshold, status=record.status,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _profile_to_domain(m)

    async def get_policy_profile(self, tenant_id: str, profile_id: str) -> PolicyProfileRecord | None:
        m = await self.session.get(models.PolicyProfile, profile_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _profile_to_domain(m)

    async def get_default_policy_profile(self, tenant_id: str) -> PolicyProfileRecord | None:
        rows = await self.session.execute(
            select(models.PolicyProfile)
            .where(models.PolicyProfile.tenant_id == tenant_id, models.PolicyProfile.status == "active")
            .order_by(models.PolicyProfile.created_at)
            .limit(1)
        )
        m = rows.scalars().first()
        return _profile_to_domain(m) if m else None

    async def create_intervention_log(self, record: InterventionLogRecord) -> InterventionLogRecord:
        m = models.InterventionLog(
            id=record.id, tenant_id=record.tenant_id, policy_profile_id=record.policy_profile_id,
            stage=record.stage.value, check_type=record.check_type, decision=record.decision.value,
            violation_category=record.violation_category, latency_ms=record.latency_ms,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _log_to_domain(m)

    async def create_red_team_run(self, record: RedTeamRunRecord) -> RedTeamRunRecord:
        m = models.RedTeamRun(
            id=record.id, tenant_id=record.tenant_id, attempts_generated=record.attempts_generated,
            successful_bypasses=record.successful_bypasses,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _run_to_domain(m)

    async def list_red_team_runs(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[RedTeamRunRecord], int]:
        where_clause = models.RedTeamRun.tenant_id == tenant_id
        rows = await self.session.execute(
            select(models.RedTeamRun)
            .where(where_clause)
            .order_by(models.RedTeamRun.run_at.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self.session.execute(select(func.count(models.RedTeamRun.id)).where(where_clause))
        return [_run_to_domain(m) for m in rows.scalars().all()], total.scalar_one()

    async def create_bypass_incident(self, record: BypassIncidentRecord) -> BypassIncidentRecord:
        m = models.BypassIncident(
            id=record.id, red_team_run_id=record.red_team_run_id, attack_pattern=record.attack_pattern,
            target_check=record.target_check, severity=record.severity, resolved=record.resolved,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _incident_to_domain(m)

    async def list_bypass_incidents(self, red_team_run_id: str) -> list[BypassIncidentRecord]:
        rows = await self.session.execute(
            select(models.BypassIncident).where(models.BypassIncident.red_team_run_id == red_team_run_id)
        )
        return [_incident_to_domain(m) for m in rows.scalars().all()]

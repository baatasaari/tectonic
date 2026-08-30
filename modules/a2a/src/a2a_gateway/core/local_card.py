"""Local Card Builder (LLD §2 sub-components): assembles this platform's
own published Agent Card, served at `/.well-known/agent.json`. The
skills it advertises are exactly the keys of `skill_definition_map` — a
skill this platform accepts inbound is, by construction, a skill it also
advertises outbound; there is no separate place the two could drift
apart.
"""
from __future__ import annotations

from a2a_gateway.config import A2AGatewaySettings
from a2a_gateway.core.domain import AgentCard, AgentSkill


def build_local_card(settings: A2AGatewaySettings) -> AgentCard:
    skills = [AgentSkill(id=skill_id, name=skill_id) for skill_id in settings.skill_definition_map]
    return AgentCard(
        name=settings.agent_name, description=settings.agent_description, url=settings.self_base_url, skills=skills,
    )

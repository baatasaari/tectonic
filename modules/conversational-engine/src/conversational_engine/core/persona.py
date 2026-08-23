"""Persona Engine (LLD §2.2): applies tone/persona configuration to prompts
sent to LLM Gateway, config-driven prompt templating. Also owns the
denied-topics check — catching an out-of-scope request here, before any LLM
Gateway call, is cheaper and more explainable than relying on Guardrails to
catch it after generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from conversational_engine.core.domain import MessageRecord, PersonaConfigRecord


@dataclass
class PromptBuildResult:
    denied_topic: str | None
    prompt_context: dict[str, Any] | None


class PersonaEngine:
    def build_prompt(
        self, persona: PersonaConfigRecord, history: list[MessageRecord], message: str
    ) -> PromptBuildResult:
        lowered = message.lower()
        for topic in persona.denied_topics:
            if topic.lower() in lowered:
                return PromptBuildResult(denied_topic=topic, prompt_context=None)

        prompt_context = {
            "persona_name": persona.name,
            "tone_settings": persona.tone_settings,
            "history": [
                {"direction": m.direction.value, "content": m.content} for m in history[-20:]
            ],
            "message": message,
        }
        if persona.allowed_topics:
            prompt_context["allowed_topics"] = persona.allowed_topics
        return PromptBuildResult(denied_topic=None, prompt_context=prompt_context)

"""OpenTelemetry tracing setup (LLD §Level 4 "Tracing"). Root trace per
ConversationSession (`trace_id`), one span per turn
(`conversation.turn.process`), attributes `session.id`, `channel`,
`emotion_score`, `guardrail_result`. Nested `gen_ai.*` spans from the LLM
Gateway call inherit the same trace context.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

_TRACER_NAME = "conversational_engine"


def configure_tracing(service_name: str, otlp_endpoint: str) -> None:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)))
    trace.set_tracer_provider(provider)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s


SPAN_CONVERSATION_TURN_PROCESS = "conversation.turn.process"

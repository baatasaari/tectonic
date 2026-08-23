"""OpenTelemetry tracing setup (LLD §4.1).

Root trace per WorkflowInstance, span names follow OTel GenAI semantic
conventions plus platform-specific extensions. ADK 2.0's built-in OTel
instrumentation emits the `gen_ai.*` spans inside the Neural Step Executor;
this module's spans wrap around them so a full trace shows workflow-level
context and agent-level detail as one continuous tree. Exported via OTLP so
it lands in whatever the customer already runs (Tempo/Jaeger/Datadog/etc.),
satisfying the cloud-agnostic requirement.
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

_TRACER_NAME = "workflow_engine"


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


# Span name constants (LLD §4.1 table).
SPAN_WORKFLOW_INSTANCE_EXECUTE = "workflow.instance.execute"
SPAN_WORKFLOW_STEP_EXECUTE = "workflow.step.execute"
SPAN_GEN_AI_AGENT_INVOKE = "gen_ai.agent.invoke"
SPAN_WORKFLOW_REPLAN_TRIGGER = "workflow.replan.trigger"
SPAN_WORKFLOW_APPROVAL_REQUEST = "workflow.approval.request"

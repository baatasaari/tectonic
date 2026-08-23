"""structlog configuration (LLD §4.2).

JSON line output; every log entry carries trace_id, tenant_id,
workflow_instance_id, step_id (where applicable), event, level. No prompt or
response content is logged at INFO — that goes to trace span attributes
instead, subject to Guardrails redaction policy. DEBUG may include truncated
content behind the per-tenant `debug_content_logging` feature flag, never on
by default in production.
"""
from __future__ import annotations

import logging

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: object) -> structlog.BoundLogger:
    return structlog.get_logger().bind(**initial_context)

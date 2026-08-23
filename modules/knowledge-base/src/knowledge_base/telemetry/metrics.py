"""Prometheus metrics (LLD §Level 4 "Metrics")."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

knowledge_base_documents_ingested_total = Counter(
    "knowledge_base_documents_ingested_total",
    "Count of documents ingested",
    labelnames=("tenant_id", "source_type"),
)

knowledge_base_ingestion_duration_seconds = Histogram(
    "knowledge_base_ingestion_duration_seconds",
    "Duration of a document ingestion",
    labelnames=("document_size_bucket",),
)

knowledge_base_chunks_per_document = Histogram(
    "knowledge_base_chunks_per_document",
    "Chunk count per ingested document",
    labelnames=("tenant_id",),
)

knowledge_base_stale_documents_ratio = Gauge(
    "knowledge_base_stale_documents_ratio",
    "Fraction of non-archived documents currently flagged stale",
    labelnames=("tenant_id",),
)

import pytest

from agentic_rag.core.domain import Provenance, RetrievalSource, RetrievedItem
from agentic_rag.core.fakes import FakeGraphDBClient, FakeKnowledgeBaseClient, FakeVectorDBClient
from agentic_rag.core.hybrid_retriever import HybridRetriever, reciprocal_rank_fusion


def _item(doc: str, content: str = "x") -> RetrievedItem:
    return RetrievedItem(content=content, source=RetrievalSource.VECTOR_DB, provenance=Provenance(source_document=doc))


def test_rrf_ranks_item_appearing_in_multiple_lists_higher():
    shared = _item("doc-shared")
    only_in_a = _item("doc-a-only")
    only_in_b = _item("doc-b-only")

    fused = reciprocal_rank_fusion([[shared, only_in_a], [shared, only_in_b]])

    assert fused[0].provenance.source_document == "doc-shared"


def test_rrf_deduplicates_by_source_document_and_location():
    same_doc_twice = _item("doc-1")
    fused = reciprocal_rank_fusion([[same_doc_twice], [same_doc_twice]])
    assert len(fused) == 1


def test_rrf_handles_empty_lists():
    fused = reciprocal_rank_fusion([[], [], []])
    assert fused == []


@pytest.mark.asyncio
async def test_hybrid_retriever_fans_out_to_all_three_backends():
    vector_db, graph_db, kb = FakeVectorDBClient(), FakeGraphDBClient(), FakeKnowledgeBaseClient()
    retriever = HybridRetriever(vector_db, graph_db, kb, hybrid_enabled=True)

    results = await retriever.retrieve("mortgage rate", scope=[], tenant_id="tenant-a")

    sources = {r.source for r in results}
    assert sources == {RetrievalSource.VECTOR_DB, RetrievalSource.GRAPH_DB, RetrievalSource.KNOWLEDGE_BASE}
    assert len(vector_db.calls) == 1


@pytest.mark.asyncio
async def test_hybrid_disabled_only_queries_vector_db():
    vector_db, graph_db, kb = FakeVectorDBClient(), FakeGraphDBClient(), FakeKnowledgeBaseClient()
    retriever = HybridRetriever(vector_db, graph_db, kb, hybrid_enabled=False)

    results = await retriever.retrieve("mortgage rate", scope=[], tenant_id="tenant-a")

    assert all(r.source == RetrievalSource.VECTOR_DB for r in results)

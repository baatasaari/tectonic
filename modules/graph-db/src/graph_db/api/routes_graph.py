"""`/v1/graph-db/*` routes (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from graph_db.api.deps import build_graph_engine, get_ctx, get_repository
from graph_db.app_context import AppContext
from graph_db.core.domain import EdgeRecord, InvalidEdgeKindError, MissingEdgeKindError, NodeRecord
from graph_db.core.ports import GraphRepository
from graph_db.schemas.graph import (
    CreateEdgeRequest,
    CreateNodeRequest,
    EdgeSchema,
    NodeSchema,
    QueryRequest,
    QueryResponse,
)

router = APIRouter(prefix="/v1/graph-db", tags=["graph-db"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _node_schema(n: NodeRecord) -> NodeSchema:
    return NodeSchema(id=n.id, entity_type=n.entity_type, name=n.name, attributes=n.attributes, created_at=n.created_at)


def _edge_schema(e: EdgeRecord) -> EdgeSchema:
    return EdgeSchema(
        id=e.id, from_node_id=e.from_node_id, to_node_id=e.to_node_id, relationship_type=e.relationship_type,
        edge_kind=e.edge_kind.value, valid_from=e.valid_from, valid_to=e.valid_to, confidence=e.confidence,
        source_ref=e.source_ref, created_at=e.created_at,
    )


@router.post("/nodes", response_model=NodeSchema, status_code=201)
async def create_node(
    body: CreateNodeRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: GraphRepository = Depends(get_repository),
) -> NodeSchema:
    engine = build_graph_engine(ctx, repository)
    node = await engine.write_node(
        tenant_id=_tenant_id(request, ctx), entity_type=body.entity_type, name=body.name, attributes=body.attributes,
    )
    return _node_schema(node)


@router.post("/edges", response_model=EdgeSchema, status_code=201)
async def create_edge(
    body: CreateEdgeRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: GraphRepository = Depends(get_repository),
) -> EdgeSchema:
    engine = build_graph_engine(ctx, repository)
    try:
        edge = await engine.write_edge(
            tenant_id=_tenant_id(request, ctx), from_node_id=body.from_node_id, to_node_id=body.to_node_id,
            relationship_type=body.relationship_type, edge_kind=body.edge_kind, valid_from=body.valid_from,
            valid_to=body.valid_to, confidence=body.confidence, source_ref=body.source_ref,
        )
    except (MissingEdgeKindError, InvalidEdgeKindError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _edge_schema(edge)


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: GraphRepository = Depends(get_repository),
) -> QueryResponse:
    engine = build_graph_engine(ctx, repository)
    tenant_id = _tenant_id(request, ctx)
    depth = body.depth if body.depth is not None else ctx.settings.query.default_max_traversal_depth

    if body.query_type == "neighbours":
        subgraph = await engine.neighbours(
            tenant_id, body.node_id, depth=depth, edge_kind_filter=body.edge_kind, as_of=body.as_of,
        )
    else:
        if not body.target_node_id:
            raise HTTPException(status_code=422, detail="target_node_id is required for query_type='path'")
        subgraph = await engine.path(
            tenant_id, body.node_id, body.target_node_id, depth=depth, edge_kind_filter=body.edge_kind,
            as_of=body.as_of,
        )

    return QueryResponse(
        nodes=[_node_schema(n) for n in subgraph.nodes], edges=[_edge_schema(e) for e in subgraph.edges],
        path=subgraph.node_path,
    )


@router.get("/nodes/{node_id}/neighbours", response_model=QueryResponse)
async def get_neighbours(
    node_id: str,
    request: Request,
    depth: int | None = Query(None),
    edge_kind: str | None = Query(None),
    as_of: datetime | None = Query(None),
    ctx: AppContext = Depends(get_ctx),
    repository: GraphRepository = Depends(get_repository),
) -> QueryResponse:
    _reject_null_byte_query(edge_kind=edge_kind)
    tenant_id = _tenant_id(request, ctx)
    existing = await repository.get_node(tenant_id, node_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="node not found")

    engine = build_graph_engine(ctx, repository)
    effective_depth = depth if depth is not None else ctx.settings.query.default_max_traversal_depth
    subgraph = await engine.neighbours(tenant_id, node_id, depth=effective_depth, edge_kind_filter=edge_kind, as_of=as_of)
    return QueryResponse(
        nodes=[_node_schema(n) for n in subgraph.nodes], edges=[_edge_schema(e) for e in subgraph.edges], path=None,
    )

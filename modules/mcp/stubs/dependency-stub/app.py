"""Dependency-stub service for MCP.

Stands in for a registered MCP server (internal or third-party) — this
module's own proxy path (RpcGateway forwarding through
MCPBackendHTTPClient) is exercised end-to-end against this stub without
needing a real third-party MCP server. Implements the minimal JSON-RPC
2.0 method set the LLD's "Deployability and testability contract" calls
for: `initialize`, `tools/list`, `tools/call`.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title="MCP dependency stub")

_TOOLS = [
    {
        "name": "search",
        "description": "Canned search tool exposed by this stub server.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
]


@app.post("/rpc")
async def rpc(body: dict[str, Any]) -> dict[str, Any]:
    method = body.get("method")
    request_id = body.get("id")

    if method == "initialize":
        result: Any = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "dependency-stub", "version": "0.1.0"}}
    elif method == "tools/list":
        result = {"tools": _TOOLS}
    elif method == "tools/call":
        # Canned success -- a real backend would dispatch on params["name"]; this stub
        # just proves the wiring, matching this platform's "stub returns canned data,
        # real behavior is exercised by the unit tier's fakes" convention.
        result = {"ok": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

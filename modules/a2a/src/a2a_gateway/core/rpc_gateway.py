"""A2A RPC Gateway (LLD §3 API surface, `/v1/a2a/rpc`): the actual A2A
wire surface external callers use — `message/send`, `tasks/get`,
`tasks/cancel` — shaping every outcome (success, access denial, unknown
skill, unknown task) into a JSON-RPC response the same way MCP's own
RpcGateway (Module 21) does for its wire surface.
"""
from __future__ import annotations

from typing import Any

from a2a_gateway.core.domain import (
    A2ATaskRecord,
    AccessDeniedError,
    JsonRpcResponse,
    TaskStatus,
    UnknownSkillError,
)
from a2a_gateway.core.inbound_gateway import InboundGateway
from a2a_gateway.core.ports import A2AGatewayRepository, WorkflowEngineClient

# JSON-RPC 2.0 reserves -32000 to -32099 for implementation-defined server errors.
_ACCESS_DENIED_CODE = -32001
_UNKNOWN_SKILL_CODE = -32002
_TASK_NOT_FOUND_CODE = -32003


def _task_to_result(task: A2ATaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.id, "status": task.status.value, "artifacts": task.output_artifacts, "error": task.error,
    }


class A2ARpcGateway:
    def __init__(
        self, repository: A2AGatewayRepository, workflow_client: WorkflowEngineClient,
        skill_definition_map: dict[str, str],
    ) -> None:
        self._repository = repository
        self._gateway = InboundGateway(repository, workflow_client, skill_definition_map)

    async def handle(
        self, *, method: str, params: dict[str, Any] | None, id: str | int | None, tenant_id: str,
        caller_agent_id: str, peer_agent_url: str,
    ) -> JsonRpcResponse:
        params = params or {}

        if method == "message/send":
            return await self._message_send(params, id, tenant_id, caller_agent_id, peer_agent_url)
        if method == "tasks/get":
            return await self._tasks_get(params, id)
        if method == "tasks/cancel":
            return await self._tasks_cancel(params, id)
        return JsonRpcResponse(jsonrpc="2.0", id=id, error={"code": -32601, "message": "Method not found"})

    async def _message_send(
        self, params: dict[str, Any], id: str | int | None, tenant_id: str, caller_agent_id: str, peer_agent_url: str,
    ) -> JsonRpcResponse:
        skill_id = params.get("skill_id", "")
        input_message = params.get("message", {})
        try:
            task = await self._gateway.accept(
                tenant_id=tenant_id, caller_agent_id=caller_agent_id, peer_agent_url=peer_agent_url,
                skill_id=skill_id, input_message=input_message,
            )
        except AccessDeniedError as exc:
            return JsonRpcResponse(jsonrpc="2.0", id=id, error={"code": _ACCESS_DENIED_CODE, "message": exc.reason})
        except UnknownSkillError as exc:
            return JsonRpcResponse(jsonrpc="2.0", id=id, error={"code": _UNKNOWN_SKILL_CODE, "message": str(exc)})
        return JsonRpcResponse(jsonrpc="2.0", id=id, result=_task_to_result(task))

    async def _tasks_get(self, params: dict[str, Any], id: str | int | None) -> JsonRpcResponse:
        task = await self._repository.get_task(params.get("task_id", ""))
        if task is None:
            return JsonRpcResponse(
                jsonrpc="2.0", id=id, error={"code": _TASK_NOT_FOUND_CODE, "message": "task not found"},
            )
        return JsonRpcResponse(jsonrpc="2.0", id=id, result=_task_to_result(task))

    async def _tasks_cancel(self, params: dict[str, Any], id: str | int | None) -> JsonRpcResponse:
        task_id = params.get("task_id", "")
        task = await self._repository.get_task(task_id)
        if task is None:
            return JsonRpcResponse(
                jsonrpc="2.0", id=id, error={"code": _TASK_NOT_FOUND_CODE, "message": "task not found"},
            )
        canceled = await self._repository.update_task_status(task_id, status=TaskStatus.CANCELED)
        return JsonRpcResponse(jsonrpc="2.0", id=id, result=_task_to_result(canceled))

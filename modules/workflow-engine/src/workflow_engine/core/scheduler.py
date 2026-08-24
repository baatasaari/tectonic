"""Execution Scheduler (LLD §2.2, §3.4, §3.5, §3.6): determines next runnable
step(s), manages parallel branches, confidence-gated escalation, retries,
compensation and replanning, and instance lifecycle transitions.

This is a self-contained graph runtime implementing the semantics the LLD
assigns to ADK 2.0's Workflow Runtime (fan-out/fan-in, retry, state
management, human-in-the-loop, dynamic nodes). It is deliberately kept behind
no ADK-specific API: swapping in the real ADK 2.0 Workflow Runtime means
implementing this same role against ADK's graph executor and Task API — see
NOTES.md — without changing the Definition Parser, the platform-level
schema, or any of the executors this scheduler drives. That boundary is what
lets the module ship and be fully tested today without a hard dependency on
an external agent runtime SDK.

Simplifying assumption for this first cut: at most one step per instance is
ever awaiting human approval at a time (the common case — a workflow branches
into an approval gate and everything else in that batch either completed
before it or waits behind it). Multi-concurrent-approval support is a
follow-up, not a change to the state model.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import replace

from workflow_engine.config import ExecutionConfig, ReplanningConfig
from workflow_engine.core import events
from workflow_engine.core.domain import (
    ExecutionMode,
    InstanceStatus,
    StepExecutionRecord,
    StepOutcome,
    StepStatus,
    WorkflowGraph,
    WorkflowInstanceRecord,
    WorkflowNode,
    new_id,
    now,
)
from workflow_engine.core.human import HumanApprovalHandler
from workflow_engine.core.neural import NeuralStepExecutor
from workflow_engine.core.ports import EventPublisher, WorkflowRepository
from workflow_engine.core.replanner import Replanner
from workflow_engine.core.router import resolve_execution_mode
from workflow_engine.core.symbolic import RuleEvaluationError, SymbolicRuleExecutor, safe_eval
from workflow_engine.telemetry.logging import get_logger
from workflow_engine.telemetry.metrics import (
    workflow_instances_active,
    workflow_orchestration_overhead_seconds,
    workflow_replan_total,
    workflow_step_duration_seconds,
    workflow_steps_total,
)

logger = get_logger(component="scheduler")


class WorkflowFailedError(Exception):
    """Raised internally to unwind the run loop on unrecoverable failure."""


class ExecutionScheduler:
    def __init__(
        self,
        repository: WorkflowRepository,
        event_publisher: EventPublisher,
        symbolic_executor: SymbolicRuleExecutor,
        neural_executor: NeuralStepExecutor,
        human_handler: HumanApprovalHandler,
        replanner: Replanner,
        execution_config: ExecutionConfig,
        replanning_config: ReplanningConfig,
        sleep_fn=asyncio.sleep,
        backoff_base_seconds: float = 0.05,
    ) -> None:
        self.repository = repository
        self.event_publisher = event_publisher
        self.symbolic_executor = symbolic_executor
        self.neural_executor = neural_executor
        self.human_handler = human_handler
        self._sleep = sleep_fn
        self._backoff_base_seconds = backoff_base_seconds
        self.replanner = replanner
        self.execution_config = execution_config
        self.replanning_config = replanning_config

    async def _publish(self, topic: str, event: dict) -> None:
        try:
            await self.event_publisher.publish(topic, event)
        except Exception:
            from workflow_engine.telemetry.metrics import workflow_event_publish_failures_total

            workflow_event_publish_failures_total.labels(
                tenant_id=event.get("tenant_id", "unknown"), destination=topic
            ).inc()
            logger.warning("event_publish_failed", topic=topic, event_type=event.get("event_type"))

    async def start(
        self, instance: WorkflowInstanceRecord, graph: WorkflowGraph
    ) -> WorkflowInstanceRecord:
        workflow_instances_active.labels(tenant_id=instance.tenant_id, status=instance.status.value).inc()
        await self._publish(
            events.TOPIC_WORKFLOW_INSTANCE,
            events.workflow_started(instance.tenant_id, instance.trace_id, instance.id, instance.definition_id),
        )
        instance = replace(instance, current_step_ids=[graph.entry_point])
        instance = await self.repository.update_instance(instance)
        return await self._run(instance, graph)

    async def resume_after_approval(
        self, instance: WorkflowInstanceRecord, graph: WorkflowGraph, approved: bool
    ) -> WorkflowInstanceRecord:
        pending_step_ids = instance.current_step_ids
        if not pending_step_ids:
            return instance

        step_id = pending_step_ids[0]
        # `list_step_executions` is now paginated (limit/offset) for the `GET
        # /instances/{id}/steps` API, but this scheduling logic needs the *complete* set of
        # step executions for the instance to find the one currently running — a truncated
        # page here could silently miss it on a long-running workflow. limit=10_000 is an
        # effectively-unbounded internal page size (one instance's step count is bounded by
        # its workflow graph, never a user-growable list).
        steps, _total = await self.repository.list_step_executions(instance.id, limit=10_000)
        step_exec = next((s for s in steps if s.step_id == step_id and s.status == StepStatus.RUNNING), None)
        if step_exec is None:
            step_exec = next((s for s in steps if s.step_id == step_id), None)

        workflow_instances_active.labels(tenant_id=instance.tenant_id, status="paused_for_approval").dec()
        workflow_instances_active.labels(tenant_id=instance.tenant_id, status="running").inc()
        instance = replace(instance, status=InstanceStatus.RUNNING)
        next_frontier: list[str] = list(pending_step_ids[1:])

        if approved:
            if step_exec is not None:
                step_exec = replace(step_exec, status=StepStatus.COMPLETED, completed_at=now())
                await self.repository.update_step_execution(step_exec)
                instance.context[step_id] = step_exec.output or {}
            next_frontier.extend(self._successors(graph, instance, step_id))
        else:
            if step_exec is not None:
                step_exec = replace(step_exec, status=StepStatus.FAILED, completed_at=now())
                await self.repository.update_step_execution(step_exec)
            # A rejected human step is a step failure: route through the same
            # compensation/replan path as any other exhausted-retry failure.
            fallback = await self._handle_step_failure(instance, graph, graph.node(step_id), "human_rejected")
            if fallback is not None:
                next_frontier.append(fallback)
            else:
                return await self._fail(instance, "human_rejected")

        instance = replace(instance, current_step_ids=next_frontier)
        instance = await self.repository.update_instance(instance)
        return await self._run(instance, graph)

    def _successors(self, graph: WorkflowGraph, instance: WorkflowInstanceRecord, step_id: str) -> list[str]:
        ready = []
        for edge in graph.outgoing(step_id):
            if edge.condition:
                try:
                    if not safe_eval(edge.condition, instance.context):
                        continue
                except RuleEvaluationError:
                    logger.warning("edge_condition_eval_failed", edge=f"{edge.from_}->{edge.to}")
                    continue
            ready.append(edge.to)
        return ready

    async def _run(self, instance: WorkflowInstanceRecord, graph: WorkflowGraph) -> WorkflowInstanceRecord:
        semaphore = asyncio.Semaphore(self.execution_config.max_parallel_steps_per_instance)

        while instance.current_step_ids and instance.status == InstanceStatus.RUNNING:
            frontier = list(dict.fromkeys(instance.current_step_ids))  # de-dup, preserve order

            # `instance` is bound as a default so each call captures this
            # iteration's value rather than whatever `instance` is rebound to
            # after the loop body finishes (ruff B023) — all of these run
            # concurrently and complete before that rebind happens, but the
            # explicit capture keeps the closure correct if that ever changes.
            async def run_one(step_id: str, instance: WorkflowInstanceRecord = instance) -> tuple[str, StepOutcome | None]:
                async with semaphore:
                    try:
                        return step_id, await self._execute_step(instance, graph, step_id)
                    except _AwaitingApproval:
                        return step_id, None

            try:
                results = await asyncio.gather(*(run_one(sid) for sid in frontier))
            except WorkflowFailedError as e:
                return await self._fail(instance, str(e))

            next_frontier: list[str] = []
            paused = False
            for step_id, outcome in results:
                if outcome is None:
                    # Awaiting approval: this step (and only this step, per the
                    # single-pending-approval simplification) carries over.
                    next_frontier.append(step_id)
                    paused = True
                    continue
                if outcome.status == StepStatus.COMPLETED:
                    instance.context[step_id] = outcome.output or {}
                    next_frontier.extend(self._successors(graph, instance, step_id))
                elif outcome.status == StepStatus.REPLAN_TRIGGERED:
                    next_frontier.append(outcome.output["reroute_to"])  # alternative step id

            if paused:
                instance = replace(instance, status=InstanceStatus.PAUSED_FOR_APPROVAL, current_step_ids=next_frontier)
                instance = await self.repository.update_instance(instance)
                await self._publish(
                    events.TOPIC_WORKFLOW_INSTANCE,
                    events.workflow_paused_for_approval(
                        instance.tenant_id, instance.trace_id, instance.id, next_frontier[0] if next_frontier else ""
                    ),
                )
                workflow_instances_active.labels(tenant_id=instance.tenant_id, status="running").dec()
                workflow_instances_active.labels(tenant_id=instance.tenant_id, status="paused_for_approval").inc()
                return instance

            instance = replace(instance, current_step_ids=next_frontier)
            instance = await self.repository.update_instance(instance)

        if instance.status == InstanceStatus.RUNNING:
            instance = replace(instance, status=InstanceStatus.COMPLETED, completed_at=now())
            instance = await self.repository.update_instance(instance)
            await self._publish(
                events.TOPIC_WORKFLOW_INSTANCE,
                events.workflow_completed(instance.tenant_id, instance.trace_id, instance.id),
            )
            workflow_instances_active.labels(tenant_id=instance.tenant_id, status="running").dec()
        return instance

    async def _fail(self, instance: WorkflowInstanceRecord, reason: str) -> WorkflowInstanceRecord:
        instance = replace(instance, status=InstanceStatus.FAILED, completed_at=now())
        instance = await self.repository.update_instance(instance)
        await self._publish(
            events.TOPIC_WORKFLOW_INSTANCE,
            events.workflow_failed(instance.tenant_id, instance.trace_id, instance.id, reason),
        )
        workflow_instances_active.labels(tenant_id=instance.tenant_id, status="running").dec()
        return instance

    async def _execute_step(
        self, instance: WorkflowInstanceRecord, graph: WorkflowGraph, step_id: str
    ) -> StepOutcome:
        node = graph.node(step_id)
        mode = resolve_execution_mode(node)

        overhead_start = time.perf_counter()
        step_exec = StepExecutionRecord(
            id=new_id(),
            instance_id=instance.id,
            step_id=step_id,
            execution_mode=mode,
            status=StepStatus.RUNNING,
            input_snapshot=dict(instance.context),
            started_at=now(),
        )
        step_exec = await self.repository.create_step_execution(step_exec)
        workflow_orchestration_overhead_seconds.labels(tenant_id=instance.tenant_id).observe(
            time.perf_counter() - overhead_start
        )

        await self._publish(
            events.TOPIC_WORKFLOW_STEP,
            events.step_started(instance.tenant_id, instance.trace_id, instance.id, step_id, mode.value),
        )

        duration_start = time.perf_counter()
        outcome, retry_count = await self._invoke_with_retry(node, mode, instance)
        workflow_step_duration_seconds.labels(tenant_id=instance.tenant_id, execution_mode=mode.value).observe(
            time.perf_counter() - duration_start
        )
        step_exec = replace(step_exec, retry_count=retry_count)

        needs_approval = outcome.status == StepStatus.COMPLETED and (
            mode == ExecutionMode.HUMAN
            or (
                mode == ExecutionMode.NEURAL
                and outcome.confidence_score is not None
                and outcome.confidence_score < node.confidence_threshold
            )
        )
        if needs_approval:
            approval = await self.human_handler.request_approval(
                step_execution_id=step_exec.id, context=instance.context, tenant_id=instance.tenant_id
            )
            step_exec = replace(step_exec, output=outcome.output, confidence_score=outcome.confidence_score)
            await self.repository.update_step_execution(step_exec)
            await self._publish(
                events.TOPIC_WORKFLOW_APPROVAL,
                events.approval_requested(
                    instance.tenant_id,
                    instance.trace_id,
                    instance.id,
                    step_id,
                    approval.id,
                    self.human_handler_timeout(node),
                ),
            )
            raise _AwaitingApproval()

        if outcome.status == StepStatus.FAILED:
            workflow_steps_total.labels(tenant_id=instance.tenant_id, execution_mode=mode.value, status="failed").inc()
            step_exec = replace(step_exec, status=StepStatus.FAILED, completed_at=now())
            await self.repository.update_step_execution(step_exec)
            await self._publish(
                events.TOPIC_WORKFLOW_STEP,
                events.step_failed(instance.tenant_id, instance.trace_id, instance.id, step_id, step_exec.retry_count, outcome.error or ""),
            )
            fallback = await self._handle_step_failure(instance, graph, node, outcome.error or "step_failed")
            if fallback is not None:
                return StepOutcome(status=StepStatus.REPLAN_TRIGGERED, output={"reroute_to": fallback})
            raise WorkflowFailedError(outcome.error or "step_failed")

        step_exec = replace(
            step_exec,
            status=StepStatus.COMPLETED,
            output=outcome.output,
            confidence_score=outcome.confidence_score,
            completed_at=now(),
        )
        await self.repository.update_step_execution(step_exec)
        workflow_steps_total.labels(tenant_id=instance.tenant_id, execution_mode=mode.value, status="completed").inc()
        await self._publish(
            events.TOPIC_WORKFLOW_STEP,
            events.step_completed(instance.tenant_id, instance.trace_id, instance.id, step_id, mode.value, outcome.confidence_score),
        )
        return outcome

    def human_handler_timeout(self, node: WorkflowNode) -> int:
        return node.config.get("approval_timeout_seconds", 86400)

    async def _invoke_with_retry(
        self, node: WorkflowNode, mode: ExecutionMode, instance: WorkflowInstanceRecord
    ) -> tuple[StepOutcome, int]:
        """Retries a failing step per its retry_policy before the caller
        falls through to compensation/replan. `human` steps are never
        retried here — a rejection is a decision, not a transient failure."""
        max_retries = node.retry_policy.max_retries if mode != ExecutionMode.HUMAN else 0
        attempt = 0
        outcome = await self._invoke_executor(node, mode, instance)
        while outcome.status == StepStatus.FAILED and attempt < max_retries:
            attempt += 1
            delay = self._backoff_delay(node.retry_policy.backoff_strategy, attempt)
            if delay:
                await self._sleep(delay)
            await self._publish(
                events.TOPIC_WORKFLOW_STEP,
                events.step_failed(instance.tenant_id, instance.trace_id, instance.id, node.id, attempt, outcome.error or ""),
            )
            outcome = await self._invoke_executor(node, mode, instance)
        return outcome, attempt

    def _backoff_delay(self, strategy: str, attempt: int) -> float:
        if strategy == "none":
            return 0.0
        if strategy == "fixed":
            return self._backoff_base_seconds
        return self._backoff_base_seconds * (2 ** (attempt - 1))  # exponential

    async def _invoke_executor(
        self, node: WorkflowNode, mode: ExecutionMode, instance: WorkflowInstanceRecord
    ) -> StepOutcome:
        if mode == ExecutionMode.SYMBOLIC:
            rule_ref = node.config.get("symbolic_rule_ref")
            try:
                output = self.symbolic_executor.evaluate(rule_ref, instance.context)
                return StepOutcome(status=StepStatus.COMPLETED, output=output)
            except RuleEvaluationError as e:
                return StepOutcome(status=StepStatus.FAILED, error=str(e))
        if mode == ExecutionMode.NEURAL:
            return await self.neural_executor.execute(node, instance.context, instance.tenant_id, instance.trace_id)
        if mode == ExecutionMode.HUMAN:
            # The actual approval request is raised uniformly in _execute_step
            # (shared with the neural confidence-gate path); this is just the
            # "step ran" placeholder that makes it eligible for that gate.
            return StepOutcome(status=StepStatus.COMPLETED, output={})
        return StepOutcome(status=StepStatus.FAILED, error=f"unknown execution_mode {mode}")

    async def _handle_step_failure(
        self, instance: WorkflowInstanceRecord, graph: WorkflowGraph, node: WorkflowNode, reason: str
    ) -> str | None:
        """Runs compensation (if configured) then attempts a replan.
        Returns the alternative step id to route to, or None if the caller
        should treat this as a terminal failure."""
        if node.retry_policy.compensation_step_id:
            try:
                comp_node = graph.node(node.retry_policy.compensation_step_id)
                await self._invoke_executor(comp_node, resolve_execution_mode(comp_node), instance)
            except KeyError:
                logger.warning("compensation_step_not_found", step_id=node.retry_policy.compensation_step_id)

        if not self.replanning_config.enabled:
            workflow_replan_total.labels(tenant_id=instance.tenant_id, trigger_reason=reason, outcome="disabled").inc()
            return None

        _record, alternative = await self.replanner.replan(
            instance_id=instance.id,
            graph=graph,
            failed_step_id=node.id,
            reason=reason,
            context=instance.context,
            tenant_id=instance.tenant_id,
            trace_id=instance.trace_id,
        )
        outcome = "rerouted" if alternative else "no_valid_replan"
        workflow_replan_total.labels(tenant_id=instance.tenant_id, trigger_reason=reason, outcome=outcome).inc()
        await self._publish(
            events.TOPIC_WORKFLOW_REPLAN,
            events.replan_triggered(instance.tenant_id, instance.trace_id, instance.id, node.id, reason, outcome),
        )
        return alternative.id if alternative else None


class _AwaitingApproval(Exception):
    """Internal control-flow signal: this step is now paused on a human
    approval request and should not be treated as failed or completed."""

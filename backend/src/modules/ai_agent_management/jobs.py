"""Idempotent async-job handlers for long-running module work."""

from __future__ import annotations

from src.core.async_jobs.models import AsyncJob

from .registries import runner_registry
from .services import (
    AgentServiceError,
    EvaluationService,
    ExecutionService,
    EXECUTION_MACHINE,
    _transition,
)


def execute_agent_job(job: AsyncJob) -> dict[str, object]:
    execution = ExecutionService.get_execution(job.tenant_id, job.payload["execution_id"])
    if execution.state in execution.terminal_states:
        return {"execution_id": str(execution.id), "state": execution.state, "idempotent": True}
    if execution.state == "queued":
        execution = _transition(EXECUTION_MACHINE, execution, "start", job.tenant_id, f"job:{job.id}:start")
    runner = runner_registry.get(execution.agent.runner_key)
    if runner is None:
        ExecutionService.fail(job.tenant_id, execution.id, "RUNNER_UNAVAILABLE", "The configured runner is unavailable.", f"job:{job.id}:unavailable")
        raise AgentServiceError("RUNNER_UNAVAILABLE", "The configured runner is unavailable.")
    try:
        result = runner(tenant_id=str(job.tenant_id), execution_id=str(execution.id), task=execution.task_definition)
    except Exception:
        ExecutionService.fail(job.tenant_id, execution.id, "RUNNER_FAILED", "The configured runner failed.", f"job:{job.id}:failed")
        raise AgentServiceError("RUNNER_FAILED", "The configured runner failed.")
    completed = ExecutionService.complete(job.tenant_id, execution.id, result, {"runner_key": execution.agent.runner_key}, f"job:{job.id}:complete")
    return {"execution_id": str(completed.id), "state": completed.state}


def evaluation_job(job: AsyncJob) -> dict[str, object]:
    result = EvaluationService.run_evaluation_job(job.tenant_id, job.id)
    return dict(result)


__all__ = ["evaluation_job", "execute_agent_job"]


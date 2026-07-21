"""Audited lifecycle state machines for durable process-mining work."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from django.db import models

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition, register

from .models import AnalysisStatus, BottleneckAnalysis, ConformanceCheck, EventExportJob, ExportStatus, ProcessDiscoveryJob

ModelT = TypeVar("ModelT", bound=models.Model)


class AuditedStateMachine(StateMachine[ModelT]):
    """Enforce the complete transition evidence contract."""

    def apply(self, *args: Any, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        audit = dict(metadata or {})
        missing = [key for key in ("actor_id", "reason", "correlation_id") if not audit.get(key)]
        if missing:
            raise StateMachineConfigurationError(f"Transition audit metadata is missing: {', '.join(missing)}")
        audit.update({key: str(audit[key]) for key in ("actor_id", "reason", "correlation_id")})
        return super().apply(*args, metadata=audit, **kwargs)


def _analysis_machine(name: str, model: type[ModelT]) -> AuditedStateMachine[ModelT]:
    return AuditedStateMachine(
        name=name,
        model=model,
        states=AnalysisStatus.values,
        terminal_states=[AnalysisStatus.COMPLETED, AnalysisStatus.CANCELLED],
        transitions=[
            Transition("start", AnalysisStatus.QUEUED, AnalysisStatus.RUNNING),
            Transition("cancel", AnalysisStatus.QUEUED, AnalysisStatus.CANCELLED),
            Transition("complete", AnalysisStatus.RUNNING, AnalysisStatus.COMPLETED),
            Transition("fail", AnalysisStatus.RUNNING, AnalysisStatus.FAILED),
            Transition("timeout", AnalysisStatus.RUNNING, AnalysisStatus.TIMED_OUT),
            Transition("cancel", AnalysisStatus.RUNNING, AnalysisStatus.CANCELLED),
            Transition("retry", AnalysisStatus.FAILED, AnalysisStatus.QUEUED),
            Transition("retry", AnalysisStatus.TIMED_OUT, AnalysisStatus.QUEUED),
        ],
    )


DISCOVERY_STATE_MACHINE = _analysis_machine("process_mining.discovery", ProcessDiscoveryJob)
CONFORMANCE_STATE_MACHINE = _analysis_machine("process_mining.conformance", ConformanceCheck)
BOTTLENECK_STATE_MACHINE = _analysis_machine("process_mining.bottleneck", BottleneckAnalysis)
EXPORT_STATE_MACHINE = AuditedStateMachine(
    name="process_mining.export",
    model=EventExportJob,
    states=ExportStatus.values,
    terminal_states=[ExportStatus.CANCELLED, ExportStatus.EXPIRED],
    transitions=[
        Transition("start", ExportStatus.QUEUED, ExportStatus.RUNNING),
        Transition("cancel", ExportStatus.QUEUED, ExportStatus.CANCELLED),
        Transition("complete", ExportStatus.RUNNING, ExportStatus.COMPLETED),
        Transition("fail", ExportStatus.RUNNING, ExportStatus.FAILED),
        Transition("timeout", ExportStatus.RUNNING, ExportStatus.TIMED_OUT),
        Transition("cancel", ExportStatus.RUNNING, ExportStatus.CANCELLED),
        Transition("retry", ExportStatus.FAILED, ExportStatus.QUEUED),
        Transition("retry", ExportStatus.TIMED_OUT, ExportStatus.QUEUED),
        Transition("expire", ExportStatus.COMPLETED, ExportStatus.EXPIRED),
    ],
)

for _machine in (DISCOVERY_STATE_MACHINE, CONFORMANCE_STATE_MACHINE, BOTTLENECK_STATE_MACHINE, EXPORT_STATE_MACHINE):
    register(_machine.name or "", _machine)


__all__ = [
    "AuditedStateMachine",
    "BOTTLENECK_STATE_MACHINE",
    "CONFORMANCE_STATE_MACHINE",
    "DISCOVERY_STATE_MACHINE",
    "EXPORT_STATE_MACHINE",
]

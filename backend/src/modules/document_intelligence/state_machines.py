"""Registered, tenant-locked lifecycle machines for document intelligence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, TypeVar

from django.db import models

from src.core.state_machine import StateMachine, StateMachineConfigurationError, Transition, register

from .models import (
    ClassificationStatus,
    ClassifierModelVersion,
    ClassifierTrainingJob,
    DocumentClassification,
    DocumentExtraction,
    ExtractionStatus,
    ExtractionTemplate,
    ModelVersionStatus,
    TemplateStatus,
    TrainingStatus,
)

ModelT = TypeVar("ModelT", bound=models.Model)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AuditedStateMachine(StateMachine[ModelT]):
    """Require the stable audit context mandated for every domain transition."""

    def apply(self, *args: Any, metadata: Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        audit = dict(metadata or {})
        missing = [key for key in ("actor_id", "reason", "correlation_id") if not audit.get(key)]
        if missing:
            raise StateMachineConfigurationError(f"Transition audit metadata is missing: {', '.join(missing)}")
        # JSONField uses the standard encoder in this project; normalize UUIDs
        # without weakening validation of the caller-provided identity.
        audit["actor_id"] = str(audit["actor_id"])
        audit["correlation_id"] = str(audit["correlation_id"])
        audit["reason"] = str(audit["reason"])
        aggregate = next((value for value in args if isinstance(value, models.Model)), kwargs.get("aggregate"))
        command = next((value for value in args if isinstance(value, str)), None)
        if aggregate is not None and command is not None and self.name:
            from .services import ConfigurationService

            workflow_name = self.name.rsplit(".", 1)[-1]
            configured = ConfigurationService().get_value(aggregate.tenant_id, f"workflows.{workflow_name}")
            current_state = str(getattr(aggregate, self.state_field))
            configured_edges = {(str(edge["command"]), str(edge["from"]), str(edge["to"])) for edge in configured}
            declared_edges = {
                (edge.command, edge.source, edge.target)
                for edge in self.transitions
                if edge.command == command and edge.source == current_state
            }
            if not declared_edges or declared_edges.isdisjoint(configured_edges):
                raise StateMachineConfigurationError(
                    f"Tenant workflow does not allow {command!r} from {current_state!r}."
                )
        return super().apply(*args, metadata=audit, **kwargs)


def _artifact_ready(model: ClassifierModelVersion, context: Mapping[str, Any]) -> bool:
    """Activation requires measured quality and a successful readiness probe."""

    from .services import ConfigurationService

    threshold = Decimal(
        str(ConfigurationService().get_value(model.tenant_id, "classifier.activation_accuracy_threshold"))
    )

    return (
        model.accuracy > threshold
        and _SHA256_RE.fullmatch(model.artifact_checksum) is not None
        and context.get("artifact_ready") is True
    )


extraction_state_machine = AuditedStateMachine(
    name="document_intelligence.extraction",
    model=DocumentExtraction,
    states=ExtractionStatus.values,
    terminal_states=[ExtractionStatus.COMPLETED, ExtractionStatus.NEEDS_REVIEW, ExtractionStatus.CANCELLED],
    transitions=[
        Transition("start", ExtractionStatus.QUEUED, ExtractionStatus.PROCESSING),
        Transition("cancel", ExtractionStatus.QUEUED, ExtractionStatus.CANCELLED),
        Transition("complete", ExtractionStatus.PROCESSING, ExtractionStatus.COMPLETED),
        Transition("require_review", ExtractionStatus.PROCESSING, ExtractionStatus.NEEDS_REVIEW),
        Transition("fail", ExtractionStatus.PROCESSING, ExtractionStatus.FAILED),
        Transition("time_out", ExtractionStatus.PROCESSING, ExtractionStatus.TIMED_OUT),
        Transition("cancel", ExtractionStatus.PROCESSING, ExtractionStatus.CANCELLED),
        Transition("retry", ExtractionStatus.FAILED, ExtractionStatus.QUEUED),
        Transition("retry", ExtractionStatus.TIMED_OUT, ExtractionStatus.QUEUED),
    ],
)

classification_state_machine = AuditedStateMachine(
    name="document_intelligence.classification",
    model=DocumentClassification,
    states=ClassificationStatus.values,
    terminal_states=[ClassificationStatus.COMPLETED, ClassificationStatus.CANCELLED],
    transitions=[
        Transition("start", ClassificationStatus.QUEUED, ClassificationStatus.PROCESSING),
        Transition("cancel", ClassificationStatus.QUEUED, ClassificationStatus.CANCELLED),
        Transition("complete", ClassificationStatus.PROCESSING, ClassificationStatus.COMPLETED),
        Transition("fail", ClassificationStatus.PROCESSING, ClassificationStatus.FAILED),
        Transition("time_out", ClassificationStatus.PROCESSING, ClassificationStatus.TIMED_OUT),
        Transition("cancel", ClassificationStatus.PROCESSING, ClassificationStatus.CANCELLED),
        Transition("retry", ClassificationStatus.FAILED, ClassificationStatus.QUEUED),
        Transition("retry", ClassificationStatus.TIMED_OUT, ClassificationStatus.QUEUED),
    ],
)

training_state_machine = AuditedStateMachine(
    name="document_intelligence.training",
    model=ClassifierTrainingJob,
    states=TrainingStatus.values,
    terminal_states=[TrainingStatus.COMPLETED, TrainingStatus.CANCELLED],
    transitions=[
        Transition("start", TrainingStatus.QUEUED, TrainingStatus.TRAINING),
        Transition("cancel", TrainingStatus.QUEUED, TrainingStatus.CANCELLED),
        Transition("complete", TrainingStatus.TRAINING, TrainingStatus.COMPLETED),
        Transition("fail", TrainingStatus.TRAINING, TrainingStatus.FAILED),
        Transition("time_out", TrainingStatus.TRAINING, TrainingStatus.TIMED_OUT),
        Transition("cancel", TrainingStatus.TRAINING, TrainingStatus.CANCELLED),
        Transition("retry", TrainingStatus.FAILED, TrainingStatus.QUEUED),
        Transition("retry", TrainingStatus.TIMED_OUT, TrainingStatus.QUEUED),
    ],
)

model_version_state_machine = AuditedStateMachine(
    name="document_intelligence.model_version",
    model=ClassifierModelVersion,
    states=ModelVersionStatus.values,
    terminal_states=[ModelVersionStatus.FAILED],
    transitions=[
        Transition("activate", ModelVersionStatus.CANDIDATE, ModelVersionStatus.ACTIVE, (_artifact_ready,)),
        Transition("fail", ModelVersionStatus.CANDIDATE, ModelVersionStatus.FAILED),
        Transition("retire", ModelVersionStatus.ACTIVE, ModelVersionStatus.RETIRED),
        Transition("rollback", ModelVersionStatus.RETIRED, ModelVersionStatus.ACTIVE, (_artifact_ready,)),
    ],
)

template_state_machine = AuditedStateMachine(
    name="document_intelligence.template",
    model=ExtractionTemplate,
    states=TemplateStatus.values,
    terminal_states=[TemplateStatus.RETIRED],
    transitions=[
        Transition("activate", TemplateStatus.DRAFT, TemplateStatus.ACTIVE),
        Transition("deactivate", TemplateStatus.ACTIVE, TemplateStatus.INACTIVE),
        Transition("retire", TemplateStatus.ACTIVE, TemplateStatus.RETIRED),
        Transition("activate", TemplateStatus.INACTIVE, TemplateStatus.ACTIVE),
        Transition("retire", TemplateStatus.INACTIVE, TemplateStatus.RETIRED),
        Transition("retire", TemplateStatus.DRAFT, TemplateStatus.RETIRED),
    ],
)

# Stable aliases keep service code terse without creating parallel machines.
EXTRACTION_STATE_MACHINE = extraction_state_machine
CLASSIFICATION_STATE_MACHINE = classification_state_machine
TRAINING_STATE_MACHINE = training_state_machine
MODEL_VERSION_STATE_MACHINE = model_version_state_machine
TEMPLATE_STATE_MACHINE = template_state_machine

for _machine in (
    extraction_state_machine,
    classification_state_machine,
    training_state_machine,
    model_version_state_machine,
    template_state_machine,
):
    register(_machine.name or "", _machine)


__all__ = [
    "AuditedStateMachine",
    "CLASSIFICATION_STATE_MACHINE",
    "EXTRACTION_STATE_MACHINE",
    "MODEL_VERSION_STATE_MACHINE",
    "TEMPLATE_STATE_MACHINE",
    "TRAINING_STATE_MACHINE",
    "classification_state_machine",
    "extraction_state_machine",
    "model_version_state_machine",
    "template_state_machine",
    "training_state_machine",
]

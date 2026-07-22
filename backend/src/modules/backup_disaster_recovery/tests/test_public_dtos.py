"""Black-box contracts for role-appropriate public response DTOs."""

from __future__ import annotations

import uuid

import pytest

from ..serializers import (
    DRExerciseDetailSerializer,
    DRRunbookDetailSerializer,
    DRStepExecutionDetailSerializer,
    RecoveryPointDetailSerializer,
    RestoreRunDetailSerializer,
    RunbookStepDetailSerializer,
)
from ..state_machines import RUNBOOK_MACHINE
from .factories import (
    exercise_factory,
    recovery_point_factory,
    restore_run_factory,
    runbook_factory,
    runbook_step_factory,
    step_execution_factory,
)


def _assert_absent(payload: dict[str, object], *fields: str) -> None:
    leaked = sorted(set(fields).intersection(payload))
    assert not leaked, f"Public response leaked internal fields: {leaked}"


@pytest.mark.django_db
def test_recovery_point_detail_normalizes_evidence_and_redacts_actor() -> None:
    point = recovery_point_factory()
    point.verification_evidence = {
        "valid": True,
        "checksum_matches": True,
        "artifact_available": True,
        "encryption_metadata_valid": True,
        "provider_acknowledged": True,
        "error_code": "",
        "provider_payload": {"location": "secret/provider/path"},
    }

    payload = dict(RecoveryPointDetailSerializer(point).data)

    _assert_absent(
        payload,
        "tenant_id",
        "created_by",
        "artifact_locator_ref",
        "encryption_key_ref",
        "transition_history",
    )
    assert set(payload["verification_evidence"]) == {
        "kind",
        "checksum_valid",
        "artifact_available",
        "encryption_metadata_valid",
        "provider_acknowledged",
        "checked_at",
    }
    assert payload["verification_evidence"]["kind"] == "artifact_validation"
    assert payload["verification_evidence"]["checksum_valid"] is True


@pytest.mark.django_db
def test_operational_detail_dtos_redact_internal_identifiers_and_raw_payloads() -> None:
    runbook = runbook_factory()
    step = runbook_step_factory(runbook)
    point = recovery_point_factory(tenant_id=runbook.tenant_id)
    restore = restore_run_factory(
        point,
        runbook=None,
        async_job_id=uuid.uuid4(),
        validation_evidence={"provider_payload": {"secret": True}},
        verification_evidence={"provider_payload": {"secret": True}},
        error_message="provider stack trace",
    )
    restore.transition_history = [
        {
            "transition_key": "internal-idempotency-key",
            "command": "begin_validation",
            "from_state": "queued",
            "to_state": "validating",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "metadata": {"provider_operation_id": "private-operation"},
        }
    ]
    RUNBOOK_MACHINE.apply(runbook, "publish", transition_key="publish-public-dto")
    exercise = exercise_factory(
        runbook,
        async_job_id=uuid.uuid4(),
        evidence_summary={"provider_payload": {"secret": True}},
    )
    execution = step_execution_factory(
        exercise,
        step,
        async_job_id=uuid.uuid4(),
        provider_operation_id="provider-operation-secret",
        evidence={"provider_payload": {"secret": True}},
        error_message="provider stack trace",
    )
    execution.transition_history = [
        {
            "transition_key": "private-step-key",
            "command": "start",
            "from_state": "pending",
            "to_state": "running",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "metadata": {},
        }
    ]

    runbook_payload = dict(DRRunbookDetailSerializer(runbook).data)
    _assert_absent(
        runbook_payload,
        "tenant_id",
        "adapter_key",
        "owner_id",
        "created_by",
        "updated_by",
        "transition_history",
    )
    step_payload = dict(RunbookStepDetailSerializer(step).data)
    _assert_absent(
        step_payload,
        "tenant_id",
        "created_by",
        "updated_by",
        "deleted_by",
    )
    restore_payload = dict(RestoreRunDetailSerializer(restore).data)
    _assert_absent(
        restore_payload,
        "tenant_id",
        "idempotency_key",
        "async_job_id",
        "requested_by",
        "approved_by",
        "validation_evidence",
        "verification_evidence",
        "error_message",
        "transition_history",
    )
    exercise_payload = dict(DRExerciseDetailSerializer(exercise).data)
    _assert_absent(
        exercise_payload,
        "tenant_id",
        "idempotency_key",
        "async_job_id",
        "initiated_by",
        "evidence_summary",
        "transition_history",
    )
    execution_payload = dict(DRStepExecutionDetailSerializer(execution).data)
    _assert_absent(
        execution_payload,
        "tenant_id",
        "provider_operation_id",
        "async_job_id",
        "evidence",
        "error_message",
        "transition_history",
    )

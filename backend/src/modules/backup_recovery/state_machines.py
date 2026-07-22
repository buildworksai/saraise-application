"""Canonical guarded state machines for backup and verification workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.state_machine import StateMachine, Transition

from .models import BackupJob, BackupJobStatus, BackupVerification, VerificationStatus


def _claimed_and_available(_job: BackupJob, context: Mapping[str, Any]) -> bool:
    return context.get("async_job_claimed") is True and context.get("adapter_available") is True


def _cancellation_safe(_job: BackupJob, context: Mapping[str, Any]) -> bool:
    return context.get("adapter_acknowledged") is True or context.get("before_commit") is True


def _has_durable_artifact(_job: BackupJob, context: Mapping[str, Any]) -> bool:
    return context.get("provider_receipt_valid") is True and context.get("artifact_persisted") is True


def _has_stable_error(_job: BackupJob, context: Mapping[str, Any]) -> bool:
    error_code = context.get("error_code")
    return isinstance(error_code, str) and bool(error_code.strip()) and len(error_code) <= 64


JOB_STATE_MACHINE = StateMachine(
    name="backup_recovery.job",
    model=BackupJob,
    states=tuple(BackupJobStatus.values),
    terminal_states=(BackupJobStatus.COMPLETED, BackupJobStatus.FAILED, BackupJobStatus.CANCELLED),
    transitions=(
        Transition("start", BackupJobStatus.PENDING, BackupJobStatus.RUNNING, (_claimed_and_available,)),
        Transition("cancel", BackupJobStatus.PENDING, BackupJobStatus.CANCELLED),
        Transition("cancel", BackupJobStatus.RUNNING, BackupJobStatus.CANCELLED, (_cancellation_safe,)),
        Transition("complete", BackupJobStatus.RUNNING, BackupJobStatus.COMPLETED, (_has_durable_artifact,)),
        Transition("fail", BackupJobStatus.RUNNING, BackupJobStatus.FAILED, (_has_stable_error,)),
    ),
)


VERIFICATION_STATE_MACHINE = StateMachine(
    name="backup_recovery.verification",
    model=BackupVerification,
    states=tuple(VerificationStatus.values),
    terminal_states=(VerificationStatus.PASSED, VerificationStatus.FAILED, VerificationStatus.CANCELLED),
    transitions=(
        Transition("start", VerificationStatus.PENDING, VerificationStatus.RUNNING),
        Transition("cancel", VerificationStatus.PENDING, VerificationStatus.CANCELLED),
        Transition("cancel", VerificationStatus.RUNNING, VerificationStatus.CANCELLED),
        Transition("pass", VerificationStatus.RUNNING, VerificationStatus.PASSED),
        Transition("fail", VerificationStatus.RUNNING, VerificationStatus.FAILED),
    ),
)


__all__ = ["JOB_STATE_MACHINE", "VERIFICATION_STATE_MACHINE"]

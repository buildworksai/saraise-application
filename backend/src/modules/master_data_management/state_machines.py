"""Registered command graphs for governed MDM lifecycle transitions."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, Generic, TypeVar

from django.db import transaction
from django.utils import timezone

from src.core.observability import get_correlation_id
from src.core.state_machine import (
    GuardFailedError,
    IllegalTransitionError,
    JSONFieldTransitionRecorder,
    StateMachine,
    TerminalStateError,
    Transition,
    UnknownCommandError,
)

from .models import (
    DataQualityIssue,
    EntityStatus,
    IssueStatus,
    MasterDataEntity,
    MatchCandidate,
    MatchStatus,
    MergeHistory,
    MergeReversal,
    MergeStatus,
)

AggregateT = TypeVar("AggregateT", MasterDataEntity, DataQualityIssue, MatchCandidate, MergeHistory)


class CompanionFieldRecorder(JSONFieldTransitionRecorder[AggregateT], Generic[AggregateT]):
    """Persist fields prepared by guards in the same transition statement."""

    def __init__(self, *companion_fields: str) -> None:
        super().__init__("transition_history")
        self.companion_fields = tuple(companion_fields)

    def aggregate_update_fields(self) -> Collection[str]:
        return (*super().aggregate_update_fields(), *self.companion_fields)


def _required(context: Mapping[str, Any], key: str) -> Any:
    value = context.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def _transition_time(context: Mapping[str, Any], key: str) -> datetime:
    value = context.get(key)
    return value if isinstance(value, datetime) else timezone.now()


def _prepare_archive(entity: MasterDataEntity, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    if actor_id is None:
        return False
    entity.is_deleted = True
    entity.deleted_at = _transition_time(context, "deleted_at")
    entity.updated_by = actor_id
    return True


def _prepare_restore(entity: MasterDataEntity, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    if actor_id is None:
        return False
    entity.is_deleted = False
    entity.deleted_at = None
    entity.updated_by = actor_id
    return True


def _prepare_entity_merge(entity: MasterDataEntity, context: Mapping[str, Any]) -> bool:
    golden_record_id = _required(context, "golden_record_id")
    actor_id = _required(context, "actor_id")
    if golden_record_id is None or actor_id is None or str(golden_record_id) == str(entity.pk):
        return False
    golden = (
        MasterDataEntity.objects.for_tenant(entity.tenant_id)
        .filter(
            pk=golden_record_id,
            entity_type_id=entity.entity_type_id,
            is_golden=True,
            is_deleted=False,
        )
        .first()
    )
    if golden is None:
        return False
    entity.golden_record = golden
    entity.updated_by = actor_id
    return True


def _prepare_reverse_entity_merge(entity: MasterDataEntity, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    if actor_id is None:
        return False
    entity.golden_record = None
    entity.updated_by = actor_id
    return True


def _prepare_actor_update(entity: MasterDataEntity, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    if actor_id is None:
        return False
    entity.updated_by = actor_id
    return True


def _prepare_assignment(issue: DataQualityIssue, context: Mapping[str, Any]) -> bool:
    assignee_id = _required(context, "assignee_id")
    actor_id = _required(context, "actor_id")
    if assignee_id is None or actor_id is None:
        return False
    issue.assigned_to = assignee_id
    issue.updated_by = actor_id
    return True


def _prepare_issue_resolution(issue: DataQualityIssue, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    resolution = _required(context, "resolution")
    if actor_id is None or resolution is None:
        return False
    issue.resolution = str(resolution).strip()
    issue.resolved_by = actor_id
    issue.resolved_at = _transition_time(context, "resolved_at")
    issue.updated_by = actor_id
    return True


def _prepare_match_review(candidate: MatchCandidate, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    if actor_id is None:
        return False
    candidate.reviewed_by = actor_id
    candidate.reviewed_at = _transition_time(context, "reviewed_at")
    candidate.review_note = str(context.get("note", "")).strip()
    candidate.updated_by = actor_id
    return True


def _prepare_candidate_merge(candidate: MatchCandidate, context: Mapping[str, Any]) -> bool:
    merge_history_id = _required(context, "merge_history_id")
    if merge_history_id is None or candidate.reviewed_by is None:
        return False
    merge = (
        MergeHistory.objects.for_tenant(candidate.tenant_id)
        .filter(pk=merge_history_id, status=MergeStatus.APPLIED, reversal__isnull=True)
        .first()
    )
    if merge is None:
        return False
    candidate.merge_history = merge
    actor_id = context.get("actor_id")
    if actor_id is not None:
        candidate.updated_by = actor_id
    return True


MASTER_ENTITY_STATE_MACHINE: StateMachine[MasterDataEntity] = StateMachine(
    name="master_data_management.entity",
    model=MasterDataEntity,
    states=EntityStatus.values,
    transitions=(
        Transition("request_review", EntityStatus.ACTIVE, EntityStatus.PENDING_REVIEW, (_prepare_actor_update,)),
        Transition("approve", EntityStatus.PENDING_REVIEW, EntityStatus.ACTIVE, (_prepare_actor_update,)),
        Transition("merge", EntityStatus.ACTIVE, EntityStatus.MERGED, (_prepare_entity_merge,)),
        Transition("merge", EntityStatus.PENDING_REVIEW, EntityStatus.MERGED, (_prepare_entity_merge,)),
        Transition("archive", EntityStatus.ACTIVE, EntityStatus.ARCHIVED, (_prepare_archive,)),
        Transition("archive", EntityStatus.PENDING_REVIEW, EntityStatus.ARCHIVED, (_prepare_archive,)),
        Transition("restore", EntityStatus.ARCHIVED, EntityStatus.ACTIVE, (_prepare_restore,)),
        Transition("reverse_merge", EntityStatus.MERGED, EntityStatus.ACTIVE, (_prepare_reverse_entity_merge,)),
    ),
    recorder=CompanionFieldRecorder("golden_record", "is_deleted", "deleted_at", "updated_by"),
)

QUALITY_ISSUE_STATE_MACHINE: StateMachine[DataQualityIssue] = StateMachine(
    name="master_data_management.quality_issue",
    model=DataQualityIssue,
    states=IssueStatus.values,
    terminal_states=(IssueStatus.RESOLVED, IssueStatus.WAIVED),
    transitions=(
        Transition("assign", IssueStatus.OPEN, IssueStatus.IN_REVIEW, (_prepare_assignment,)),
        Transition("resolve", IssueStatus.OPEN, IssueStatus.RESOLVED, (_prepare_issue_resolution,)),
        Transition("resolve", IssueStatus.IN_REVIEW, IssueStatus.RESOLVED, (_prepare_issue_resolution,)),
        Transition("waive", IssueStatus.OPEN, IssueStatus.WAIVED, (_prepare_issue_resolution,)),
        Transition("waive", IssueStatus.IN_REVIEW, IssueStatus.WAIVED, (_prepare_issue_resolution,)),
    ),
    recorder=CompanionFieldRecorder("assigned_to", "resolution", "resolved_by", "resolved_at", "updated_by"),
)

MATCH_CANDIDATE_STATE_MACHINE: StateMachine[MatchCandidate] = StateMachine(
    name="master_data_management.match_candidate",
    model=MatchCandidate,
    states=MatchStatus.values,
    terminal_states=(MatchStatus.REJECTED, MatchStatus.MERGED),
    transitions=(
        Transition("confirm", MatchStatus.PENDING, MatchStatus.CONFIRMED, (_prepare_match_review,)),
        Transition("reject", MatchStatus.PENDING, MatchStatus.REJECTED, (_prepare_match_review,)),
        Transition("merge", MatchStatus.CONFIRMED, MatchStatus.MERGED, (_prepare_candidate_merge,)),
    ),
    recorder=CompanionFieldRecorder("reviewed_by", "reviewed_at", "review_note", "merge_history", "updated_by"),
)


class ConfiguredStateMachine(Generic[AggregateT]):
    """Tenant policy gate around a stable transition execution engine."""

    def __init__(self, workflow_key: str, engine: StateMachine[AggregateT]) -> None:
        self.workflow_key = workflow_key
        self.engine = engine
        self.name = engine.name

    def __getattr__(self, name: str) -> Any:
        return getattr(self.engine, name)

    def apply(
        self,
        aggregate: AggregateT,
        command: str,
        *,
        tenant_id: Any | None = None,
        **kwargs: Any,
    ) -> AggregateT:
        from .services import ConfigurationService

        scoped_tenant = tenant_id or aggregate.tenant_id
        transition_key = kwargs.get("transition_key")
        history = getattr(aggregate, "transition_history", ())
        if (
            transition_key
            and isinstance(history, list)
            and any(isinstance(item, Mapping) and item.get("transition_key") == transition_key for item in history)
        ):
            # Idempotent replay is governed by the durable transition receipt,
            # not by whether the source edge remains legal after it succeeded.
            return self.engine.apply(
                aggregate,
                command,
                tenant_id=scoped_tenant,
                **kwargs,
            )
        workflows = ConfigurationService.get_effective(scoped_tenant).get("workflows")
        policy = workflows.get(self.workflow_key) if isinstance(workflows, Mapping) else None
        if not isinstance(policy, Mapping):
            raise GuardFailedError(f"Workflow policy {self.workflow_key!r} is unavailable.")
        states = policy.get("states")
        transitions = policy.get("transitions")
        terminal_states = policy.get("terminal_states", [])
        if not isinstance(states, list) or not isinstance(transitions, list) or not isinstance(terminal_states, list):
            raise GuardFailedError(f"Workflow policy {self.workflow_key!r} is invalid.")
        current_state = str(getattr(aggregate, "status", ""))
        if current_state not in states:
            raise GuardFailedError(f"State {current_state!r} is disabled by tenant workflow policy.")
        if current_state in terminal_states:
            raise TerminalStateError(f"State {current_state!r} is terminal by tenant workflow policy.")
        permitted = any(
            isinstance(item, Mapping)
            and item.get("from") == current_state
            and item.get("command") == command
            and item.get("to") in states
            for item in transitions
        )
        if not permitted:
            known_command = any(isinstance(item, Mapping) and item.get("command") == command for item in transitions)
            if known_command:
                raise IllegalTransitionError(
                    f"Command {command!r} cannot transition tenant workflow "
                    f"{self.workflow_key!r} from {current_state!r}."
                )
            raise UnknownCommandError(
                f"Command {command!r} is disabled by tenant workflow policy from {current_state!r}."
            )
        return self.engine.apply(
            aggregate,
            command,
            tenant_id=scoped_tenant,
            **kwargs,
        )


MASTER_ENTITY_STATE_MACHINE = ConfiguredStateMachine(
    "entity",
    MASTER_ENTITY_STATE_MACHINE,
)
QUALITY_ISSUE_STATE_MACHINE = ConfiguredStateMachine(
    "quality_issue",
    QUALITY_ISSUE_STATE_MACHINE,
)
MATCH_CANDIDATE_STATE_MACHINE = ConfiguredStateMachine(
    "match_candidate",
    MATCH_CANDIDATE_STATE_MACHINE,
)


class MergeReversalMachine:
    """Compatibility command facade that writes separate immutable evidence."""

    name = "master_data_management.merge_history"

    @staticmethod
    def _compatibility_view(merge: MergeHistory, reversal: MergeReversal) -> MergeHistory:
        # These attributes are intentionally in-memory only. The persisted merge
        # evidence remains byte-for-byte unchanged.
        merge.status = MergeStatus.REVERSED
        merge.reversed_by = reversal.reversed_by
        merge.reversed_at = reversal.created_at
        merge.reversal_reason = reversal.reason
        return merge

    def apply(
        self,
        aggregate: MergeHistory,
        command: str,
        *,
        transition_key: str,
        context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        tenant_id: Any | None = None,
        **kwargs: Any,
    ) -> MergeHistory:
        del kwargs
        if command != "reverse":
            raise UnknownCommandError(f"Machine {self.name!r} has no command {command!r}")
        from .services import ConfigurationService

        scoped_tenant = tenant_id or aggregate.tenant_id
        workflows = ConfigurationService.get_effective(scoped_tenant).get("workflows")
        policy = workflows.get("merge") if isinstance(workflows, Mapping) else None
        transitions = policy.get("transitions") if isinstance(policy, Mapping) else None
        if not isinstance(transitions, list) or not any(
            isinstance(item, Mapping)
            and item.get("from") == MergeStatus.APPLIED
            and item.get("to") == MergeStatus.REVERSED
            and item.get("command") == command
            for item in transitions
        ):
            raise GuardFailedError("Merge reversal is disabled by tenant workflow policy.")
        values = dict(context or {})
        actor_id = _required(values, "actor_id")
        reason = _required(values, "reason")
        if actor_id is None or reason is None:
            raise GuardFailedError("Merge reversal requires actor_id and reason.")
        with transaction.atomic():
            locked = MergeHistory.objects.select_for_update().get(
                pk=aggregate.pk,
                tenant_id=scoped_tenant,
            )
            existing = (
                MergeReversal.objects.for_tenant(scoped_tenant)
                .filter(
                    merge_history=locked,
                )
                .first()
            )
            if existing is not None:
                if existing.transition_key == transition_key:
                    return self._compatibility_view(aggregate, existing)
                raise TerminalStateError(
                    f"{MergeHistory._meta.label} {locked.pk} already has immutable reversal evidence"
                )
            reversal = MergeReversal.objects.create(
                tenant_id=scoped_tenant,
                merge_history=locked,
                reversed_by=actor_id,
                reason=str(reason).strip(),
                correlation_id=str((metadata or {}).get("correlation_id") or get_correlation_id() or uuid.uuid4()),
                transition_key=transition_key,
                participant_versions={},
            )
        return self._compatibility_view(aggregate, reversal)


MERGE_HISTORY_STATE_MACHINE = MergeReversalMachine()

# Concise aliases keep service call sites readable while retaining descriptive
# public names for extensions and tests.
ENTITY_MACHINE = MASTER_ENTITY_STATE_MACHINE
ISSUE_MACHINE = QUALITY_ISSUE_STATE_MACHINE
CANDIDATE_MACHINE = MATCH_CANDIDATE_STATE_MACHINE
MATCH_MACHINE = MATCH_CANDIDATE_STATE_MACHINE
MERGE_MACHINE = MERGE_HISTORY_STATE_MACHINE


__all__ = [
    "CANDIDATE_MACHINE",
    "ENTITY_MACHINE",
    "ISSUE_MACHINE",
    "MASTER_ENTITY_STATE_MACHINE",
    "MATCH_CANDIDATE_STATE_MACHINE",
    "MATCH_MACHINE",
    "MERGE_HISTORY_STATE_MACHINE",
    "MERGE_MACHINE",
    "QUALITY_ISSUE_STATE_MACHINE",
]

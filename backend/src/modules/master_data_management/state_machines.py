"""Registered command graphs for governed MDM lifecycle transitions."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, Generic, TypeVar

from django.utils import timezone

from src.core.state_machine import JSONFieldTransitionRecorder, StateMachine, Transition

from .models import (
    DataQualityIssue,
    EntityStatus,
    IssueStatus,
    MasterDataEntity,
    MatchCandidate,
    MatchStatus,
    MergeHistory,
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
    golden = MasterDataEntity.objects.for_tenant(entity.tenant_id).filter(
        pk=golden_record_id,
        entity_type_id=entity.entity_type_id,
        is_golden=True,
        is_deleted=False,
    ).first()
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
        .filter(pk=merge_history_id, status=MergeStatus.APPLIED)
        .first()
    )
    if merge is None:
        return False
    candidate.merge_history = merge
    actor_id = context.get("actor_id")
    if actor_id is not None:
        candidate.updated_by = actor_id
    return True


def _prepare_merge_reversal(merge: MergeHistory, context: Mapping[str, Any]) -> bool:
    actor_id = _required(context, "actor_id")
    reason = _required(context, "reason")
    if actor_id is None or reason is None:
        return False
    merge.reversed_by = actor_id
    merge.reversed_at = _transition_time(context, "reversed_at")
    merge.reversal_reason = str(reason).strip()
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
    recorder=CompanionFieldRecorder(
        "assigned_to", "resolution", "resolved_by", "resolved_at", "updated_by"
    ),
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
    recorder=CompanionFieldRecorder(
        "reviewed_by", "reviewed_at", "review_note", "merge_history", "updated_by"
    ),
)

MERGE_HISTORY_STATE_MACHINE: StateMachine[MergeHistory] = StateMachine(
    name="master_data_management.merge_history",
    model=MergeHistory,
    states=MergeStatus.values,
    terminal_states=(MergeStatus.REVERSED,),
    transitions=(
        Transition("reverse", MergeStatus.APPLIED, MergeStatus.REVERSED, (_prepare_merge_reversal,)),
    ),
    recorder=CompanionFieldRecorder("reversed_by", "reversed_at", "reversal_reason"),
)

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

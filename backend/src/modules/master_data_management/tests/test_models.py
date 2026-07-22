"""Persistence invariants, ownership guards, and immutable-audit tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.state_machine import (
    GuardFailedError,
    IdempotencyConflictError,
    IllegalTransitionError,
    TerminalStateError,
    UnknownCommandError,
)
from src.modules.master_data_management.models import (
    DataQualityIssue,
    DataQualityRule,
    EntityStatus,
    IssueStatus,
    MasterDataEntity,
    MasterDataVersion,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MergeHistory,
    MergeParticipant,
)
from src.modules.master_data_management.state_machines import (
    CANDIDATE_MACHINE,
    ENTITY_MACHINE,
    ISSUE_MACHINE,
    MERGE_MACHINE,
)

from .factories import (
    actor_id,
    make_candidate,
    make_entity,
    make_entity_type,
    make_issue,
    make_matching_rule,
    make_merge,
    make_participant,
    make_quality_rule,
    make_version,
)

pytestmark = pytest.mark.django_db

MUTABLE_MODELS = (
    MasterEntityType,
    MasterDataEntity,
    DataQualityRule,
    DataQualityIssue,
    MatchingRule,
    MatchCandidate,
)
TENANT_MODELS = MUTABLE_MODELS + (MasterDataVersion, MergeHistory, MergeParticipant)


def test_all_domain_models_use_canonical_indexed_uuid_tenancy() -> None:
    for model in TENANT_MODELS:
        assert issubclass(model, TenantScopedModel), model.__name__
        tenant = model._meta.get_field("tenant_id")
        assert isinstance(tenant, models.UUIDField), model.__name__
        assert tenant.null is False
        assert tenant.db_index is True
        assert hasattr(model.objects, "for_tenant")


def test_mutable_models_have_uuid_identity_timestamps_and_actor_audit() -> None:
    for model in MUTABLE_MODELS:
        assert issubclass(model, TimestampedModel), model.__name__
        identity = model._meta.get_field("id")
        assert isinstance(identity, models.UUIDField)
        assert identity.primary_key is True
        assert identity.editable is False
        assert model._meta.get_field("created_by").null is False
        assert model._meta.get_field("created_by").editable is False
        assert model._meta.get_field("updated_by").null is True
        assert model._meta.get_field("updated_by").editable is False


def test_entity_type_defaults_and_field_path_validation() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant, key="customer")
    assert entity_type.schema_version == 1
    assert entity_type.owner_module == "master_data_management"
    assert entity_type.is_active is True
    assert entity_type.is_system is False
    assert entity_type.is_deleted is False

    with pytest.raises(ValidationError):
        make_entity_type(tenant, key="Vendor")
    with pytest.raises(ValidationError, match="Field paths must be unique"):
        make_entity_type(tenant, key="duplicate_paths", required_fields=["email", "email"])
    with pytest.raises(ValidationError, match="dotted field paths"):
        make_entity_type(tenant, key="invalid_paths", sensitive_fields=["bank..account"])
    with pytest.raises(ValidationError, match="JSON object"):
        make_entity_type(tenant, key="invalid_schema", json_schema=[])


def test_entity_type_key_is_unique_per_tenant_but_not_globally() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    make_entity_type(tenant_a, key="customer")
    make_entity_type(tenant_b, key="customer")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_entity_type(tenant_a, key="customer")


def test_system_type_and_soft_delete_lifecycle_is_guarded() -> None:
    tenant = uuid.uuid4()
    system_type = make_entity_type(tenant, key="customer", is_system=True, is_active=False)
    assert system_type.is_active is False
    with pytest.raises((ValidationError, IntegrityError), match="System entity types|mdm_type_system_not_deleted_ck"):
        make_entity_type(
            tenant,
            key="system_deleted",
            is_system=True,
            is_deleted=True,
            deleted_at=timezone.now(),
        )
    with pytest.raises(ValidationError, match="set or cleared together"):
        make_entity_type(tenant, key="supplier", is_deleted=True)

    entity_type = make_entity_type(tenant, key="material")
    with pytest.raises(ValidationError, match="Physical deletion is forbidden"):
        entity_type.delete()


def test_entity_defaults_business_key_scope_and_string_representation() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    customer_a = make_entity_type(tenant_a, key="customer")
    supplier_a = make_entity_type(tenant_a, key="supplier")
    customer_b = make_entity_type(tenant_b, key="customer")
    own = make_entity(tenant_a, entity_type=customer_a, entity_code="PARTY-001")
    make_entity(tenant_a, entity_type=supplier_a, entity_code="PARTY-001")
    make_entity(tenant_b, entity_type=customer_b, entity_code="PARTY-001")

    assert own.status == EntityStatus.ACTIVE
    assert own.source_system == "manual"
    assert own.quality_score == Decimal("0.00")
    assert own.version == 1
    assert own.golden_record_id is None
    assert own.transition_history == []
    assert str(own) == "customer - PARTY-001"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_entity(tenant_a, entity_type=customer_a, entity_code="PARTY-001")


def test_soft_deleted_entity_releases_business_key_and_cannot_be_hard_deleted() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant, key="customer")
    entity = make_entity(tenant, entity_type=entity_type, entity_code="REUSABLE")
    MasterDataEntity.objects.filter(pk=entity.pk).update(is_deleted=True, deleted_at=timezone.now())
    replacement = make_entity(tenant, entity_type=entity_type, entity_code="REUSABLE")
    assert replacement.pk != entity.pk
    with pytest.raises(ValidationError, match="Physical deletion is forbidden"):
        replacement.delete()


def test_entity_relations_must_share_tenant_and_type() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    customer_a = make_entity_type(tenant_a, key="customer")
    customer_b = make_entity_type(tenant_b, key="customer")
    foreign_type = make_entity_type(tenant_b, key="supplier")
    golden = make_entity(tenant_a, entity_type=customer_a, is_golden=True)

    with pytest.raises(ValidationError, match="same tenant"):
        make_entity(tenant_a, entity_type=customer_b)
    with pytest.raises(ValidationError, match="same tenant"):
        make_entity(
            tenant_b,
            entity_type=foreign_type,
            status=EntityStatus.MERGED,
            golden_record=golden,
        )


def test_direct_status_assignment_and_invalid_golden_states_are_rejected() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant, key="customer")
    entity = make_entity(tenant, entity_type=entity_type)
    entity.status = EntityStatus.ARCHIVED
    with pytest.raises(ValidationError, match="registered state machine"):
        entity.save()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_entity(tenant, entity_type=entity_type, status=EntityStatus.MERGED)


def test_versions_are_tenant_consistent_unique_and_strictly_append_only() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    entity = make_entity(tenant_a)
    version = make_version(tenant_a, entity=entity)
    assert version.version_number == 1

    version.change_reason = "Tampered"
    with pytest.raises(ValidationError, match="Append-only"):
        version.save()
    with pytest.raises(ValidationError, match="Append-only"):
        version.delete()
    with pytest.raises(ValidationError, match="Append-only"):
        MasterDataVersion.objects.filter(pk=version.pk).update(change_reason="Tampered")
    with pytest.raises(ValidationError, match="same tenant"):
        make_version(tenant_b, entity=entity)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_version(tenant_a, entity=entity)


def test_quality_rule_configuration_weight_uniqueness_and_type_scope() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    rule = make_quality_rule(tenant, entity_type=entity_type, name="Required email")
    assert rule.weight == Decimal("1.0000")
    with pytest.raises(ValidationError, match="JSON object"):
        make_quality_rule(tenant, entity_type=entity_type, configuration=[])
    with pytest.raises(ValidationError, match="dotted field path"):
        make_quality_rule(tenant, entity_type=entity_type, field_path="address..city")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_quality_rule(tenant, entity_type=entity_type, name="Required email")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_quality_rule(tenant, entity_type=entity_type, weight=Decimal("0"))


def test_quality_issue_same_tenant_type_resolution_and_open_uniqueness() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    entity = make_entity(tenant, entity_type=entity_type)
    rule = make_quality_rule(tenant, entity_type=entity_type)
    issue = make_issue(tenant, entity=entity, rule=rule)
    assert issue.status == IssueStatus.OPEN
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_issue(tenant, entity=entity, rule=rule)

    other_type = make_entity_type(tenant, key="supplier")
    other_rule = make_quality_rule(tenant, entity_type=other_type)
    with pytest.raises(ValidationError, match="same entity type"):
        make_issue(tenant, entity=entity, rule=other_rule)


@pytest.mark.parametrize(
    "overrides",
    [
        {"field_weights": {}},
        {"field_weights": {"email": "0.8"}},
        {"field_weights": {"email": "-1.0", "entity_name": "2.0"}},
        {"blocking_fields": ["bad..path"]},
        {"field_weights": {"bad..path": "1.0"}},
    ],
)
def test_matching_rule_rejects_non_deterministic_or_invalid_weight_config(
    overrides: dict[str, object],
) -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    with pytest.raises(ValidationError):
        make_matching_rule(tenant, entity_type=entity_type, **overrides)


def test_matching_thresholds_are_bounded_ordered_and_rules_are_unique() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    make_matching_rule(tenant, entity_type=entity_type, name="Identity")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_matching_rule(tenant, entity_type=entity_type, name="Identity")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_matching_rule(
                tenant,
                entity_type=entity_type,
                review_threshold=Decimal("0.9000"),
                auto_confirm_threshold=Decimal("0.8000"),
            )


def test_candidate_pair_is_canonical_unique_same_type_and_tenant() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    left = make_entity(tenant, entity_type=entity_type)
    right = make_entity(tenant, entity_type=entity_type)
    rule = make_matching_rule(tenant, entity_type=entity_type)
    candidate = make_candidate(tenant, matching_rule=rule, first=right, second=left)
    assert candidate.left_entity_id < candidate.right_entity_id
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_candidate(tenant, matching_rule=rule, first=left, second=right)

    other_type = make_entity_type(tenant, key="supplier")
    supplier = make_entity(tenant, entity_type=other_type)
    with pytest.raises(ValidationError, match="same entity type"):
        make_candidate(tenant, matching_rule=rule, first=left, second=supplier)


def test_merge_and_participant_evidence_is_immutable_unique_and_tenant_safe() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    survivor = make_entity(tenant, entity_type=entity_type, is_golden=True)
    source = make_entity(tenant, entity_type=entity_type)
    merge = make_merge(tenant, golden_record=survivor)
    survivor_participant = make_participant(
        tenant,
        merge_history=merge,
        source_entity=survivor,
        role="survivor",
    )
    source_participant = make_participant(tenant, merge_history=merge, source_entity=source)
    assert survivor_participant.role == "survivor"
    assert source_participant.role == "merged_source"

    merge.reason = "Tampered"
    with pytest.raises(ValidationError, match="append-only"):
        merge.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        merge.delete()
    with pytest.raises(ValidationError, match="Append-only"):
        source_participant.delete()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_participant(tenant, merge_history=merge, source_entity=source)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_participant(
                tenant,
                merge_history=merge,
                source_entity=make_entity(tenant, entity_type=entity_type),
                role="survivor",
            )


def test_database_table_and_required_index_contracts() -> None:
    assert {model._meta.db_table for model in TENANT_MODELS} == {
        "mdm_entity_types",
        "mdm_entities",
        "mdm_entity_versions",
        "mdm_quality_rules",
        "mdm_quality_issues",
        "mdm_matching_rules",
        "mdm_match_candidates",
        "mdm_merge_history",
        "mdm_merge_participants",
    }
    index_names = {
        index.name
        for model in TENANT_MODELS
        for index in model._meta.indexes
    }
    assert {
        "mdm_type_active_key_idx",
        "mdm_entity_type_stat_code_idx",
        "mdm_version_entity_desc_idx",
        "mdm_issue_status_severity_idx",
        "mdm_candidate_status_score_idx",
        "mdm_merge_status_created_idx",
        "mdm_participant_source_idx",
    } <= index_names


def test_created_and_updated_actor_fields_are_real_uuid_audit_references() -> None:
    tenant = uuid.uuid4()
    created_by = actor_id("creator")
    updated_by = actor_id("updater")
    entity_type = make_entity_type(tenant, created_by=created_by, updated_by=updated_by)
    assert entity_type.created_by == created_by
    assert entity_type.updated_by == updated_by


def test_entity_state_machine_covers_review_archive_restore_merge_and_reverse() -> None:
    tenant = uuid.uuid4()
    steward = actor_id("lifecycle")
    entity_type = make_entity_type(tenant)
    source = make_entity(tenant, entity_type=entity_type)
    golden = make_entity(tenant, entity_type=entity_type, is_golden=True)

    source = ENTITY_MACHINE.apply(
        source,
        "request_review",
        transition_key="review-1",
        context={"actor_id": steward},
        metadata={"reason_code": "steward_review"},
    )
    assert source.status == EntityStatus.PENDING_REVIEW
    source = ENTITY_MACHINE.apply(
        source,
        "approve",
        transition_key="approve-1",
        context={"actor_id": steward},
    )
    assert source.status == EntityStatus.ACTIVE
    source = ENTITY_MACHINE.apply(
        source,
        "archive",
        transition_key="archive-1",
        context={"actor_id": steward},
    )
    assert source.status == EntityStatus.ARCHIVED
    assert source.is_deleted is True and source.deleted_at is not None
    source = ENTITY_MACHINE.apply(
        source,
        "restore",
        transition_key="restore-1",
        context={"actor_id": steward},
    )
    assert source.status == EntityStatus.ACTIVE
    assert source.is_deleted is False and source.deleted_at is None
    source = ENTITY_MACHINE.apply(
        source,
        "merge",
        transition_key="merge-1",
        context={"actor_id": steward, "golden_record_id": golden.id},
    )
    assert source.status == EntityStatus.MERGED
    assert source.golden_record_id == golden.id
    source = ENTITY_MACHINE.apply(
        source,
        "reverse_merge",
        transition_key="reverse-1",
        context={"actor_id": steward},
    )
    assert source.status == EntityStatus.ACTIVE
    assert source.golden_record_id is None
    assert [item["command"] for item in source.transition_history] == [
        "request_review",
        "approve",
        "archive",
        "restore",
        "merge",
        "reverse_merge",
    ]


def test_entity_transition_guards_unknown_commands_and_idempotency_conflict() -> None:
    tenant = uuid.uuid4()
    entity = make_entity(tenant)
    with pytest.raises(GuardFailedError):
        ENTITY_MACHINE.apply(entity, "archive", transition_key="missing-actor", context={})
    with pytest.raises(UnknownCommandError):
        ENTITY_MACHINE.apply(
            entity,
            "hard_delete",
            transition_key="forbidden-command",
            context={"actor_id": actor_id()},
        )

    archived = ENTITY_MACHINE.apply(
        entity,
        "archive",
        transition_key="archive-idempotent",
        context={"actor_id": actor_id()},
    )
    replayed = ENTITY_MACHINE.apply(
        archived,
        "archive",
        transition_key="archive-idempotent",
        context={"actor_id": actor_id("other")},
    )
    assert replayed.status == EntityStatus.ARCHIVED
    assert len(replayed.transition_history) == 1
    with pytest.raises(IdempotencyConflictError):
        ENTITY_MACHINE.apply(
            replayed,
            "restore",
            transition_key="archive-idempotent",
            context={"actor_id": actor_id()},
        )
    with pytest.raises(IllegalTransitionError):
        ENTITY_MACHINE.apply(
            replayed,
            "approve",
            transition_key="illegal-approve",
            context={"actor_id": actor_id()},
        )


def test_quality_issue_state_machine_guards_terminal_states_and_records_resolution() -> None:
    tenant = uuid.uuid4()
    entity = make_entity(tenant)
    rule = make_quality_rule(tenant, entity_type=entity.entity_type)
    issue = make_issue(tenant, entity=entity, rule=rule)
    assignee = actor_id("assignee")
    reviewer = actor_id("reviewer")
    with pytest.raises(GuardFailedError):
        ISSUE_MACHINE.apply(
            issue,
            "assign",
            transition_key="assign-missing",
            context={"actor_id": reviewer},
        )
    issue = ISSUE_MACHINE.apply(
        issue,
        "assign",
        transition_key="assign-1",
        context={"actor_id": reviewer, "assignee_id": assignee},
    )
    assert issue.status == IssueStatus.IN_REVIEW
    assert issue.assigned_to == assignee
    with pytest.raises(GuardFailedError):
        ISSUE_MACHINE.apply(
            issue,
            "resolve",
            transition_key="resolve-missing",
            context={"actor_id": reviewer, "resolution": "  "},
        )
    issue = ISSUE_MACHINE.apply(
        issue,
        "resolve",
        transition_key="resolve-1",
        context={"actor_id": reviewer, "resolution": "Verified at source"},
    )
    assert issue.status == IssueStatus.RESOLVED
    assert issue.resolution == "Verified at source"
    assert issue.resolved_by == reviewer and issue.resolved_at is not None
    with pytest.raises(TerminalStateError):
        ISSUE_MACHINE.apply(
            issue,
            "waive",
            transition_key="terminal-waive",
            context={"actor_id": reviewer, "resolution": "No longer relevant"},
        )


def test_match_candidate_state_machine_covers_confirm_reject_and_merge() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    first = make_entity(tenant, entity_type=entity_type)
    second = make_entity(tenant, entity_type=entity_type)
    golden = make_entity(tenant, entity_type=entity_type, is_golden=True)
    rule = make_matching_rule(tenant, entity_type=entity_type)
    candidate = make_candidate(tenant, matching_rule=rule, first=first, second=second)
    reviewer = actor_id("match-reviewer")
    candidate = CANDIDATE_MACHINE.apply(
        candidate,
        "confirm",
        transition_key="confirm-1",
        context={"actor_id": reviewer, "note": "Same legal entity"},
    )
    assert candidate.status == "confirmed"
    assert candidate.reviewed_by == reviewer
    merge = make_merge(tenant, golden_record=golden)
    candidate = CANDIDATE_MACHINE.apply(
        candidate,
        "merge",
        transition_key="candidate-merge-1",
        context={"actor_id": reviewer, "merge_history_id": merge.id},
    )
    assert candidate.status == "merged" and candidate.merge_history_id == merge.id
    with pytest.raises(TerminalStateError):
        CANDIDATE_MACHINE.apply(
            candidate,
            "reject",
            transition_key="late-reject",
            context={"actor_id": reviewer},
        )

    rejected = make_candidate(
        tenant,
        matching_rule=rule,
        first=make_entity(tenant, entity_type=entity_type),
        second=make_entity(tenant, entity_type=entity_type),
    )
    rejected = CANDIDATE_MACHINE.apply(
        rejected,
        "reject",
        transition_key="reject-1",
        context={"actor_id": reviewer, "note": "Different registrations"},
    )
    assert rejected.status == "rejected"


def test_merge_history_state_machine_is_single_terminal_reversal() -> None:
    tenant = uuid.uuid4()
    merge = make_merge(tenant, golden_record=make_entity(tenant, is_golden=True))
    reverser = actor_id("merge-reverser")
    with pytest.raises(GuardFailedError):
        MERGE_MACHINE.apply(
            merge,
            "reverse",
            transition_key="reverse-missing-reason",
            context={"actor_id": reverser},
        )
    merge = MERGE_MACHINE.apply(
        merge,
        "reverse",
        transition_key="reverse-merge-1",
        context={"actor_id": reverser, "reason": "Erroneous duplicate decision"},
    )
    assert merge.status == "reversed"
    assert merge.reversed_by == reverser
    assert merge.reversal_reason == "Erroneous duplicate decision"
    with pytest.raises(TerminalStateError):
        MERGE_MACHINE.apply(
            merge,
            "reverse",
            transition_key="reverse-again",
            context={"actor_id": reverser, "reason": "Again"},
        )

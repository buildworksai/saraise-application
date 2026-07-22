"""Transactional service authority tests for the complete MDM domain."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.modules.master_data_management import services
from src.modules.master_data_management.extension_registry import (
    CapabilityUnavailable,
    EntityRecord,
    ExtensionConflict,
    MDMExtensionRegistry,
)
from src.modules.master_data_management.models import (
    DataQualityIssue,
    MasterDataEntity,
    MasterDataVersion,
    MergeParticipant,
)
from src.modules.master_data_management.services import (
    DashboardService,
    DataQualityService,
    EntityTypeService,
    MDMDomainError,
    MasterEntityService,
    MatchingService,
    MergeService,
    QualityRuleService,
)

from .factories import (
    actor_id,
    make_candidate,
    make_entity,
    make_entity_type,
    make_matching_rule,
)

pytestmark = pytest.mark.django_db


def schema(*, require_email: bool = False) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "format": "email"},
            "tax_id": {"type": "string"},
            "city": {"type": "string"},
        },
        "required": ["email"] if require_email else [],
        "additionalProperties": False,
    }


def create_type(
    tenant: uuid.UUID,
    actor: uuid.UUID,
    *,
    key: str = "customer",
    require_email: bool = False,
    idempotency_key: str | None = None,
):
    return EntityTypeService.create_type(
        tenant,
        actor,
        key=key,
        display_name=key.replace("_", " ").title(),
        description="Governed customer master",
        json_schema=schema(require_email=require_email),
        required_fields=["email"] if require_email else [],
        sensitive_fields=["tax_id"],
        searchable_fields=["name", "email"],
        owner_module="master_data_management",
        idempotency_key=idempotency_key or f"create-type-{key}",
    )


def create_entity(
    tenant: uuid.UUID,
    actor: uuid.UUID,
    entity_type_id: uuid.UUID,
    *,
    code: str = "CUST-001",
    data: dict[str, object] | None = None,
    idempotency_key: str | None = None,
):
    return MasterEntityService.create_entity(
        tenant,
        actor,
        entity_type_id=entity_type_id,
        entity_code=code,
        entity_name=f"Customer {code}",
        data=data if data is not None else {"name": "Acme", "email": "ops@example.test"},
        source_system="manual",
        source_record_id=f"source-{code}",
        idempotency_key=idempotency_key or f"create-entity-{code}",
    )


def assert_domain_error(error_code: str, callable_: object, *args: object, **kwargs: object) -> MDMDomainError:
    with pytest.raises(MDMDomainError) as caught:
        callable_(*args, **kwargs)  # type: ignore[operator]
    assert caught.value.error_code == error_code
    return caught.value


def test_entity_type_create_update_deactivate_and_outbox_contract() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    assert entity_type.tenant_id == tenant
    assert entity_type.created_by == actor
    created = OutboxEvent.objects.for_tenant(tenant).get(
        event_type="mdm.entity_type.created",
        aggregate_id=entity_type.id,
    )
    assert created.payload["actor_id"] == str(actor)

    updated = EntityTypeService.update_type(
        tenant,
        actor,
        entity_type.id,
        expected_schema_version=1,
        changes={
            "json_schema": {
                **schema(),
                "properties": {**schema()["properties"], "phone": {"type": "string"}},  # type: ignore[dict-item]
            }
        },
        idempotency_key="type-schema-v2",
    )
    assert updated.schema_version == 2
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.entity_type.updated").count() == 1

    deactivated = EntityTypeService.deactivate_type(
        tenant,
        actor,
        entity_type.id,
        reason="Replaced by a specialized schema",
        idempotency_key="deactivate-type",
    )
    assert deactivated.is_active is False
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.entity_type.deactivated").exists()


def test_entity_type_idempotency_replay_and_conflicting_replay() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    first = create_type(tenant, actor, idempotency_key="stable-type-request")
    replay = create_type(tenant, actor, idempotency_key="stable-type-request")
    assert replay.id == first.id
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.entity_type.created").count() == 1

    with pytest.raises(MDMDomainError) as caught:
        EntityTypeService.create_type(
            tenant,
            actor,
            key="supplier",
            display_name="Supplier",
            json_schema=schema(),
            idempotency_key="stable-type-request",
        )
    assert caught.value.error_code == "IDEMPOTENCY_CONFLICT"


def test_entity_type_validation_optimistic_conflict_and_tenant_isolation() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant_b, actor)
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        EntityTypeService.update_type,
        tenant_a,
        actor,
        entity_type.id,
        expected_schema_version=1,
        changes={"display_name": "Spoofed"},
        idempotency_key="cross-tenant-update",
    )
    assert_domain_error(
        "SCHEMA_VERSION_CONFLICT",
        EntityTypeService.update_type,
        tenant_b,
        actor,
        entity_type.id,
        expected_schema_version=99,
        changes={"display_name": "Stale"},
        idempotency_key="stale-type-update",
    )
    assert_domain_error(
        "UNSUPPORTED_SCHEMA_KEYWORD",
        EntityTypeService.create_type,
        tenant_a,
        actor,
        key="unsafe_type",
        display_name="Unsafe",
        json_schema={"type": "object", "x-python-hook": "evil"},
        idempotency_key="unsafe-type",
    )
    entity_type.refresh_from_db()
    assert entity_type.display_name == "Customer"


def test_builtin_seed_is_complete_tenant_local_and_idempotent() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    seeded_a = EntityTypeService.seed_builtin_types(tenant_a, actor)
    replay_a = EntityTypeService.seed_builtin_types(tenant_a, actor)
    seeded_b = EntityTypeService.seed_builtin_types(tenant_b, actor)
    assert {item.key for item in seeded_a} == {
        "customer",
        "supplier",
        "product",
        "employee",
        "location",
        "account",
        "material",
    }
    assert [item.id for item in replay_a] == [item.id for item in seeded_a]
    assert {item.id for item in seeded_a}.isdisjoint({item.id for item in seeded_b})
    assert next(item for item in seeded_a if item.key == "supplier").display_name == "Vendor"


def test_create_entity_is_schema_validated_versioned_scoped_scored_and_evented() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor, require_email=True)
    entity = create_entity(tenant, actor, entity_type.id)
    assert entity.status == "active" and entity.version == 1
    assert entity.quality_score == Decimal("0.00")
    version = MasterDataVersion.objects.for_tenant(tenant).get(entity=entity, version_number=1)
    assert version.data_snapshot == entity.data
    assert version.changed_by == actor
    assert OutboxEvent.objects.for_tenant(tenant).filter(
        event_type="mdm.entity.created",
        aggregate_id=entity.id,
    ).exists()
    # With no configured quality rules the record is explicitly unevaluated,
    # never silently awarded a perfect score.
    report = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="no-rules-evaluation",
    )
    assert report.evaluated is False and report.score is None
    assert OutboxEvent.objects.for_tenant(tenant).filter(
        event_type="mdm.entity.quality_scored",
        aggregate_id=entity.id,
        payload__causation_id="no-rules-evaluation",
    ).count() == 1

    # A retry returns the durable original outcome even when rule configuration
    # changes between attempts; an idempotency key cannot become a fresh command.
    QualityRuleService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Email required after first evaluation",
        field_path="email",
        rule_type="required",
        configuration={},
        dimension="completeness",
        severity="error",
        weight="1.0000",
        idempotency_key="late-quality-rule",
    )
    replay = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="no-rules-evaluation",
    )
    assert replay == report
    entity.refresh_from_db()
    assert entity.quality_evaluated_at is None


def test_entity_create_replay_conflict_cross_tenant_type_and_atomic_rollback() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant_a, actor)
    first = create_entity(tenant_a, actor, entity_type.id, idempotency_key="entity-replay")
    replay = create_entity(tenant_a, actor, entity_type.id, idempotency_key="entity-replay")
    assert replay.id == first.id
    assert MasterDataVersion.objects.for_tenant(tenant_a).filter(entity=first).count() == 1
    assert_domain_error(
        "IDEMPOTENCY_CONFLICT",
        create_entity,
        tenant_a,
        actor,
        entity_type.id,
        code="CUST-DIFFERENT",
        idempotency_key="entity-replay",
    )
    assert_domain_error(
        "ENTITY_TYPE_UNAVAILABLE",
        create_entity,
        tenant_b,
        actor,
        entity_type.id,
        code="FOREIGN",
    )

    before = MasterDataEntity.objects.for_tenant(tenant_a).count()
    with patch.object(services, "publish_domain_event", side_effect=RuntimeError("outbox unavailable")):
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            create_entity(tenant_a, actor, entity_type.id, code="ROLLBACK")
    assert MasterDataEntity.objects.for_tenant(tenant_a).count() == before
    assert not MasterDataVersion.objects.for_tenant(tenant_a).filter(entity__entity_code="ROLLBACK").exists()


def test_entity_update_archive_restore_rollback_and_version_conflicts() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    QualityRuleService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Name required",
        field_path="name",
        rule_type="required",
        configuration={},
        dimension="completeness",
        severity="error",
        weight="1.0000",
        idempotency_key="entity-lifecycle-quality-rule",
    )
    entity = create_entity(tenant, actor, entity_type.id)
    updated = MasterEntityService.update_entity(
        tenant,
        actor,
        entity.id,
        expected_version=1,
        changes={"entity_name": "Acme Holdings", "data": {"name": "Acme Holdings", "email": "hq@example.test"}},
        reason="Verified legal name",
        idempotency_key="entity-update-v2",
    )
    assert updated.version == 2 and updated.entity_name == "Acme Holdings"
    updated_replay = MasterEntityService.update_entity(
        tenant,
        actor,
        entity.id,
        expected_version=1,
        changes={"entity_name": "Acme Holdings", "data": {"name": "Acme Holdings", "email": "hq@example.test"}},
        reason="Verified legal name",
        idempotency_key="entity-update-v2",
    )
    assert updated_replay.id == updated.id and updated_replay.version == 2
    assert MasterDataVersion.objects.for_tenant(tenant).filter(entity=entity).count() == 2
    assert_domain_error(
        "VERSION_CONFLICT",
        MasterEntityService.update_entity,
        tenant,
        actor,
        entity.id,
        expected_version=1,
        changes={"entity_name": "Stale"},
        reason="Stale edit",
        idempotency_key="stale-edit",
    )
    assert_domain_error(
        "VALIDATION_ERROR",
        MasterEntityService.update_entity,
        tenant,
        actor,
        entity.id,
        expected_version=2,
        changes={"quality_score": "100.00"},
        reason="Attempt overpost",
        idempotency_key="overpost",
    )

    archived = MasterEntityService.archive_entity(
        tenant,
        actor,
        entity.id,
        expected_version=2,
        reason="Temporarily retired",
        idempotency_key="archive-v3",
    )
    assert archived.status == "archived" and archived.is_deleted is True and archived.version == 3
    archived_replay = MasterEntityService.archive_entity(
        tenant,
        actor,
        entity.id,
        expected_version=2,
        reason="Temporarily retired",
        idempotency_key="archive-v3",
    )
    assert archived_replay.id == archived.id and archived_replay.version == 3
    restored = MasterEntityService.restore_entity(
        tenant,
        actor,
        entity.id,
        expected_version=3,
        reason="Reactivated",
        idempotency_key="restore-v4",
    )
    assert restored.status == "active" and restored.is_deleted is False and restored.version == 4
    restored_replay = MasterEntityService.restore_entity(
        tenant,
        actor,
        entity.id,
        expected_version=3,
        reason="Reactivated",
        idempotency_key="restore-v4",
    )
    assert restored_replay.id == restored.id and restored_replay.version == 4
    rolled_back = MasterEntityService.rollback_to_version(
        tenant,
        actor,
        entity.id,
        1,
        expected_version=4,
        reason="Restore original source values",
        idempotency_key="rollback-v5",
    )
    assert rolled_back.version == 5
    assert rolled_back.entity_name == f"Customer {entity.entity_code}"
    rollback_replay = MasterEntityService.rollback_to_version(
        tenant,
        actor,
        entity.id,
        1,
        expected_version=4,
        reason="Restore original source values",
        idempotency_key="rollback-v5",
    )
    assert rollback_replay.id == rolled_back.id and rollback_replay.version == 5
    assert MasterDataVersion.objects.for_tenant(tenant).filter(entity=entity).count() == 5
    quality_causes = set(
        OutboxEvent.objects.for_tenant(tenant)
        .filter(event_type="mdm.entity.quality_scored", aggregate_id=entity.id)
        .values_list("payload__causation_id", flat=True)
    )
    assert {"entity-update-v2:quality", "archive-v3:quality", "restore-v4:quality", "rollback-v5:quality"} <= quality_causes


def test_resolve_by_code_returns_tenant_record_and_excludes_merged_source() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    type_a = create_type(tenant_a, actor)
    type_b = create_type(tenant_b, actor)
    own = create_entity(tenant_a, actor, type_a.id, code="SHARED")
    create_entity(tenant_b, actor, type_b.id, code="SHARED")
    resolved = MasterEntityService.resolve_by_code(tenant_a, "customer", "SHARED")
    assert resolved.id == own.id and resolved.tenant_id == tenant_a
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        MasterEntityService.resolve_by_code,
        tenant_a,
        "customer",
        "MISSING",
    )


def test_quality_validation_rules_scoring_issue_reconciliation_and_transitions() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    invalid = DataQualityService.validate_payload(tenant, entity_type.id, {"email": "not-an-email"})
    assert invalid.valid is False and invalid.evaluated is True
    assert any(finding.code == "SCHEMA_VALIDATION" for finding in invalid.findings)

    rule = QualityRuleService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Email required",
        field_path="email",
        rule_type="required",
        configuration={},
        dimension="completeness",
        severity="error",
        weight="1.0000",
        idempotency_key="quality-rule-create",
    )
    entity = create_entity(tenant, actor, entity_type.id, data={"name": "No email"})
    entity.refresh_from_db()
    assert entity.quality_score == Decimal("0.00")
    issue = DataQualityIssue.objects.for_tenant(tenant).get(entity=entity, rule=rule)
    assert issue.status == "open"
    failed_report = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="failed-quality-replay",
    )
    failed_replay = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="failed-quality-replay",
    )
    assert failed_report.findings and failed_replay == failed_report
    assigned = DataQualityService.assign_issue(
        tenant,
        actor,
        issue.id,
        actor_id("assignee"),
        transition_key="assign-issue",
    )
    assert assigned.status == "in_review"
    resolved = DataQualityService.resolve_issue(
        tenant,
        actor,
        issue.id,
        resolution="Verified exception",
        transition_key="resolve-issue",
    )
    assert resolved.status == "resolved" and resolved.resolved_by == actor
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.quality_issue.resolved").exists()

    passing = MasterEntityService.update_entity(
        tenant,
        actor,
        entity.id,
        expected_version=entity.version,
        changes={"data": {"name": "Now complete", "email": "complete@example.test"}},
        reason="Completed email",
        idempotency_key="complete-email",
    )
    assert passing.quality_score == Decimal("100.00")

    manual = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="manual-quality-replay",
    )
    entity.refresh_from_db()
    evaluated_at = entity.quality_evaluated_at
    replay = DataQualityService.evaluate_entity(
        tenant,
        actor,
        entity.id,
        idempotency_key="manual-quality-replay",
    )
    entity.refresh_from_db()
    assert replay == manual
    assert entity.quality_evaluated_at == evaluated_at
    assert OutboxEvent.objects.for_tenant(tenant).filter(
        event_type="mdm.entity.quality_scored",
        payload__causation_id="manual-quality-replay",
    ).count() == 1


def test_quality_rule_configuration_update_soft_delete_and_tenant_scope() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    type_a = create_type(tenant_a, actor)
    type_b = create_type(tenant_b, actor)
    rule = QualityRuleService.create_rule(
        tenant_a,
        actor,
        entity_type_id=type_a.id,
        name="Email syntax",
        field_path="email",
        rule_type="format",
        configuration={"pattern": r"^[^@]+@[^@]+$"},
        dimension="conformity",
        severity="warning",
        weight="0.5000",
        idempotency_key="format-rule",
    )
    updated = QualityRuleService.update_rule(
        tenant_a,
        actor,
        rule.id,
        changes={"severity": "error", "weight": "1.0000"},
        idempotency_key="format-rule-update",
    )
    assert updated.severity == "error" and updated.weight == Decimal("1.0000")
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        QualityRuleService.update_rule,
        tenant_b,
        actor,
        rule.id,
        changes={"severity": "critical"},
        idempotency_key="foreign-rule-update",
    )
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        QualityRuleService.create_rule,
        tenant_a,
        actor,
        entity_type_id=type_b.id,
        name="Foreign",
        field_path="email",
        rule_type="required",
        configuration={},
        dimension="completeness",
        severity="error",
        weight="1",
        idempotency_key="foreign-type-rule",
    )
    deleted = QualityRuleService.deactivate_rule(
        tenant_a,
        actor,
        rule.id,
        idempotency_key="deactivate-quality-rule",
    )
    assert deleted.is_deleted is True and deleted.is_active is False and deleted.deleted_at is not None
    delete_replay = QualityRuleService.deactivate_rule(
        tenant_a,
        actor,
        rule.id,
        idempotency_key="deactivate-quality-rule",
    )
    assert delete_replay.id == deleted.id and delete_replay.deleted_at == deleted.deleted_at


@pytest.mark.parametrize(
    ("algorithm", "left_name", "right_name", "expected"),
    [
        ("exact", "Acme Ltd", "Acme Ltd", Decimal("1.0000")),
        ("normalized", "  ACME, LTD. ", "acme ltd", Decimal("1.0000")),
        ("phonetic", "Robert", "Rupert", Decimal("1.0000")),
    ],
)
def test_matching_is_local_deterministic_and_reproducible(
    algorithm: str,
    left_name: str,
    right_name: str,
    expected: Decimal,
) -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    left = create_entity(tenant, actor, entity_type.id, code="LEFT", data={"name": left_name})
    right = create_entity(tenant, actor, entity_type.id, code="RIGHT", data={"name": right_name})
    rule = MatchingService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name=f"{algorithm} legal name",
        algorithm=algorithm,
        field_weights={"name": "1.0000"},
        blocking_fields=[],
        review_threshold="0.5000",
        auto_confirm_threshold="0.9500",
        idempotency_key=f"rule-{algorithm}",
    )
    first = MatchingService.preview_pair(tenant, left.id, right.id, rule_id=rule.id)
    second = MatchingService.preview_pair(tenant, left.id, right.id, rule_id=rule.id)
    assert first == second
    assert first.confidence == expected
    assert first.evidence == {"algorithm": algorithm, "strategy_version": 1}
    assert first.outcome == "auto_confirm"


def test_matching_rule_validation_candidate_review_uniqueness_and_scope() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant_a)
    left = make_entity(tenant_a, entity_type=entity_type, data={"name": "Acme"})
    right = make_entity(tenant_a, entity_type=entity_type, data={"name": "Acme"})
    rule = make_matching_rule(
        tenant_a,
        entity_type=entity_type,
        field_weights={"name": "1.0000"},
        blocking_fields=[],
    )
    candidate = make_candidate(tenant_a, matching_rule=rule, first=left, second=right)
    reviewed = MatchingService.review_candidate(
        tenant_a,
        actor,
        candidate.id,
        decision="confirm",
        note="Same registration",
        transition_key="review-candidate",
    )
    assert reviewed.status == "confirmed" and reviewed.reviewed_by == actor
    replay = MatchingService.review_candidate(
        tenant_a,
        actor,
        candidate.id,
        decision="confirm",
        note="Same registration",
        transition_key="review-candidate",
    )
    assert replay.status == "confirmed"
    assert len(replay.transition_history) == 1
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        MatchingService.review_candidate,
        tenant_b,
        actor,
        candidate.id,
        decision="reject",
        note="Spoof",
        transition_key="cross-tenant-review",
    )
    assert_domain_error(
        "INVALID_MATCH_WEIGHTS",
        MatchingService.create_rule,
        tenant_a,
        actor,
        entity_type_id=entity_type.id,
        name="Invalid weights",
        algorithm="exact",
        field_weights={"name": "0.7"},
        blocking_fields=[],
        review_threshold="0.5",
        auto_confirm_threshold="0.9",
        idempotency_key="invalid-weight-rule",
    )
    deleted = MatchingService.deactivate_rule(
        tenant_a,
        actor,
        rule.id,
        idempotency_key="deactivate-matching-rule",
    )
    replayed_delete = MatchingService.deactivate_rule(
        tenant_a,
        actor,
        rule.id,
        idempotency_key="deactivate-matching-rule",
    )
    assert replayed_delete.id == deleted.id and replayed_delete.deleted_at == deleted.deleted_at


def test_merge_preview_survivorship_merge_idempotency_and_reverse() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    left = create_entity(
        tenant,
        actor,
        entity_type.id,
        code="LEFT",
        data={"name": "Acme", "email": "old@example.test", "city": "Pune"},
    )
    right = create_entity(
        tenant,
        actor,
        entity_type.id,
        code="RIGHT",
        data={"name": "Acme Holdings", "email": "verified@example.test", "city": "Pune"},
    )
    preview = MergeService.preview_merge(
        tenant,
        actor,
        entity_ids=[right.id, left.id],
        survivorship_overrides={"email": right.id},
    )
    assert preview.entity_ids == tuple(sorted((left.id, right.id), key=str))
    assert preview.golden_values["data"]["email"] == "verified@example.test"  # type: ignore[index]
    assert preview.provenance["data.email"] == right.id

    merge = MergeService.merge_entities(
        tenant,
        actor,
        entity_ids=[left.id, right.id],
        survivorship_overrides={"email": right.id},
        reason="Duplicate customer registrations",
        idempotency_key="merge-left-right",
    )
    assert merge.status == "applied"
    assert MergeParticipant.objects.for_tenant(tenant).filter(merge_history=merge).count() == 2
    assert MergeParticipant.objects.for_tenant(tenant).filter(merge_history=merge, role="survivor").count() == 1
    assert (
        MasterDataEntity.objects.for_tenant(tenant)
        .filter(status="merged", golden_record=merge.golden_record)
        .count()
        == 1
    )
    replay = MergeService.merge_entities(
        tenant,
        actor,
        entity_ids=[left.id, right.id],
        survivorship_overrides={"email": right.id},
        reason="Duplicate customer registrations",
        idempotency_key="merge-left-right",
    )
    assert replay.id == merge.id
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.entities.merged").count() == 1

    reversed_merge = MergeService.reverse_merge(
        tenant,
        actor,
        merge.id,
        reason="Steward found separate legal entities",
        transition_key="reverse-left-right",
    )
    assert reversed_merge.status == "reversed"
    assert MasterDataEntity.objects.for_tenant(tenant).filter(pk__in=(left.id, right.id), status="active").count() == 2
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="mdm.merge.reversed").count() == 1


def test_merge_rejects_cross_tenant_type_mismatch_and_reversal_conflict() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    type_a = create_type(tenant_a, actor, key="customer")
    other_a = create_type(tenant_a, actor, key="supplier")
    type_b = create_type(tenant_b, actor, key="customer")
    first = create_entity(tenant_a, actor, type_a.id, code="A-1")
    wrong_type = create_entity(tenant_a, actor, other_a.id, code="A-2")
    foreign = create_entity(tenant_b, actor, type_b.id, code="B-1")
    assert_domain_error(
        "MERGE_TYPE_MISMATCH",
        MergeService.preview_merge,
        tenant_a,
        actor,
        entity_ids=[first.id, wrong_type.id],
        survivorship_overrides={},
    )
    assert_domain_error(
        "RESOURCE_NOT_FOUND",
        MergeService.preview_merge,
        tenant_a,
        actor,
        entity_ids=[first.id, foreign.id],
        survivorship_overrides={},
    )

    second = create_entity(tenant_a, actor, type_a.id, code="A-3")
    merge = MergeService.merge_entities(
        tenant_a,
        actor,
        entity_ids=[first.id, second.id],
        survivorship_overrides={},
        reason="Initially considered duplicates",
        idempotency_key="merge-conflict",
    )
    source = MergeParticipant.objects.for_tenant(tenant_a).filter(
        merge_history=merge,
        role="merged_source",
    ).get().source_entity
    MasterDataEntity.objects.filter(pk=source.id).update(version=source.version + 1)
    assert_domain_error(
        "MERGE_REVERSAL_CONFLICT",
        MergeService.reverse_merge,
        tenant_a,
        actor,
        merge.id,
        reason="Attempt reversal after later edit",
        transition_key="reverse-conflict",
    )
    merge.refresh_from_db()
    assert merge.status == "applied"


def test_dashboard_aggregates_are_bounded_to_tenant_and_optional_type() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    actor = actor_id()
    type_a = create_type(tenant_a, actor)
    type_b = create_type(tenant_b, actor)
    create_entity(tenant_a, actor, type_a.id, code="A-1")
    create_entity(tenant_a, actor, type_a.id, code="A-2")
    create_entity(tenant_b, actor, type_b.id, code="B-1")

    summary = DashboardService.get_summary(tenant_a)
    assert summary["entity_count"] == 2
    assert summary["entity_status_counts"] == {"active": 2}
    assert summary["quality_distribution"]["not_evaluated"] == 2  # type: ignore[index]
    assert all(
        item["entity_name"].startswith("Customer A-")
        for item in summary["recent_activity"]  # type: ignore[union-attr]
    )
    filtered = DashboardService.get_summary(tenant_a, entity_type_id=type_a.id)
    assert filtered["entity_count"] == 2


def test_durable_scan_requests_are_tenant_scoped_idempotent_and_honest() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = create_type(tenant, actor)
    rule = MatchingService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Deduplicate by name",
        algorithm="normalized",
        field_weights={"name": "1.0000"},
        blocking_fields=[],
        review_threshold="0.75",
        auto_confirm_threshold="0.95",
        idempotency_key="dedupe-rule",
    )
    quality_job = DataQualityService.enqueue_quality_scan(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        idempotency_key="quality-scan-1",
    )
    match_job = MatchingService.enqueue_deduplication_scan(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        rule_ids=[rule.id],
        idempotency_key="match-scan-1",
    )
    assert quality_job.status == "queued" and match_job.status == "queued"
    assert {quality_job.command, match_job.command} == {
        "master_data_management.quality_scan",
        "master_data_management.deduplication_scan",
    }
    assert AsyncJob.objects.for_tenant(tenant).count() == 2
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="async_job.enqueued").count() == 2
    replay = DataQualityService.enqueue_quality_scan(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        idempotency_key="quality-scan-1",
    )
    assert replay.id == quality_job.id

    other_type = create_type(tenant, actor, key="supplier")
    assert_domain_error(
        "IDEMPOTENCY_CONFLICT",
        DataQualityService.enqueue_quality_scan,
        tenant,
        actor,
        entity_type_id=other_type.id,
        idempotency_key="quality-scan-1",
    )
    other_rule = MatchingService.create_rule(
        tenant,
        actor,
        entity_type_id=other_type.id,
        name="Supplier identity",
        algorithm="exact",
        field_weights={"name": "1.0000"},
        blocking_fields=[],
        review_threshold="0.5000",
        auto_confirm_threshold="1.0000",
        idempotency_key="supplier-match-rule",
    )
    assert_domain_error(
        "IDEMPOTENCY_CONFLICT",
        MatchingService.enqueue_deduplication_scan,
        tenant,
        actor,
        entity_type_id=other_type.id,
        rule_ids=[other_rule.id],
        idempotency_key="match-scan-1",
    )


def test_paid_extension_registry_is_versioned_collision_safe_and_fails_explicitly() -> None:
    class Validator:
        owner_module = "paid_healthcare"
        key = "patient_identifier"

        def __init__(self, version: str) -> None:
            self.version = version

        def validate(self, tenant_id: uuid.UUID, entity: EntityRecord) -> tuple[object, ...]:
            del tenant_id, entity
            return ()

    registry = MDMExtensionRegistry()
    first = Validator("1.0.0")
    second = Validator("2.0.0")
    registered = registry.register("validator", first)
    assert registry.resolve("validator", "paid_healthcare", "patient_identifier", "1.0.0") is first
    assert registry.register("validator", first) is registered
    with pytest.raises(ExtensionConflict):
        registry.register("validator", Validator("1.0.0"))
    with pytest.raises(ExtensionConflict, match="explicitly name"):
        registry.register("validator", second)
    registry.register("validator", second, replaces_version="1.0.0")
    assert registry.resolve("validator", "paid_healthcare", "patient_identifier", "2.0.0") is second
    with pytest.raises(CapabilityUnavailable) as unavailable:
        registry.resolve("validator", "paid_healthcare", "patient_identifier", "1.0.0")
    assert unavailable.value.code == "CAPABILITY_UNAVAILABLE"


def test_extension_entity_record_is_immutable_policy_filtered_dto() -> None:
    record = EntityRecord(
        tenant_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        entity_type_key="patient",
        entity_code="PAT-001",
        entity_name="Masked Patient",
        data={"display_name": "Masked", "nested": {"value": "safe"}},
        version=1,
        schema_version=1,
        purpose="projection",
        allowed_fields=frozenset({"display_name", "nested.value"}),
    )
    with pytest.raises(TypeError):
        record.data["display_name"] = "Tampered"  # type: ignore[index]
    with pytest.raises(TypeError):
        record.data["nested"]["value"] = "Tampered"  # type: ignore[index]
    with pytest.raises(AttributeError):
        record.entity_name = "Tampered"  # type: ignore[misc]

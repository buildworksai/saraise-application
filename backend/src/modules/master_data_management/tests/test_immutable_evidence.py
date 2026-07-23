"""Focused proof for immutable MDM evidence and reversal safety."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.models import F

from src.modules.master_data_management.models import (
    DataQualityIssue,
    DataQualityRuleVersion,
    MatchCandidate,
    MatchingRuleVersion,
    MergeReversal,
)
from src.modules.master_data_management.services import (
    MatchingService,
    MergeService,
    QualityRuleService,
)

from .factories import (
    actor_id,
    make_candidate,
    make_entity,
    make_entity_type,
    make_issue,
    make_matching_rule,
    make_quality_rule,
)

pytestmark = pytest.mark.django_db


def test_issue_and_candidate_evidence_reject_model_queryset_and_database_updates() -> None:
    tenant = uuid.uuid4()
    entity_type = make_entity_type(tenant)
    entity = make_entity(tenant, entity_type=entity_type)
    quality_rule = make_quality_rule(tenant, entity_type=entity_type)
    issue = make_issue(tenant, entity=entity, rule=quality_rule)
    issue.evidence = {"tampered": True}
    with pytest.raises(ValidationError, match="evidence is immutable"):
        issue.save()
    with pytest.raises(ValidationError, match="evidence is immutable"):
        DataQualityIssue.objects.filter(pk=issue.pk).update(evidence={"tampered": True})

    matching_rule = make_matching_rule(tenant, entity_type=entity_type)
    candidate = make_candidate(
        tenant,
        matching_rule=matching_rule,
        first=entity,
        second=make_entity(tenant, entity_type=entity_type),
    )
    candidate.field_scores = {"email": "0.0000"}
    with pytest.raises(ValidationError, match="field scores and evidence are immutable"):
        candidate.save()
    with pytest.raises(ValidationError, match="evidence is immutable"):
        MatchCandidate.objects.filter(pk=candidate.pk).update(evidence={"tampered": True})

    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE mdm_quality_issues SET evidence = %s WHERE id = %s",
                [json.dumps({"tampered": True}), issue.pk.hex],
            )


def test_rule_services_create_append_only_correlated_versions() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    quality = QualityRuleService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Email required",
        field_path="email",
        rule_type="required",
        configuration={},
        dimension="completeness",
        severity="error",
        weight=Decimal("1.0000"),
        idempotency_key="quality-create-version",
    )
    QualityRuleService.update_rule(
        tenant,
        actor,
        quality.id,
        changes={"severity": "critical"},
        idempotency_key="quality-update-version",
    )
    quality_versions = list(
        DataQualityRuleVersion.objects.for_tenant(tenant).filter(rule=quality).order_by("version_number")
    )
    assert [version.version_number for version in quality_versions] == [1, 2]
    assert quality_versions[0].snapshot["severity"] == "error"
    assert quality_versions[1].snapshot["severity"] == "critical"
    assert all(version.correlation_id for version in quality_versions)
    with pytest.raises(ValidationError, match="Append-only"):
        quality_versions[0].save()
    quality_export = QualityRuleService.export_document(tenant, quality.id)
    QualityRuleService.rollback(
        tenant,
        actor,
        quality.id,
        version_number=1,
        reason="Restore the original severity",
        idempotency_key="quality-rollback-version",
    )
    quality.refresh_from_db()
    assert quality.severity == "error"
    QualityRuleService.import_document(
        tenant,
        actor,
        quality.id,
        document=quality_export,
        reason="Promote the reviewed portable document",
        idempotency_key="quality-import-version",
    )
    quality.refresh_from_db()
    assert quality.severity == "critical"
    assert QualityRuleService.version_history(tenant, quality.id).count() == 4

    matching = MatchingService.create_rule(
        tenant,
        actor,
        entity_type_id=entity_type.id,
        name="Customer identity",
        algorithm="normalized",
        field_weights={"email": "1.0000"},
        blocking_fields=[],
        review_threshold="0.7000",
        auto_confirm_threshold="0.9500",
        idempotency_key="matching-create-version",
    )
    MatchingService.update_rule(
        tenant,
        actor,
        matching.id,
        changes={"review_threshold": "0.8000"},
        idempotency_key="matching-update-version",
    )
    matching_versions = list(
        MatchingRuleVersion.objects.for_tenant(tenant).filter(rule=matching).order_by("version_number")
    )
    assert [version.version_number for version in matching_versions] == [1, 2]
    assert matching_versions[0].snapshot["review_threshold"] == "0.7000"
    assert matching_versions[1].snapshot["review_threshold"] == "0.8000"
    matching_export = MatchingService.export_document(tenant, matching.id)
    MatchingService.rollback(
        tenant,
        actor,
        matching.id,
        version_number=1,
        reason="Restore reviewed threshold",
        idempotency_key="matching-rollback-version",
    )
    matching.refresh_from_db()
    assert matching.review_threshold == Decimal("0.7000")
    MatchingService.import_document(
        tenant,
        actor,
        matching.id,
        document=matching_export,
        reason="Reapply portable matching policy",
        idempotency_key="matching-import-version",
    )
    matching.refresh_from_db()
    assert matching.review_threshold == Decimal("0.8000")
    assert MatchingService.version_history(tenant, matching.id).count() == 4


def test_merge_history_is_append_only_and_reversal_preview_reports_version_conflicts() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    first = make_entity(tenant, entity_type=entity_type, entity_code="A-1")
    second = make_entity(tenant, entity_type=entity_type, entity_code="A-2")
    merge = MergeService.merge_entities(
        tenant,
        actor,
        entity_ids=[first.id, second.id],
        survivorship_overrides={},
        reason="Duplicate registrations",
        idempotency_key="immutable-merge",
    )
    clean_preview = MergeService.preview_reversal(tenant, merge.id)
    assert clean_preview.can_reverse is True
    assert clean_preview.conflicts == ()

    participant_id = next(iter(clean_preview.participant_versions))
    make_entity(tenant, entity_type=entity_type)  # proves unrelated rows do not affect the preview
    type(first).objects.filter(pk=participant_id).update(version=F("version") + 1)
    conflict_preview = MergeService.preview_reversal(tenant, merge.id)
    assert conflict_preview.can_reverse is False
    assert len(conflict_preview.conflicts) == 1
    assert conflict_preview.conflicts[0].code == "MERGE_PARTICIPANT_VERSION_CONFLICT"

    merge.reason = "Tampered evidence"
    with pytest.raises(ValidationError, match="append-only"):
        merge.save()


def test_reversal_creates_immutable_evidence_without_mutating_merge_history() -> None:
    tenant = uuid.uuid4()
    actor = actor_id()
    entity_type = make_entity_type(tenant)
    first = make_entity(tenant, entity_type=entity_type, entity_code="B-1")
    second = make_entity(tenant, entity_type=entity_type, entity_code="B-2")
    merge = MergeService.merge_entities(
        tenant,
        actor,
        entity_ids=[first.id, second.id],
        survivorship_overrides={},
        reason="Duplicate registrations",
        idempotency_key="reversal-evidence-merge",
    )
    original_reason = merge.reason
    result = MergeService.reverse_merge(
        tenant,
        actor,
        merge.id,
        reason="Steward confirmed separate records",
        transition_key="immutable-reversal",
    )
    assert result.status == "reversed"
    reversal = MergeReversal.objects.for_tenant(tenant).get(merge_history=merge)
    assert reversal.reason == "Steward confirmed separate records"
    assert reversal.correlation_id
    assert reversal.participant_versions
    persisted = type(merge).objects.for_tenant(tenant).get(pk=merge.id)
    assert persisted.status == "applied"
    assert persisted.reason == original_reason
    assert persisted.reversed_by is None
    assert persisted.current_status == "reversed"
    with pytest.raises(ValidationError, match="Append-only"):
        reversal.save()

"""Deterministic, tenant-explicit domain factories for MDM tests.

These helpers deliberately require a tenant UUID for every aggregate.  Tests
therefore cannot accidentally create an unowned control row or conceal a
cross-tenant relation behind an implicit global default.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from ..models import (
    DataQualityIssue,
    DataQualityRule,
    MasterDataEntity,
    MasterDataVersion,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MergeHistory,
    MergeParticipant,
)


def actor_id(label: str = "steward") -> uuid.UUID:
    """Return a stable UUID audit reference without inventing a Django FK."""

    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:test-actor:{label}")


def make_entity_type(tenant_id: uuid.UUID, **overrides: Any) -> MasterEntityType:
    suffix = uuid.uuid4().hex[:8]
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "key": f"customer_{suffix}",
        "display_name": "Customer",
        "description": "Tenant-owned customer master",
        "json_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "tax_id": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            },
        },
        "required_fields": ["email"],
        "sensitive_fields": ["tax_id"],
        "searchable_fields": ["email", "address.city"],
        "created_by": actor_id(),
    }
    values.update(overrides)
    return MasterEntityType.objects.create(**values)


def make_entity(
    tenant_id: uuid.UUID,
    *,
    entity_type: MasterEntityType | None = None,
    **overrides: Any,
) -> MasterDataEntity:
    entity_type = entity_type or make_entity_type(tenant_id)
    suffix = uuid.uuid4().hex[:10].upper()
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity_type": entity_type,
        "entity_code": f"CUST-{suffix}",
        "entity_name": "Acme Customer",
        "data": {"email": f"customer-{suffix.lower()}@example.test", "tax_id": "TAX-SECRET"},
        "source_system": "manual",
        "source_record_id": f"source-{suffix.lower()}",
        "created_by": actor_id(),
    }
    values.update(overrides)
    return MasterDataEntity.objects.create(**values)


def make_version(
    tenant_id: uuid.UUID,
    *,
    entity: MasterDataEntity,
    **overrides: Any,
) -> MasterDataVersion:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity": entity,
        "version_number": entity.version,
        "entity_type_key": entity.entity_type.key,
        "entity_code": entity.entity_code,
        "entity_name": entity.entity_name,
        "data_snapshot": dict(entity.data),
        "status_snapshot": entity.status,
        "quality_score_snapshot": entity.quality_score,
        "changed_fields": ["entity_code", "entity_name", "data"],
        "change_reason": "Initial version",
        "changed_by": actor_id(),
        "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
    }
    values.update(overrides)
    return MasterDataVersion.objects.create(**values)


def make_quality_rule(
    tenant_id: uuid.UUID,
    *,
    entity_type: MasterEntityType,
    **overrides: Any,
) -> DataQualityRule:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity_type": entity_type,
        "name": f"Email required {uuid.uuid4().hex[:8]}",
        "field_path": "email",
        "rule_type": "required",
        "configuration": {},
        "dimension": "completeness",
        "severity": "error",
        "weight": Decimal("1.0000"),
        "created_by": actor_id(),
    }
    values.update(overrides)
    return DataQualityRule.objects.create(**values)


def make_issue(
    tenant_id: uuid.UUID,
    *,
    entity: MasterDataEntity,
    rule: DataQualityRule | None = None,
    **overrides: Any,
) -> DataQualityIssue:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity": entity,
        "rule": rule,
        "field_path": "email",
        "dimension": "completeness",
        "severity": "error",
        "message": "Email is required",
        "evidence": {"code": "required_value_missing"},
        "created_by": actor_id(),
    }
    values.update(overrides)
    return DataQualityIssue.objects.create(**values)


def make_matching_rule(
    tenant_id: uuid.UUID,
    *,
    entity_type: MasterEntityType,
    **overrides: Any,
) -> MatchingRule:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity_type": entity_type,
        "name": f"Customer identity {uuid.uuid4().hex[:8]}",
        "algorithm": "normalized",
        "field_weights": {"entity_name": "0.6000", "email": "0.4000"},
        "blocking_fields": ["address.city"],
        "review_threshold": Decimal("0.7000"),
        "auto_confirm_threshold": Decimal("0.9500"),
        "created_by": actor_id(),
    }
    values.update(overrides)
    return MatchingRule.objects.create(**values)


def make_candidate(
    tenant_id: uuid.UUID,
    *,
    matching_rule: MatchingRule,
    first: MasterDataEntity,
    second: MasterDataEntity,
    **overrides: Any,
) -> MatchCandidate:
    left, right = sorted((first, second), key=lambda entity: entity.id)
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "matching_rule": matching_rule,
        "left_entity": left,
        "right_entity": right,
        "confidence": Decimal("0.8500"),
        "field_scores": {"entity_name": "1.0000", "email": "0.6250"},
        "evidence": {"algorithm": "normalized", "algorithm_version": "1"},
        "created_by": actor_id(),
    }
    values.update(overrides)
    return MatchCandidate.objects.create(**values)


def make_merge(
    tenant_id: uuid.UUID,
    *,
    golden_record: MasterDataEntity,
    **overrides: Any,
) -> MergeHistory:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "golden_record": golden_record,
        "survivorship_policy": {"entity_name": str(golden_record.id)},
        "golden_snapshot_before": {"version": golden_record.version, "data": dict(golden_record.data)},
        "golden_snapshot_after": {"version": golden_record.version, "data": dict(golden_record.data)},
        "reason": "Consolidate duplicate records",
        "merged_by": actor_id(),
        "idempotency_key": f"merge-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4().hex[:16]}",
    }
    values.update(overrides)
    return MergeHistory.objects.create(**values)


def make_participant(
    tenant_id: uuid.UUID,
    *,
    merge_history: MergeHistory,
    source_entity: MasterDataEntity,
    **overrides: Any,
) -> MergeParticipant:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "merge_history": merge_history,
        "source_entity": source_entity,
        "source_version": source_entity.version,
        "source_snapshot": {
            "entity_code": source_entity.entity_code,
            "entity_name": source_entity.entity_name,
            "data": dict(source_entity.data),
            "version": source_entity.version,
        },
        "role": "merged_source",
    }
    values.update(overrides)
    return MergeParticipant.objects.create(**values)


__all__ = [
    "actor_id",
    "make_candidate",
    "make_entity",
    "make_entity_type",
    "make_issue",
    "make_matching_rule",
    "make_merge",
    "make_participant",
    "make_quality_rule",
    "make_version",
]

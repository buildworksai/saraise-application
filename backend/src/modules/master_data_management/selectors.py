"""Bounded, tenant-explicit MDM read selectors."""

from __future__ import annotations

from uuid import UUID

from django.db.models import Count, QuerySet

from .models import (
    DataQualityIssue,
    DataQualityRule,
    MasterDataEntity,
    MasterDataVersion,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MergeHistory,
)


def entity_types(tenant_id: UUID) -> QuerySet[MasterEntityType]:
    return MasterEntityType.objects.for_tenant(tenant_id).filter(is_deleted=False)


def entities(tenant_id: UUID, *, include_deleted: bool = False) -> QuerySet[MasterDataEntity]:
    queryset = MasterDataEntity.objects.for_tenant(tenant_id).select_related("entity_type", "golden_record")
    return queryset if include_deleted else queryset.filter(is_deleted=False)


def versions(tenant_id: UUID, entity_id: UUID) -> QuerySet[MasterDataVersion]:
    return MasterDataVersion.objects.for_tenant(tenant_id).filter(entity_id=entity_id).order_by("-version_number")


def quality_rules(tenant_id: UUID) -> QuerySet[DataQualityRule]:
    return DataQualityRule.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related("entity_type")


def quality_issues(tenant_id: UUID) -> QuerySet[DataQualityIssue]:
    return DataQualityIssue.objects.for_tenant(tenant_id).select_related("entity", "rule", "entity__entity_type")


def matching_rules(tenant_id: UUID) -> QuerySet[MatchingRule]:
    return MatchingRule.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related("entity_type")


def match_candidates(tenant_id: UUID) -> QuerySet[MatchCandidate]:
    return MatchCandidate.objects.for_tenant(tenant_id).select_related(
        "matching_rule",
        "left_entity",
        "left_entity__entity_type",
        "right_entity",
        "right_entity__entity_type",
        "merge_history",
    )


def merges(tenant_id: UUID) -> QuerySet[MergeHistory]:
    return (
        MergeHistory.objects.for_tenant(tenant_id)
        .select_related("golden_record", "golden_record__entity_type", "reversal")
        .prefetch_related("participants", "participants__source_entity")
    )


def entity_issue_counts(tenant_id: UUID, entity_ids: list[UUID]) -> dict[UUID, int]:
    rows = (
        DataQualityIssue.objects.for_tenant(tenant_id)
        .filter(entity_id__in=entity_ids, status__in=("open", "in_review"))
        .values("entity_id")
        .annotate(total=Count("id"))
    )
    return {row["entity_id"]: row["total"] for row in rows}


__all__ = [
    "entities",
    "entity_issue_counts",
    "entity_types",
    "match_candidates",
    "matching_rules",
    "merges",
    "quality_issues",
    "quality_rules",
    "versions",
]

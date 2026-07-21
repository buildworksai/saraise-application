"""Versioned, tenant-safe contribution surface for industry modules.

Paid modules contribute declarative contracts only.  They cannot inject code,
credentials, or URLs into this foundation module.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence
from uuid import UUID

from django.db import transaction

from .models import MonitoringExtension
from .services import ConflictError, MonitoringError, _actor, _tenant

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,159}$")
VERSION_PATTERN = re.compile(r"^[1-9]\d*\.\d+(?:\.\d+)?$")
NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
FORBIDDEN_KEYS = frozenset({"api_key", "authorization", "credential", "password", "secret", "token", "url"})


@dataclass(frozen=True)
class MonitoringContribution:
    extension_key: str
    provider: str
    schema_version: str = "1.0"
    metric_namespaces: Sequence[str] = field(default_factory=tuple)
    semantic_attributes: Mapping[str, str] = field(default_factory=dict)
    dashboard_templates: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    slo_packs: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    alert_rule_templates: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    drill_down_links: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    event_consumers: Sequence[str] = field(default_factory=tuple)


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in FORBIDDEN_KEYS
            or str(key).lower().endswith(("_secret", "_token", "_url"))
            or _contains_forbidden(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_forbidden(item) for item in value)
    return False


def validate_contribution(contribution: MonitoringContribution) -> None:
    if not KEY_PATTERN.fullmatch(contribution.extension_key):
        raise MonitoringError("extension_key must be a stable dotted identifier.")
    if not KEY_PATTERN.fullmatch(contribution.provider):
        raise MonitoringError("provider must be a stable dotted identifier.")
    if not VERSION_PATTERN.fullmatch(contribution.schema_version):
        raise MonitoringError("schema_version must use major.minor or major.minor.patch.")
    if not contribution.metric_namespaces:
        raise MonitoringError("At least one metric namespace is required.")
    invalid = [value for value in contribution.metric_namespaces if not NAMESPACE_PATTERN.fullmatch(value)]
    if invalid:
        raise MonitoringError("Metric namespaces must use lowercase dot notation.", details={"invalid": invalid})
    if len(set(contribution.metric_namespaces)) != len(contribution.metric_namespaces):
        raise MonitoringError("Metric namespaces must be unique.")
    if _contains_forbidden(asdict(contribution)):
        raise MonitoringError("Contribution contracts cannot contain credentials or network destinations.")
    for consumer in contribution.event_consumers:
        if not KEY_PATTERN.fullmatch(consumer.replace("*", "all")):
            raise MonitoringError("Event consumers must be stable event-type patterns.")


class MonitoringExtensionRegistry:
    @transaction.atomic
    def register(
        self,
        tenant_id: UUID | str,
        contribution: MonitoringContribution,
        *,
        created_by: UUID | str | None = None,
    ) -> MonitoringExtension:
        tenant = _tenant(tenant_id)
        validate_contribution(contribution)
        values = asdict(contribution)
        existing = (
            MonitoringExtension.objects.select_for_update()
            .for_tenant(tenant)
            .filter(
                extension_key=contribution.extension_key,
                schema_version=contribution.schema_version,
                is_deleted=False,
            )
            .first()
        )
        if existing:
            comparable = {key: getattr(existing, key) for key in values}
            # JSONField normalizes every tuple in the immutable contribution
            # dataclass to a list. Compare that canonical JSON representation
            # so retrying an identical registration is genuinely idempotent.
            expected = json.loads(json.dumps(values))
            if comparable != expected:
                raise ConflictError("This contribution version is already registered with different content.")
            return existing
        return MonitoringExtension.objects.create(tenant_id=tenant, created_by=_actor(created_by), **values)

    def resolve(
        self,
        tenant_id: UUID | str,
        *,
        provider: str | None = None,
        extension_key: str | None = None,
    ):
        queryset = MonitoringExtension.objects.for_tenant(_tenant(tenant_id)).filter(is_active=True, is_deleted=False)
        if provider:
            queryset = queryset.filter(provider=provider)
        if extension_key:
            queryset = queryset.filter(extension_key=extension_key)
        return queryset.order_by("provider", "extension_key", "schema_version")


__all__ = ["MonitoringContribution", "MonitoringExtensionRegistry", "validate_contribution"]

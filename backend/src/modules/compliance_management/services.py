"""Tenant-safe domain services for the open-source compliance workspace.

Controllers in this module are deliberately thin.  Relationship resolution,
lifecycle guards, configuration, audit capture, and all writes live here so
that HTTP, jobs, and paid extensions execute the same rules.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from src.core.auth_utils import get_user_tenant_id

from .models import (
    ComplianceActivity,
    ComplianceAssessment,
    ComplianceConfigurationRevision,
    ComplianceEvidence,
    ComplianceFramework,
    CompliancePolicy,
    CompliancePolicyVersion,
    ComplianceRequirement,
    EvidenceRequirementLink,
    RequirementPolicyMapping,
)


class ComplianceError(Exception):
    """Base error translated by the governed API."""


class ComplianceNotFound(ComplianceError):
    """A tenant-visible resource does not exist."""


class ComplianceConflict(ComplianceError):
    """The requested command conflicts with persisted state."""


class ComplianceValidationError(ComplianceError):
    """A domain invariant failed."""

    def __init__(self, detail: Mapping[str, Sequence[str]] | str):
        self.detail = (
            {"non_field_errors": [detail]}
            if isinstance(detail, str)
            else {key: list(value) for key, value in detail.items()}
        )
        super().__init__(next(iter(next(iter(self.detail.values()), ["Invalid input."])), "Invalid input."))


class ComplianceDependencyUnavailable(ComplianceError):
    """A real dependency needed to complete the command is unavailable."""


class DmsReferenceValidator(Protocol):
    def validate_document_reference(self, tenant_id: UUID, document_id: UUID) -> Mapping[str, object]: ...


ALLOWED_ORDERINGS: dict[str, frozenset[str]] = {
    "framework": frozenset({"name", "code", "created_at"}),
    "requirement": frozenset({"sort_order", "code", "updated_at"}),
    "policy": frozenset({"code", "title", "next_review_date", "updated_at"}),
    "mapping": frozenset({"mapped_at", "coverage"}),
    "assessment": frozenset({"assessed_at", "due_date"}),
    "evidence": frozenset({"collected_at", "valid_until", "name"}),
    "activity": frozenset({"occurred_at", "action"}),
}
SAFE_MARKUP = re.compile(r"<(?:script|iframe|object|embed|link|meta)\b", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ENTITY_TYPES = {
    "framework", "requirement", "policy", "policy_version", "mapping",
    "assessment", "evidence", "evidence_link", "configuration",
}


def _uuid(value: UUID | str, field: str = "id") -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ComplianceValidationError({field: ["Must be a valid UUID."]}) from exc


def _actor(actor: object | None) -> object | None:
    if actor is None:
        return None
    if getattr(actor, "pk", None) is not None:
        return actor
    try:
        return get_user_model().objects.filter(pk=actor).first()
    except (TypeError, ValueError):
        return None


def _validate_model(instance: object) -> None:
    try:
        instance.full_clean()  # type: ignore[attr-defined]
    except DjangoValidationError as exc:
        raise ComplianceValidationError(
            getattr(exc, "message_dict", {"non_field_errors": exc.messages})
        ) from exc


def _ordering(value: str | None, resource: str, fallback: str) -> str:
    requested = value or fallback
    bare = requested.removeprefix("-")
    if bare not in ALLOWED_ORDERINGS[resource]:
        raise ComplianceValidationError({"ordering": ["Unsupported ordering field."]})
    return requested


def _only(data: Mapping[str, object], allowed: set[str]) -> dict[str, object]:
    unknown = set(data) - allowed
    if unknown:
        raise ComplianceValidationError({key: ["Unknown or read-only field."] for key in sorted(unknown)})
    return dict(data)


def _validate_category(tenant_id: UUID | str, category: object) -> None:
    configured = _effective_or_defaults(tenant_id)["regulation_categories"]
    if not isinstance(category, str) or category not in configured:
        raise ComplianceValidationError({"category": ["Select a category from active configuration."]})


def _validate_owner(tenant_id: UUID | str, owner: object | None) -> None:
    if owner is None:
        return
    try:
        owner_tenant = get_user_tenant_id(owner)
    except Exception as exc:
        raise ComplianceValidationError({"owner_id": ["Owner tenant could not be verified."]}) from exc
    if str(owner_tenant) != str(_uuid(tenant_id)):
        raise ComplianceValidationError({"owner_id": ["Owner must belong to the request tenant."]})


def _clean_snapshot(value: object) -> object:
    """Produce bounded audit JSON without content, credentials, or PII."""
    if not isinstance(value, Mapping):
        return value
    redacted = {"content", "description", "external_uri", "text_reference", "token", "secret", "password"}
    result: dict[str, object] = {}
    for key, item in value.items():
        if key.lower() in redacted:
            result[key] = "[REDACTED]"
        elif isinstance(item, (UUID, date, datetime)):
            result[key] = item.isoformat() if hasattr(item, "isoformat") else str(item)
        elif getattr(item, "pk", None) is not None:
            result[f"{key}_id"] = str(item.pk)
        elif isinstance(item, Mapping):
            result[key] = _clean_snapshot(item)
        elif isinstance(item, (str, int, float, bool, list, tuple, type(None))):
            result[key] = item
    return result


def _state(instance: object) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in instance._meta.concrete_fields:  # type: ignore[attr-defined]
        values[field.name] = getattr(instance, field.name)
    return _clean_snapshot(values)  # type: ignore[return-value]


def _get(model: type, tenant_id: UUID | str, object_id: UUID | str, *, include_deleted: bool = False):
    tenant = _uuid(tenant_id, "tenant_id")
    queryset = model.objects.for_tenant(tenant)
    if hasattr(model, "deleted_at") and not include_deleted:
        queryset = queryset.filter(deleted_at__isnull=True)
    try:
        return queryset.get(pk=_uuid(object_id))
    except model.DoesNotExist as exc:
        raise ComplianceNotFound(f"{model.__name__} was not found.") from exc


def _transition(instance: object, command: str, key: str, allowed: Mapping[str, str]) -> bool:
    if not key or len(key) > 255:
        raise ComplianceValidationError({"transition_key": ["A bounded transition key is required."]})
    history = list(getattr(instance, "transition_history", []))
    for item in history:
        if item.get("key") == key:
            if item.get("command") != command:
                raise ComplianceConflict("Transition key was already used for a different command.")
            return False
    current = getattr(instance, "status")
    target = allowed.get(current)
    if target is None:
        raise ComplianceConflict(f"Cannot {command} from {current}.")
    history.append({
        "key": key,
        "command": command,
        "from": current,
        "to": target,
        "occurred_at": timezone.now().isoformat(),
    })
    instance.status = target
    instance.transition_history = history
    return True


class ActivityService:
    @staticmethod
    def record(
        tenant_id: UUID | str,
        actor: object | None,
        entity: object,
        action: str,
        before: Mapping[str, object],
        after: Mapping[str, object],
        reason: str,
        correlation_id: UUID | str,
    ) -> ComplianceActivity:
        entity_type = getattr(entity, "activity_type", entity.__class__.__name__.lower().replace("compliance", ""))
        entity_type = {
            "policyversion": "policy_version",
            "configurationrevision": "configuration",
            "evidencerequirementlink": "evidence_link",
            "requirementpolicymapping": "mapping",
        }.get(entity_type, entity_type)
        if entity_type not in ENTITY_TYPES:
            raise ComplianceValidationError({"entity_type": ["Unsupported audit entity."]})
        record = ComplianceActivity(
            tenant_id=_uuid(tenant_id, "tenant_id"),
            entity_type=entity_type,
            entity_id=entity.pk,
            action=action[:100],
            actor=_actor(actor),
            correlation_id=_uuid(correlation_id, "correlation_id"),
            before=_clean_snapshot(before),
            after=_clean_snapshot(after),
            reason=reason,
        )
        _validate_model(record)
        record.save(force_insert=True)
        return record

    @staticmethod
    def list_activity(tenant_id: UUID | str, filters: Mapping[str, object] | None = None, ordering: str = "-occurred_at"):
        qs = ComplianceActivity.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
        filters = filters or {}
        for key in ("entity_type", "entity_id", "actor_id", "action", "correlation_id"):
            if filters.get(key) not in (None, ""):
                qs = qs.filter(**{key: filters[key]})
        if filters.get("occurred_after"):
            qs = qs.filter(occurred_at__gte=filters["occurred_after"])
        if filters.get("occurred_before"):
            qs = qs.filter(occurred_at__lte=filters["occurred_before"])
        return qs.order_by(_ordering(ordering, "activity", "-occurred_at"))


class ConfigurationService:
    ENVIRONMENTS = {"development", "staging", "production"}

    @classmethod
    def _environment(cls, environment: str) -> str:
        if environment not in cls.ENVIRONMENTS:
            raise ComplianceValidationError({"environment": ["Unsupported environment."]})
        return environment

    @staticmethod
    def _defaults() -> dict[str, object]:
        return {
            "policy_code_prefix": "POL",
            "default_review_frequency_days": 365,
            "expiry_warning_days": 30,
            "evidence_warning_days": 30,
            "minimum_assessment_note_length": 10,
            "allow_external_evidence_urls": False,
            "bulk_import_row_limit": 1000,
            "regulation_categories": ["General", "GDPR", "SOX", "HIPAA", "ISO 27001"],
            "rollout": {"frameworks": {"enabled": True, "roles": [], "cohorts": []}},
        }

    @classmethod
    def list_revisions(cls, tenant_id: UUID | str, environment: str):
        return ComplianceConfigurationRevision.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(
            environment=cls._environment(environment)
        ).order_by("-version")

    @classmethod
    def get_effective(cls, tenant_id: UUID | str, environment: str):
        tenant = _uuid(tenant_id, "tenant_id")
        environment = cls._environment(environment)
        revision = ComplianceConfigurationRevision.objects.for_tenant(tenant).filter(
            environment=environment, status="active"
        ).first()
        if revision is None:
            raise ComplianceDependencyUnavailable("Compliance configuration has not been activated.")
        return revision

    @classmethod
    @transaction.atomic
    def create_revision(cls, tenant_id, actor, environment: str, data: Mapping[str, object], correlation_id):
        tenant = _uuid(tenant_id, "tenant_id")
        environment = cls._environment(environment)
        latest = ComplianceConfigurationRevision.objects.select_for_update().for_tenant(tenant).filter(
            environment=environment
        ).order_by("-version").first()
        values = cls._defaults()
        if latest:
            for key in values:
                values[key] = getattr(latest, key)
        values.update(dict(data))
        revision = ComplianceConfigurationRevision(
            tenant_id=tenant, environment=environment, version=(latest.version + 1 if latest else 1),
            status="draft", created_by=_actor(actor), **values,
        )
        _validate_model(revision)
        revision.save(force_insert=True)
        ActivityService.record(tenant, actor, revision, "configuration.created", {}, _state(revision), "", correlation_id)
        return revision

    @classmethod
    @transaction.atomic
    def update_draft(cls, tenant_id, actor, revision_id, data: Mapping[str, object], correlation_id):
        revision = _get(ComplianceConfigurationRevision, tenant_id, revision_id, include_deleted=True)
        revision = ComplianceConfigurationRevision.objects.select_for_update().get(pk=revision.pk)
        if revision.status != "draft":
            raise ComplianceConflict("Only draft configuration revisions can be edited.")
        before = _state(revision)
        blocked = {"tenant_id", "id", "version", "status", "created_by", "created_at", "activated_by", "activated_at"}
        if set(data) & blocked:
            raise ComplianceValidationError({key: ["Field is read-only."] for key in sorted(set(data) & blocked)})
        for key, value in data.items():
            if not hasattr(revision, key):
                raise ComplianceValidationError({key: ["Unknown field."]})
            setattr(revision, key, value)
        _validate_model(revision)
        revision.save()
        ActivityService.record(tenant_id, actor, revision, "configuration.updated", before, _state(revision), "", correlation_id)
        return revision

    @classmethod
    def preview(cls, tenant_id, revision_id):
        revision = _get(ComplianceConfigurationRevision, tenant_id, revision_id, include_deleted=True)
        active = ComplianceConfigurationRevision.objects.for_tenant(_uuid(tenant_id)).filter(
            environment=revision.environment, status="active"
        ).first()
        fields = tuple(cls._defaults())
        diff = [
            {"field": key, "before": getattr(active, key, None), "after": getattr(revision, key)}
            for key in fields if active is None or getattr(active, key) != getattr(revision, key)
        ]
        return {
            "revision_id": revision.id,
            "environment": revision.environment,
            "diff": diff,
            "affected": {
                "frameworks": ComplianceFramework.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).count(),
                "policies": CompliancePolicy.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).count(),
                "evidence": ComplianceEvidence.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).count(),
            },
        }

    @classmethod
    @transaction.atomic
    def activate(cls, tenant_id, actor, revision_id, transition_key: str, correlation_id):
        tenant = _uuid(tenant_id)
        revision = _get(ComplianceConfigurationRevision, tenant, revision_id, include_deleted=True)
        revision = ComplianceConfigurationRevision.objects.select_for_update().get(pk=revision.pk)
        if revision.status == "active":
            if any(item.get("key") == transition_key and item.get("command") == "activate" for item in revision.transition_history):
                return revision
            raise ComplianceConflict("Configuration is already active.")
        if revision.status != "draft":
            raise ComplianceConflict("Only a draft revision can be activated.")
        before = _state(revision)
        ComplianceConfigurationRevision.objects.for_tenant(tenant).filter(
            environment=revision.environment, status="active"
        ).update(status="superseded")
        revision.status = "active"
        revision.activated_by = _actor(actor)
        revision.activated_at = timezone.now()
        revision.transition_history = list(revision.transition_history) + [{
            "key": transition_key, "command": "activate", "from": "draft", "to": "active",
            "occurred_at": timezone.now().isoformat(),
        }]
        _validate_model(revision)
        revision.save()
        ActivityService.record(tenant, actor, revision, "configuration.activated", before, _state(revision), "", correlation_id)
        return revision

    @classmethod
    @transaction.atomic
    def rollback(cls, tenant_id, actor, revision_id, transition_key: str, correlation_id):
        source = _get(ComplianceConfigurationRevision, tenant_id, revision_id, include_deleted=True)
        data = {key: getattr(source, key) for key in cls._defaults()}
        revision = cls.create_revision(tenant_id, actor, source.environment, data, correlation_id)
        revision = cls.activate(tenant_id, actor, revision.id, transition_key, correlation_id)
        ActivityService.record(tenant_id, actor, revision, "configuration.rolled_back", {"source": str(source.id)}, _state(revision), "", correlation_id)
        return revision

    @classmethod
    def export_revision(cls, tenant_id, revision_id):
        revision = _get(ComplianceConfigurationRevision, tenant_id, revision_id, include_deleted=True)
        return {
            "schema": "saraise.compliance.configuration/v1",
            "environment": revision.environment,
            "configuration": {key: getattr(revision, key) for key in cls._defaults()},
        }

    @classmethod
    def import_revision(cls, tenant_id, actor, document: Mapping[str, object], correlation_id):
        if document.get("schema") != "saraise.compliance.configuration/v1":
            raise ComplianceValidationError({"schema": ["Unsupported configuration schema."]})
        config = document.get("configuration")
        if not isinstance(config, Mapping):
            raise ComplianceValidationError({"configuration": ["Must be an object."]})
        return cls.create_revision(tenant_id, actor, str(document.get("environment", "")), config, correlation_id)


class FrameworkService:
    @staticmethod
    def list_frameworks(tenant_id, filters=None, ordering="name"):
        qs = ComplianceFramework.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True)
        filters = filters or {}
        for key in ("status", "category", "source_kind"):
            if filters.get(key): qs = qs.filter(**{key: filters[key]})
        if filters.get("search"):
            qs = qs.filter(Q(name__icontains=filters["search"]) | Q(code__icontains=filters["search"]) | Q(description__icontains=filters["search"]))
        return qs.order_by(_ordering(ordering, "framework", "name"))

    @staticmethod
    def get_framework(tenant_id, framework_id): return _get(ComplianceFramework, tenant_id, framework_id)

    @staticmethod
    @transaction.atomic
    def create_framework(tenant_id, actor, data, correlation_id):
        tenant = _uuid(tenant_id)
        values = _only(data, {"code", "name", "version", "category", "description", "source_kind", "source_package", "source_version"})
        _validate_category(tenant, values.get("category"))
        framework = ComplianceFramework(tenant_id=tenant, created_by=_actor(actor), updated_by=_actor(actor), **values)
        _validate_model(framework); framework.save(force_insert=True)
        ActivityService.record(tenant, actor, framework, "framework.created", {}, _state(framework), "", correlation_id)
        return framework

    @classmethod
    @transaction.atomic
    def update_framework(cls, tenant_id, actor, framework_id, data, correlation_id):
        framework = cls.get_framework(tenant_id, framework_id)
        before = _state(framework)
        if framework.status == "archived": raise ComplianceConflict("Archived frameworks are immutable.")
        values = _only(data, {"code", "name", "version", "category", "description", "source_kind", "source_package", "source_version"})
        if "category" in values: _validate_category(tenant_id, values["category"])
        for key, value in values.items(): setattr(framework, key, value)
        framework.updated_by = _actor(actor); _validate_model(framework); framework.save()
        ActivityService.record(tenant_id, actor, framework, "framework.updated", before, _state(framework), "", correlation_id)
        return framework

    @classmethod
    @transaction.atomic
    def activate_framework(cls, tenant_id, actor, framework_id, transition_key, correlation_id):
        framework = ComplianceFramework.objects.select_for_update().get(pk=cls.get_framework(tenant_id, framework_id).pk)
        before = _state(framework)
        if _transition(framework, "activate", transition_key, {"draft": "active"}):
            framework.updated_by = _actor(actor); _validate_model(framework); framework.save()
            ActivityService.record(tenant_id, actor, framework, "framework.activated", before, _state(framework), "", correlation_id)
        return framework

    @classmethod
    @transaction.atomic
    def archive_framework(cls, tenant_id, actor, framework_id, transition_key, correlation_id):
        framework = ComplianceFramework.objects.select_for_update().get(pk=cls.get_framework(tenant_id, framework_id).pk)
        before = _state(framework)
        if _transition(framework, "archive", transition_key, {"active": "archived"}):
            framework.updated_by = _actor(actor); framework.deleted_at = timezone.now(); framework.deleted_by = _actor(actor)
            framework.save(); ActivityService.record(tenant_id, actor, framework, "framework.archived", before, _state(framework), "", correlation_id)
        return framework

    @staticmethod
    def validate_import(tenant_id, package):
        if not isinstance(package, Mapping) or package.get("schema") != "saraise.compliance.framework/v1":
            raise ComplianceValidationError({"package": ["Unsupported framework package schema."]})
        framework = package.get("framework"); requirements = package.get("requirements", [])
        if not isinstance(framework, Mapping) or not isinstance(requirements, list):
            raise ComplianceValidationError({"package": ["Framework and requirements are required."]})
        row_limit = int(_effective_or_defaults(tenant_id)["bulk_import_row_limit"])
        if len(requirements) > row_limit:
            raise ComplianceValidationError({"requirements": [f"Package exceeds the configured {row_limit}-row limit."]})
        codes: set[str] = set()
        for index, row in enumerate(requirements):
            if not isinstance(row, Mapping) or not str(row.get("code", "")).strip():
                raise ComplianceValidationError({f"requirements.{index}.code": ["A code is required."]})
            code = str(row["code"]).strip()
            if code in codes: raise ComplianceValidationError({f"requirements.{index}.code": ["Duplicate code."]})
            codes.add(code)
            if SAFE_MARKUP.search(str(row.get("description", ""))):
                raise ComplianceValidationError({f"requirements.{index}.description": ["Unsafe markup is not allowed."]})
        return {"valid": True, "requirement_count": len(requirements), "framework": dict(framework), "requirements": requirements}

    @classmethod
    @transaction.atomic
    def import_framework(cls, tenant_id, actor, package, idempotency_key, correlation_id):
        validated = cls.validate_import(tenant_id, package)
        prior = ComplianceActivity.objects.for_tenant(_uuid(tenant_id)).filter(action="framework.imported", after__idempotency_key=idempotency_key).first()
        if prior: return cls.get_framework(tenant_id, prior.entity_id)
        framework = cls.create_framework(tenant_id, actor, validated["framework"], correlation_id)
        for row in validated["requirements"]:
            RequirementService.create_requirement(tenant_id, actor, {**dict(row), "framework_id": framework.id}, correlation_id)
        ActivityService.record(tenant_id, actor, framework, "framework.imported", {}, {"idempotency_key": idempotency_key, "requirements": len(validated["requirements"])}, "", correlation_id)
        return framework

    @classmethod
    def export_framework(cls, tenant_id, framework_id):
        framework = cls.get_framework(tenant_id, framework_id)
        fields = ("code", "name", "version", "category", "description", "source_kind", "source_package", "source_version")
        req_fields = ("code", "title", "description", "section", "guidance", "applicability", "applicability_rationale", "sort_order", "tags")
        return {"schema": "saraise.compliance.framework/v1", "framework": {k: getattr(framework, k) for k in fields}, "requirements": [{k: getattr(r, k) for k in req_fields} for r in framework.requirements.filter(deleted_at__isnull=True).order_by("sort_order", "code")]}


class RequirementService:
    @staticmethod
    def list_requirements(tenant_id, filters=None, ordering="sort_order"):
        qs = ComplianceRequirement.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).select_related("framework")
        filters = filters or {}
        for key in ("status", "applicability"):
            if filters.get(key): qs = qs.filter(**{key: filters[key]})
        if filters.get("framework_id"): qs = qs.filter(framework_id=_uuid(filters["framework_id"], "framework_id"))
        if filters.get("search"): qs = qs.filter(Q(code__icontains=filters["search"]) | Q(title__icontains=filters["search"]) | Q(description__icontains=filters["search"]))
        return qs.order_by(_ordering(ordering, "requirement", "sort_order"), "code")

    @staticmethod
    def get_requirement(tenant_id, requirement_id): return _get(ComplianceRequirement, tenant_id, requirement_id)

    @staticmethod
    @transaction.atomic
    def create_requirement(tenant_id, actor, data, correlation_id):
        values = _only(data, {"framework_id", "framework", "code", "title", "description", "section", "guidance", "applicability", "applicability_rationale", "sort_order", "tags"}); framework_id = values.pop("framework_id", values.pop("framework", None))
        framework = _get(ComplianceFramework, tenant_id, framework_id)
        requirement = ComplianceRequirement(tenant_id=_uuid(tenant_id), framework=framework, created_by=_actor(actor), updated_by=_actor(actor), **values)
        _validate_model(requirement); requirement.save(force_insert=True)
        ActivityService.record(tenant_id, actor, requirement, "requirement.created", {}, _state(requirement), "", correlation_id)
        return requirement

    @classmethod
    @transaction.atomic
    def update_requirement(cls, tenant_id, actor, requirement_id, data, correlation_id):
        requirement = cls.get_requirement(tenant_id, requirement_id); before = _state(requirement)
        values = _only(data, {"framework_id", "code", "title", "description", "section", "guidance", "applicability", "applicability_rationale", "sort_order", "tags"})
        if "framework_id" in values:
            requirement.framework = _get(ComplianceFramework, tenant_id, values.pop("framework_id"))
        for key, value in values.items(): setattr(requirement, key, value)
        requirement.updated_by = _actor(actor); _validate_model(requirement); requirement.save()
        ActivityService.record(tenant_id, actor, requirement, "requirement.updated", before, _state(requirement), "", correlation_id)
        return requirement

    @classmethod
    @transaction.atomic
    def _change(cls, tenant_id, actor, requirement_id, command, transition_key, correlation_id):
        source = (_get(ComplianceRequirement, tenant_id, requirement_id, include_deleted=True)
                  if command == "restore" else cls.get_requirement(tenant_id, requirement_id))
        requirement = ComplianceRequirement.objects.select_for_update().get(pk=source.pk); before = _state(requirement)
        allowed = {"active": "archived"} if command == "archive" else {"archived": "active"}
        if _transition(requirement, command, transition_key, allowed):
            requirement.updated_by = _actor(actor)
            requirement.deleted_at = timezone.now() if command == "archive" else None
            requirement.deleted_by = _actor(actor) if command == "archive" else None
            requirement.save(); ActivityService.record(tenant_id, actor, requirement, f"requirement.{command}d", before, _state(requirement), "", correlation_id)
        return requirement

    archive_requirement = classmethod(lambda cls, tenant_id, actor, requirement_id, transition_key, correlation_id: cls._change(tenant_id, actor, requirement_id, "archive", transition_key, correlation_id))
    restore_requirement = classmethod(lambda cls, tenant_id, actor, requirement_id, transition_key, correlation_id: cls._change(tenant_id, actor, requirement_id, "restore", transition_key, correlation_id))

    @classmethod
    @transaction.atomic
    def bulk_import(cls, tenant_id, actor, framework_id, rows, idempotency_key, correlation_id):
        framework = _get(ComplianceFramework, tenant_id, framework_id)
        config = _effective_or_defaults(tenant_id)
        if not isinstance(rows, list) or len(rows) > config["bulk_import_row_limit"]:
            raise ComplianceValidationError({"rows": ["Import row limit exceeded or invalid rows."]})
        codes = [str(row.get("code", "")).strip() for row in rows if isinstance(row, Mapping)]
        if len(codes) != len(rows) or any(not code for code in codes) or len(set(codes)) != len(codes):
            raise ComplianceValidationError({"rows": ["Every row needs a unique code."]})
        created = [cls.create_requirement(tenant_id, actor, {**dict(row), "framework_id": framework.id}, correlation_id) for row in rows]
        ActivityService.record(tenant_id, actor, framework, "requirements.imported", {}, {"idempotency_key": idempotency_key, "count": len(created)}, "", correlation_id)
        return created


def _effective_or_defaults(tenant_id, environment="development") -> dict[str, Any]:
    try:
        revision = ConfigurationService.get_effective(tenant_id, environment)
        return {key: getattr(revision, key) for key in ConfigurationService._defaults()}
    except ComplianceDependencyUnavailable:
        return ConfigurationService._defaults()


class PolicyService:
    @staticmethod
    def list_policies(tenant_id, filters=None, ordering="code"):
        qs = CompliancePolicy.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).select_related("owner")
        filters = filters or {}
        for key in ("status", "category", "owner_id"):
            if filters.get(key): qs = qs.filter(**{key: filters[key]})
        if filters.get("review_before"): qs = qs.filter(next_review_date__lte=filters["review_before"])
        if filters.get("expiry_before"): qs = qs.filter(expiry_date__lte=filters["expiry_before"])
        if filters.get("search"): qs = qs.filter(Q(code__icontains=filters["search"]) | Q(title__icontains=filters["search"]) | Q(summary__icontains=filters["search"]))
        return qs.order_by(_ordering(ordering, "policy", "code"))

    @staticmethod
    def get_policy(tenant_id, policy_id): return _get(CompliancePolicy, tenant_id, policy_id)

    @staticmethod
    @transaction.atomic
    def create_policy(tenant_id, actor, data=None, correlation_id=None, **legacy):
        values = dict(data or {}); values.update(legacy)
        values["code"] = values.pop("policy_code", values.get("code", ""))
        values["title"] = values.pop("policy_name", values.get("title", ""))
        values["category"] = values.pop("regulation_type", values.get("category", "General"))
        values["summary"] = values.pop("description", values.get("summary", ""))
        values.pop("is_active", None)
        values = _only(values, {"code", "title", "summary", "category", "owner_id", "owner", "review_frequency_days", "effective_date", "expiry_date", "next_review_date"})
        _validate_category(tenant_id, values.get("category"))
        if "owner_id" in values:
            owner_id = values.pop("owner_id")
            values["owner"] = get_user_model().objects.filter(pk=owner_id).first()
            if values["owner"] is None: raise ComplianceValidationError({"owner_id": ["Owner was not found."]})
        _validate_owner(tenant_id, values.get("owner"))
        if not values.get("review_frequency_days"):
            values["review_frequency_days"] = _effective_or_defaults(tenant_id)["default_review_frequency_days"]
        policy = CompliancePolicy(tenant_id=_uuid(tenant_id), created_by=_actor(actor), updated_by=_actor(actor), **values)
        _validate_model(policy); policy.save(force_insert=True)
        ActivityService.record(tenant_id, actor, policy, "policy.created", {}, _state(policy), "", correlation_id or uuid4())
        return policy

    @classmethod
    @transaction.atomic
    def update_policy(cls, tenant_id, actor, policy_id, data, correlation_id):
        policy = cls.get_policy(tenant_id, policy_id); before = _state(policy)
        if policy.status in {"approved", "published", "archived"}: raise ComplianceConflict("Policy metadata is locked in this lifecycle state.")
        values = _only(data, {"code", "title", "summary", "category", "owner_id", "review_frequency_days", "effective_date", "expiry_date"})
        if "category" in values: _validate_category(tenant_id, values["category"])
        if "owner_id" in values:
            owner_id = values.pop("owner_id"); values["owner"] = get_user_model().objects.filter(pk=owner_id).first()
            if values["owner"] is None: raise ComplianceValidationError({"owner_id": ["Owner was not found."]})
            _validate_owner(tenant_id, values["owner"])
        for key, value in values.items(): setattr(policy, key, value)
        policy.updated_by = _actor(actor); _validate_model(policy); policy.save()
        ActivityService.record(tenant_id, actor, policy, "policy.updated", before, _state(policy), "", correlation_id)
        return policy

    @classmethod
    @transaction.atomic
    def create_version(cls, tenant_id, actor, policy_id, content, change_summary, idempotency_key, correlation_id):
        policy = CompliancePolicy.objects.select_for_update().get(pk=cls.get_policy(tenant_id, policy_id).pk)
        if policy.status != "draft": raise ComplianceConflict("Versions can only be created while a policy is draft.")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = CompliancePolicyVersion.objects.for_tenant(_uuid(tenant_id)).filter(policy=policy, content_sha256=digest).first()
        if existing:
            activity = ComplianceActivity.objects.for_tenant(_uuid(tenant_id)).filter(entity_id=existing.id, action="policy.version_created", after__idempotency_key=idempotency_key).first()
            if activity: return existing
            raise ComplianceConflict("This exact policy content already exists under a different command.")
        version = CompliancePolicyVersion(tenant_id=_uuid(tenant_id), policy=policy, version=policy.current_version + 1, content=content, content_sha256=digest, change_summary=change_summary, created_by=_actor(actor))
        _validate_model(version); version.save(force_insert=True)
        policy.current_version = version.version; policy.updated_by = _actor(actor); policy.save(update_fields=["current_version", "updated_by", "updated_at"])
        ActivityService.record(tenant_id, actor, version, "policy.version_created", {}, {"version": version.version, "content_sha256": digest, "idempotency_key": idempotency_key}, change_summary, correlation_id)
        return version

    @classmethod
    @transaction.atomic
    def _transition_policy(cls, tenant_id, actor, policy_id, command, transition_key, correlation_id, reason=""):
        policy = CompliancePolicy.objects.select_for_update().get(pk=cls.get_policy(tenant_id, policy_id).pk); before = _state(policy)
        transitions = {
            "submit": {"draft": "in_review"}, "request_changes": {"in_review": "draft"},
            "approve": {"in_review": "approved"}, "publish": {"approved": "published"},
            "archive": {"draft": "archived", "approved": "archived", "published": "archived"},
        }
        if command in {"submit", "approve", "publish"} and policy.current_version < 1:
            raise ComplianceConflict("A current immutable version is required.")
        if command == "publish":
            if not policy.owner_id or not policy.effective_date:
                raise ComplianceValidationError({"non_field_errors": ["Owner and effective date are required for publication."]})
            _validate_owner(tenant_id, policy.owner)
            if policy.expiry_date and policy.expiry_date <= policy.effective_date:
                raise ComplianceValidationError({"expiry_date": ["Must be later than effective date."]})
            policy.next_review_date = policy.effective_date + timedelta(days=policy.review_frequency_days)
        if _transition(policy, command, transition_key, transitions[command]):
            policy.updated_by = _actor(actor)
            if command == "archive": policy.deleted_at = timezone.now(); policy.deleted_by = _actor(actor)
            _validate_model(policy); policy.save()
            ActivityService.record(tenant_id, actor, policy, f"policy.{command}", before, _state(policy), reason, correlation_id)
        return policy

    submit = classmethod(lambda cls, tenant_id, actor, policy_id, transition_key, correlation_id: cls._transition_policy(tenant_id, actor, policy_id, "submit", transition_key, correlation_id))
    request_changes = classmethod(lambda cls, tenant_id, actor, policy_id, reason, transition_key, correlation_id: cls._transition_policy(tenant_id, actor, policy_id, "request_changes", transition_key, correlation_id, reason))
    approve = classmethod(lambda cls, tenant_id, actor, policy_id, transition_key, correlation_id: cls._transition_policy(tenant_id, actor, policy_id, "approve", transition_key, correlation_id))
    publish = classmethod(lambda cls, tenant_id, actor, policy_id, transition_key, correlation_id: cls._transition_policy(tenant_id, actor, policy_id, "publish", transition_key, correlation_id))
    archive = classmethod(lambda cls, tenant_id, actor, policy_id, transition_key, correlation_id: cls._transition_policy(tenant_id, actor, policy_id, "archive", transition_key, correlation_id))

    @classmethod
    @transaction.atomic
    def revise(cls, tenant_id, actor, policy_id, content, change_summary, transition_key, correlation_id):
        policy = cls.get_policy(tenant_id, policy_id)
        if policy.status != "published": raise ComplianceConflict("Only a published policy can be revised.")
        # State becomes draft before creating content because version creation is draft-only.
        before = _state(policy); _transition(policy, "revise", transition_key, {"published": "draft"}); policy.save()
        version = cls.create_version(tenant_id, actor, policy.id, content, change_summary, transition_key, correlation_id)
        ActivityService.record(tenant_id, actor, policy, "policy.revise", before, _state(policy), change_summary, correlation_id)
        return policy, version


class MappingService:
    @staticmethod
    def list_mappings(tenant_id, filters=None, ordering="mapped_at"):
        qs = RequirementPolicyMapping.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True).select_related("requirement", "policy", "policy_version")
        filters = filters or {}
        for key in ("requirement_id", "policy_id", "coverage"):
            if filters.get(key): qs = qs.filter(**{key: filters[key]})
        if filters.get("framework_id"): qs = qs.filter(requirement__framework_id=filters["framework_id"])
        return qs.order_by(_ordering(ordering, "mapping", "mapped_at"))

    @staticmethod
    @transaction.atomic
    def set_mapping(tenant_id, actor, requirement_id, policy_id, data, idempotency_key, correlation_id):
        requirement = _get(ComplianceRequirement, tenant_id, requirement_id); policy = _get(CompliancePolicy, tenant_id, policy_id)
        values = dict(data); version_id = values.pop("policy_version_id", None)
        version = _get(CompliancePolicyVersion, tenant_id, version_id, include_deleted=True) if version_id else None
        if version and version.policy_id != policy.id: raise ComplianceValidationError({"policy_version_id": ["Version does not belong to policy."]})
        mapping = RequirementPolicyMapping.objects.for_tenant(_uuid(tenant_id)).filter(requirement=requirement, policy=policy, deleted_at__isnull=True).first()
        before = _state(mapping) if mapping else {}
        if mapping is None: mapping = RequirementPolicyMapping(tenant_id=_uuid(tenant_id), requirement=requirement, policy=policy, created_by=_actor(actor))
        mapping.policy_version = version; mapping.updated_by = _actor(actor); mapping.mapped_at = timezone.now()
        for key, value in values.items(): setattr(mapping, key, value)
        _validate_model(mapping); mapping.save()
        ActivityService.record(tenant_id, actor, mapping, "mapping.set", before, {**_state(mapping), "idempotency_key": idempotency_key}, "", correlation_id)
        return mapping

    @staticmethod
    @transaction.atomic
    def remove_mapping(tenant_id, actor, mapping_id, correlation_id):
        mapping = _get(RequirementPolicyMapping, tenant_id, mapping_id); before = _state(mapping)
        mapping.deleted_at = timezone.now(); mapping.deleted_by = _actor(actor); mapping.updated_by = _actor(actor); mapping.save()
        ActivityService.record(tenant_id, actor, mapping, "mapping.removed", before, _state(mapping), "", correlation_id)

    @classmethod
    @transaction.atomic
    def bulk_set_mappings(cls, tenant_id, actor, rows, idempotency_key, correlation_id):
        if not isinstance(rows, list): raise ComplianceValidationError({"rows": ["Must be a list."]})
        return [cls.set_mapping(tenant_id, actor, row["requirement_id"], row["policy_id"], row, f"{idempotency_key}:{index}", correlation_id) for index, row in enumerate(rows)]

    @staticmethod
    def gap_analysis(tenant_id, framework_id, as_of=None):
        del as_of
        requirements = ComplianceRequirement.objects.for_tenant(_uuid(tenant_id)).filter(framework_id=_uuid(framework_id, "framework_id"), applicability="applicable", status="active", deleted_at__isnull=True)
        rows = []
        for req in requirements:
            mappings = req.policy_mappings.filter(tenant_id=_uuid(tenant_id), deleted_at__isnull=True)
            best = "full" if mappings.filter(coverage="full").exists() else "partial" if mappings.filter(coverage="partial").exists() else "none"
            if best != "full": rows.append({"requirement_id": req.id, "code": req.code, "title": req.title, "coverage": best, "reason": "No full policy coverage"})
        return {"framework_id": _uuid(framework_id), "total": requirements.count(), "gap_count": len(rows), "gaps": rows}


class AssessmentService:
    @staticmethod
    def list_assessments(tenant_id, filters=None, ordering="-assessed_at"):
        qs = ComplianceAssessment.objects.for_tenant(_uuid(tenant_id)).select_related("requirement", "mapping", "assessor")
        filters = filters or {}
        for key in ("requirement_id", "status"):
            if filters.get(key): qs = qs.filter(**{key: filters[key]})
        if filters.get("framework_id"): qs = qs.filter(requirement__framework_id=filters["framework_id"])
        if filters.get("due_after"): qs = qs.filter(due_date__gte=filters["due_after"])
        if filters.get("due_before"): qs = qs.filter(due_date__lte=filters["due_before"])
        return qs.order_by(_ordering(ordering, "assessment", "-assessed_at"), "-created_at", "-id")

    @staticmethod
    def get_assessment(tenant_id, assessment_id): return _get(ComplianceAssessment, tenant_id, assessment_id, include_deleted=True)

    @staticmethod
    @transaction.atomic
    def record_assessment(tenant_id, actor, data, idempotency_key, correlation_id):
        prior = ComplianceActivity.objects.for_tenant(_uuid(tenant_id)).filter(action="assessment.recorded", after__idempotency_key=idempotency_key).first()
        if prior: return _get(ComplianceAssessment, tenant_id, prior.entity_id, include_deleted=True)
        values = dict(data); requirement = _get(ComplianceRequirement, tenant_id, values.pop("requirement_id")); mapping_id = values.pop("mapping_id", None)
        mapping = _get(RequirementPolicyMapping, tenant_id, mapping_id) if mapping_id else None
        if mapping and mapping.requirement_id != requirement.id: raise ComplianceValidationError({"mapping_id": ["Mapping belongs to another requirement."]})
        assessment = ComplianceAssessment(tenant_id=_uuid(tenant_id), requirement=requirement, mapping=mapping, assessor=_actor(actor), assessed_at=values.pop("assessed_at", timezone.now()), **values)
        min_length = int(_effective_or_defaults(tenant_id)["minimum_assessment_note_length"])
        if assessment.status in {"partial", "non_compliant", "not_applicable"} and len(assessment.notes.strip()) < min_length:
            raise ComplianceValidationError({"notes": [f"Must be at least {min_length} characters for this status."]})
        _validate_model(assessment); assessment.save(force_insert=True)
        ActivityService.record(tenant_id, actor, assessment, "assessment.recorded", {}, {**_state(assessment), "idempotency_key": idempotency_key}, "", correlation_id)
        return assessment

    @classmethod
    def current_for_requirement(cls, tenant_id, requirement_id):
        requirement = _get(ComplianceRequirement, tenant_id, requirement_id)
        return cls.list_assessments(tenant_id, {"requirement_id": requirement.id}).first()

    @classmethod
    def history_for_requirement(cls, tenant_id, requirement_id):
        _get(ComplianceRequirement, tenant_id, requirement_id)
        return cls.list_assessments(tenant_id, {"requirement_id": requirement_id})

    @classmethod
    def list_overdue(cls, tenant_id, as_of):
        return cls.list_assessments(tenant_id).filter(due_date__lt=as_of).exclude(status__in=("compliant", "not_applicable"))

    @classmethod
    def scorecard(cls, tenant_id, framework_id, as_of=None):
        as_of = as_of or timezone.now()
        requirements = list(ComplianceRequirement.objects.for_tenant(_uuid(tenant_id)).filter(framework_id=_uuid(framework_id), applicability="applicable", status="active", deleted_at__isnull=True))
        points = 0.0; rows = []
        for req in requirements:
            assessment = cls.list_assessments(tenant_id, {"requirement_id": req.id})
            if isinstance(as_of, date) and not isinstance(as_of, datetime): assessment = assessment.filter(assessed_at__date__lte=as_of)
            else: assessment = assessment.filter(assessed_at__lte=as_of)
            current = assessment.first(); score = 1.0 if current and current.status == "compliant" else 0.5 if current and current.status == "partial" else 0.0
            points += score; rows.append({"requirement_id": req.id, "code": req.code, "status": current.status if current else "not_assessed", "points": score})
        denominator = len(requirements)
        return {"framework_id": _uuid(framework_id), "score": round((points / denominator) * 100, 2) if denominator else 0.0, "earned_points": points, "possible_points": denominator, "formula": "applicable requirements: compliant=1, partial=0.5, all others including unassessed=0", "requirements": rows}


class EvidenceService:
    dms_validator: DmsReferenceValidator | None = None

    @staticmethod
    def list_evidence(tenant_id, filters=None, ordering="-collected_at"):
        qs = ComplianceEvidence.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True)
        filters = filters or {}
        mapping = {"type": "evidence_type", "classification": "classification"}
        for incoming, field in mapping.items():
            if filters.get(incoming): qs = qs.filter(**{field: filters[incoming]})
        if filters.get("requirement_id"): qs = qs.filter(requirement_links__requirement_id=filters["requirement_id"])
        if filters.get("valid_before"): qs = qs.filter(valid_until__lte=filters["valid_before"])
        if filters.get("search"): qs = qs.filter(Q(name__icontains=filters["search"]) | Q(description__icontains=filters["search"]))
        return qs.distinct().order_by(_ordering(ordering, "evidence", "-collected_at"))

    @staticmethod
    def get_evidence(tenant_id, evidence_id): return _get(ComplianceEvidence, tenant_id, evidence_id)

    @classmethod
    @transaction.atomic
    def register_evidence(cls, tenant_id, actor, data, correlation_id):
        values = _only(data, {"name", "description", "evidence_type", "reference_kind", "document_id", "external_uri", "text_reference", "sha256", "classification", "collection_method", "valid_from", "valid_until", "collected_by", "collected_at"})
        if values.get("reference_kind") == "external_url" and not _effective_or_defaults(tenant_id)["allow_external_evidence_urls"]:
            raise ComplianceValidationError({"external_uri": ["External evidence URLs are disabled by active configuration."]})
        if values.get("reference_kind") == "external_url":
            parsed = urlsplit(str(values.get("external_uri", "")))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
                raise ComplianceValidationError({"external_uri": ["URL must be public HTTP(S) without embedded credentials."]})
        if values.get("reference_kind") == "dms_document":
            if cls.dms_validator is None: raise ComplianceDependencyUnavailable("DMS reference validation is unavailable.")
            cls.dms_validator.validate_document_reference(_uuid(tenant_id), _uuid(values.get("document_id"), "document_id"))
        evidence = ComplianceEvidence(tenant_id=_uuid(tenant_id), created_by=_actor(actor), updated_by=_actor(actor), collected_by=values.pop("collected_by", _actor(actor)), collected_at=values.pop("collected_at", timezone.now()), **values)
        _validate_model(evidence); evidence.save(force_insert=True)
        ActivityService.record(tenant_id, actor, evidence, "evidence.registered", {}, _state(evidence), "", correlation_id)
        return evidence

    @classmethod
    @transaction.atomic
    def update_evidence(cls, tenant_id, actor, evidence_id, data, correlation_id):
        evidence = cls.get_evidence(tenant_id, evidence_id); before = _state(evidence)
        values = _only(data, {"name", "description", "evidence_type", "reference_kind", "document_id", "external_uri", "text_reference", "sha256", "classification", "collection_method", "valid_from", "valid_until"})
        for key, value in values.items(): setattr(evidence, key, value)
        evidence.updated_by = _actor(actor); _validate_model(evidence); evidence.save()
        ActivityService.record(tenant_id, actor, evidence, "evidence.updated", before, _state(evidence), "", correlation_id)
        return evidence

    @classmethod
    @transaction.atomic
    def archive_evidence(cls, tenant_id, actor, evidence_id, correlation_id):
        evidence = cls.get_evidence(tenant_id, evidence_id); before = _state(evidence)
        evidence.deleted_at = timezone.now(); evidence.deleted_by = _actor(actor); evidence.updated_by = _actor(actor); evidence.save()
        ActivityService.record(tenant_id, actor, evidence, "evidence.archived", before, _state(evidence), "", correlation_id)

    @classmethod
    @transaction.atomic
    def link_requirement(cls, tenant_id, actor, evidence_id, requirement_id, data, correlation_id):
        evidence = cls.get_evidence(tenant_id, evidence_id); requirement = _get(ComplianceRequirement, tenant_id, requirement_id)
        link = EvidenceRequirementLink(tenant_id=_uuid(tenant_id), evidence=evidence, requirement=requirement, created_by=_actor(actor), **dict(data))
        _validate_model(link); link.save(force_insert=True)
        ActivityService.record(tenant_id, actor, link, "evidence.linked", {}, _state(link), "", correlation_id)
        return link

    @staticmethod
    @transaction.atomic
    def unlink_requirement(tenant_id, actor, link_id, correlation_id):
        link = _get(EvidenceRequirementLink, tenant_id, link_id, include_deleted=True); before = _state(link)
        ActivityService.record(tenant_id, actor, link, "evidence.unlinked", before, {}, "", correlation_id); link.delete()

    @classmethod
    def validate_evidence(cls, tenant_id, evidence_id, as_of):
        evidence = cls.get_evidence(tenant_id, evidence_id); now = as_of or timezone.now()
        reference_valid = True
        if evidence.reference_kind == "dms_document":
            if cls.dms_validator is None: raise ComplianceDependencyUnavailable("DMS reference validation is unavailable.")
            cls.dms_validator.validate_document_reference(_uuid(tenant_id), evidence.document_id)
        fresh = (evidence.valid_from is None or evidence.valid_from <= now) and (evidence.valid_until is None or evidence.valid_until >= now)
        return {"evidence_id": evidence.id, "reference_valid": reference_valid, "hash_valid": bool(not evidence.sha256 or SHA256_RE.fullmatch(evidence.sha256)), "fresh": fresh, "checked_at": timezone.now()}

    @staticmethod
    def list_expiring(tenant_id, as_of, days):
        if days < 0 or days > 365: raise ComplianceValidationError({"days": ["Must be between 0 and 365."]})
        return ComplianceEvidence.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True, valid_until__gte=as_of, valid_until__lte=as_of + timedelta(days=days)).order_by("valid_until")


class ComplianceDashboardService:
    @classmethod
    def summary(cls, tenant_id, framework_id=None, as_of=None):
        tenant = _uuid(tenant_id); as_of = as_of or timezone.now()
        frameworks = ComplianceFramework.objects.for_tenant(tenant).filter(deleted_at__isnull=True)
        if framework_id: frameworks = frameworks.filter(pk=_uuid(framework_id))
        requirements = ComplianceRequirement.objects.for_tenant(tenant).filter(deleted_at__isnull=True, status="active")
        if framework_id: requirements = requirements.filter(framework_id=_uuid(framework_id))
        assessed_ids = ComplianceAssessment.objects.for_tenant(tenant).filter(requirement__in=requirements, assessed_at__lte=as_of).values_list("requirement_id", flat=True)
        gaps = sum(MappingService.gap_analysis(tenant, framework.id, as_of)["gap_count"] for framework in frameworks)
        warning_days = int(_effective_or_defaults(tenant)["evidence_warning_days"])
        return {"frameworks": frameworks.count(), "requirements": requirements.count(), "unassessed_requirements": requirements.exclude(id__in=assessed_ids).count(), "gaps": gaps, "review_queue": len(cls.review_queue(tenant, as_of)), "expiring_evidence": EvidenceService.list_expiring(tenant, as_of, warning_days).count()}

    @staticmethod
    def review_queue(tenant_id, as_of=None):
        value = as_of or timezone.now().date(); value = value.date() if isinstance(value, datetime) else value
        return list(CompliancePolicy.objects.for_tenant(_uuid(tenant_id)).filter(deleted_at__isnull=True, next_review_date__lte=value).exclude(status="archived").order_by("next_review_date"))

    @staticmethod
    def readiness_breakdown(tenant_id, framework_id, as_of=None):
        return AssessmentService.scorecard(tenant_id, framework_id, as_of)


# Backward compatible names retained for integrations while v2 callers use the
# precise aggregate service names above.
CompliancePolicyService = PolicyService
ComplianceRequirementService = RequirementService


__all__ = [name for name in globals() if name.endswith("Service") or name.startswith("Compliance")]

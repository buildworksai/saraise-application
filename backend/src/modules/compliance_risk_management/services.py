"""Tenant-first domain services for compliance risk management.

This is the only mutation boundary for the module.  Every write is atomic,
locks existing aggregates, records a correlation-aware transition/audit entry,
and stores a versioned outbox event in the same transaction.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.async_jobs.models import OutboxEvent
from src.core.api.results import CapabilityUnavailable, OperationFailed
from src.core.middleware.correlation import get_correlation_id
from src.core.tenancy import tenant_context

from .models import (
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
    RiskConfiguration,
    RiskConfigurationVersion,
)
from .state_machines import (
    transition_calendar,
    transition_control,
    transition_control_test,
    transition_remediation,
    transition_requirement,
    transition_risk,
)

ENVIRONMENTS = frozenset({"development", "staging", "production"})
LEVELS = ("negligible", "low", "medium", "high", "critical")
FEATURE_FLAGS = frozenset(
    {
        "risk_register",
        "controls",
        "control_tests",
        "requirements",
        "calendar",
        "remediation",
        "dashboard",
        "configuration",
        "risk_heatmap",
        "recurring_control_tests",
        "compliance_reminders",
    }
)


def _uuid(value: object, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


def _correlation_id() -> str:
    return get_correlation_id() or str(uuid.uuid4())


def _history(
    actor_id: uuid.UUID,
    operation: str,
    *,
    transition_key: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "actor_id": str(actor_id),
        "command": operation,
        "transition_key": transition_key,
        "from": from_status,
        "to": to_status,
        "context": context or {},
        "correlation_id": _correlation_id(),
        "occurred_at": timezone.now().isoformat(),
    }


def _event(
    tenant_id: uuid.UUID,
    aggregate: object,
    event_type: str,
    actor_id: uuid.UUID,
    operation: str,
    *,
    extra: dict[str, Any] | None = None,
) -> OutboxEvent:
    from .events import publish_domain_event

    return publish_domain_event(
        tenant_id,
        event_type,
        aggregate.__class__.__name__,
        getattr(aggregate, "pk"),
        actor_id=actor_id,
        correlation_id=_correlation_id(),
        payload={"command": operation, **(extra or {})},
    )


def _validate(instance: object) -> None:
    try:
        instance.full_clean()  # type: ignore[attr-defined]
    except DjangoValidationError as exc:
        detail = (
            getattr(exc, "message_dict", None)
            or getattr(exc, "messages", None)
            or {"non_field_errors": ["Invalid data."]}
        )
        raise ValidationError(detail) from exc


def _get(model: type, tenant_id: uuid.UUID, object_id: object, *, lock: bool = False, active_only: bool = True) -> Any:
    queryset = model.objects.for_tenant(tenant_id)
    if active_only and hasattr(model, "is_deleted"):
        queryset = queryset.filter(is_deleted=False)
    if lock:
        queryset = queryset.select_for_update()
    value = queryset.filter(pk=object_id).first()
    if value is None:
        raise NotFound()
    return value


def _same_tenant(model: type, tenant_id: uuid.UUID, object_id: object, field: str) -> Any:
    value = model.objects.for_tenant(tenant_id).filter(pk=object_id, is_deleted=False).first()
    if value is None:
        raise ValidationError({field: "The referenced record must belong to the authenticated tenant."})
    return value


def _save(instance: Any, *, fields: Iterable[str] | None = None) -> Any:
    _validate(instance)
    instance.save(update_fields=list(fields) if fields else None)
    return instance


def _idempotent(model: type, tenant_id: uuid.UUID, key: str) -> Any | None:
    if not key:
        raise ValidationError({"idempotency_key": "This field is required."})
    for value in model.objects.for_tenant(tenant_id).iterator():
        if any(
            entry.get("idempotency_key") == key or entry.get("transition_key") == key
            for entry in (value.transition_history or [])
        ):
            return value
    return None


def _transition(
    value: Any,
    actor_id: uuid.UUID,
    command: str,
    transition_key: str,
    resolver: Any,
    *,
    context: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    history = list(value.transition_history or [])
    prior = next((entry for entry in history if entry.get("transition_key") == transition_key), None)
    if prior:
        if prior.get("command") != command:
            raise ValidationError({"transition_key": "The key was already used for a different transition."})
        return value, False
    old = value.status
    try:
        new = resolver(old, command)
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or {"command": getattr(exc, "messages", ["Invalid transition."])}
        raise ValidationError(detail) from exc
    value.status = new
    history.append(
        _history(actor_id, command, transition_key=transition_key, from_status=old, to_status=new, context=context)
    )
    value.transition_history = history
    value.updated_by_id = actor_id
    return value, True


def _soft_delete(value: Any, actor_id: uuid.UUID) -> None:
    if value.is_deleted:
        return
    value.is_deleted = True
    value.deleted_at = timezone.now()
    value.deleted_by_id = actor_id
    value.updated_by_id = actor_id
    _save(value)


class RiskConfigurationService:
    """Validated, versioned runtime policy for scoring and operations."""

    @staticmethod
    def _environment(environment: str | None) -> str:
        value = environment or str(getattr(settings, "SARAISE_ENVIRONMENT", "development"))
        if value not in ENVIRONMENTS:
            raise ValidationError({"environment": "Unsupported environment."})
        return value

    @classmethod
    def get_active(cls, tenant_id: object, environment: str | None = None) -> RiskConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        env = cls._environment(environment)
        with tenant_context(tenant):
            active = RiskConfiguration.objects.for_tenant(tenant).filter(environment=env).first()
        if active is not None:
            return active
        # Model defaults are the canonical bootstrap document; it remains
        # unsaved until an administrator publishes version 1.
        return RiskConfiguration(
            tenant_id=tenant, environment=env, version=0, published_by_id=uuid.UUID(int=0), published_at=timezone.now()
        )

    @classmethod
    def validate_candidate(cls, candidate: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "likelihood_scale_max",
            "impact_scale_max",
            "level_thresholds",
            "default_review_days",
            "default_reminder_days",
            "acceptance_max_days",
            "overdue_job_enabled",
            "feature_flags",
            "extension_config",
            "change_summary",
        }
        unknown = set(candidate) - allowed
        if unknown:
            raise ValidationError({name: "Unknown configuration field." for name in sorted(unknown)})
        candidate.setdefault("extension_config", {})
        required = allowed - {"change_summary", "extension_config"}
        missing = required - set(candidate)
        if missing:
            raise ValidationError({name: "This field is required." for name in sorted(missing)})
        likelihood = int(candidate["likelihood_scale_max"])
        impact = int(candidate["impact_scale_max"])
        if not 3 <= likelihood <= 10 or not 3 <= impact <= 10:
            raise ValidationError({"likelihood_scale_max": "Scales must be between 3 and 10."})
        reminders = candidate["default_reminder_days"]
        if not isinstance(reminders, list) or any(type(v) is not int or not 0 <= v <= 365 for v in reminders):
            raise ValidationError({"default_reminder_days": "Use unique integer days between 0 and 365."})
        candidate["default_reminder_days"] = sorted(set(reminders), reverse=True)
        if not 1 <= int(candidate["default_review_days"]) <= 3650:
            raise ValidationError({"default_review_days": "Must be between 1 and 3650."})
        if not 1 <= int(candidate["acceptance_max_days"]) <= 1095:
            raise ValidationError({"acceptance_max_days": "Must be between 1 and 1095."})
        cls._validate_thresholds(candidate["level_thresholds"], likelihood * impact)
        cls._validate_feature_flags(candidate["feature_flags"])
        if not isinstance(candidate["extension_config"], dict):
            raise ValidationError({"extension_config": "Extension configuration must be an object."})
        if candidate["extension_config"]:
            from .extensions import registry

            for key, document in candidate["extension_config"].items():
                try:
                    registry.validate_fragment(key, document)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValidationError(
                        {"extension_config": f"Invalid or unavailable schema fragment {key}."}
                    ) from exc
        return candidate

    @staticmethod
    def _validate_thresholds(thresholds: object, maximum: int) -> None:
        if not isinstance(thresholds, dict) or tuple(thresholds.keys()) != LEVELS:
            raise ValidationError({"level_thresholds": f"Thresholds must contain ordered levels: {', '.join(LEVELS)}."})
        values = list(thresholds.values())
        if (
            any(type(value) not in (int, float) for value in values)
            or values != sorted(values)
            or len(set(values)) != len(values)
        ):
            raise ValidationError({"level_thresholds": "Threshold upper bounds must increase monotonically."})
        if values[0] < 1 or values[-1] < maximum:
            raise ValidationError({"level_thresholds": "Thresholds must cover every possible score."})

    @staticmethod
    def _validate_feature_flags(flags: object) -> None:
        if not isinstance(flags, dict):
            raise ValidationError({"feature_flags": "Feature flags must be an object."})
        unknown = set(flags) - FEATURE_FLAGS
        if unknown:
            raise ValidationError({"feature_flags": f"Unsupported flags: {', '.join(sorted(unknown))}."})
        for name, rule in flags.items():
            if isinstance(rule, bool):
                continue
            if not isinstance(rule, dict) or set(rule) - {"enabled", "roles", "cohorts", "tenants"}:
                raise ValidationError({"feature_flags": f"Invalid rollout rule for {name}."})
            for key in ("roles", "cohorts", "tenants"):
                if key in rule and not isinstance(rule[key], list):
                    raise ValidationError({"feature_flags": f"{name}.{key} must be a list."})

    @classmethod
    def _snapshot(cls, config: RiskConfiguration) -> dict[str, Any]:
        return {
            name: getattr(config, name)
            for name in (
                "likelihood_scale_max",
                "impact_scale_max",
                "level_thresholds",
                "default_review_days",
                "default_reminder_days",
                "acceptance_max_days",
                "overdue_job_enabled",
                "feature_flags",
                "extension_config",
            )
        }

    @classmethod
    def preview(
        cls, tenant_id: object, actor_id: object, environment: str, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        tenant, _actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        checked = cls.validate_candidate(dict(candidate))
        active = cls.get_active(tenant, environment)
        affected = RiskAssessment.objects.for_tenant(tenant).filter(is_deleted=False).count()

        def level(thresholds: dict[str, object], score: int) -> str:
            return next((name for name in LEVELS if score <= int(thresholds[name])), "critical")

        score_changes = []
        maximum = checked["likelihood_scale_max"] * checked["impact_scale_max"]
        for score in range(1, maximum + 1):
            before = (
                level(active.level_thresholds, score)
                if score <= active.likelihood_scale_max * active.impact_scale_max
                else "critical"
            )
            after = level(checked["level_thresholds"], score)
            if before != after:
                score_changes.append({"score": score, "from": before, "to": after})
        return {
            "valid": True,
            "validation_errors": [],
            "score_band_changes": score_changes,
            "affected_record_counts": {
                "risks": affected,
                "controls": Control.objects.for_tenant(tenant).filter(is_deleted=False).count(),
                "calendar_entries": ComplianceCalendarEntry.objects.for_tenant(tenant).filter(is_deleted=False).count(),
            },
        }

    @classmethod
    def publish(
        cls,
        tenant_id: object,
        actor_id: object,
        environment: str,
        candidate: dict[str, Any],
        expected_version: int,
        *,
        restored_from_version: int | None = None,
        event_type: str = "configuration.published.v1",
    ) -> RiskConfiguration:
        tenant, actor, env = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"), cls._environment(environment)
        checked = cls.validate_candidate(dict(candidate))
        summary = str(checked.pop("change_summary", "Configuration published"))[:500]
        with transaction.atomic(), tenant_context(tenant):
            current = RiskConfiguration.objects.for_tenant(tenant).select_for_update().filter(environment=env).first()
            version = current.version if current else 0
            if version != expected_version:
                raise OperationFailed(
                    error_code="VERSION_CONFLICT",
                    message="The configuration changed after it was loaded.",
                    detail={"expected_version": expected_version, "active_version": version},
                    http_status=409,
                )
            if current is None:
                current = RiskConfiguration(tenant_id=tenant, environment=env, created_by_id=actor)
            for key, value in checked.items():
                setattr(current, key, value)
            current.version = version + 1
            current.published_at = timezone.now()
            current.published_by_id = actor
            current.updated_by_id = actor
            _save(current)
            RiskConfigurationVersion.objects.create(
                tenant_id=tenant,
                environment=env,
                version=current.version,
                configuration=cls._snapshot(current),
                change_summary=summary,
                actor_id=actor,
                correlation_id=_correlation_id(),
                restored_from_version=restored_from_version,
            )
            event_payload = {"version": current.version, "environment": env}
            if restored_from_version is not None:
                event_payload["restored_from_version"] = restored_from_version
            _event(tenant, current, event_type, actor, "publish", extra=event_payload)
            return current

    @classmethod
    def list_versions(cls, tenant_id: object, environment: str) -> QuerySet[RiskConfigurationVersion]:
        tenant = _uuid(tenant_id, "tenant_id")
        return (
            RiskConfigurationVersion.objects.for_tenant(tenant)
            .filter(environment=cls._environment(environment))
            .order_by("-version")
        )

    @classmethod
    def get_version(cls, tenant_id: object, environment: str, version: int) -> RiskConfigurationVersion:
        tenant = _uuid(tenant_id, "tenant_id")
        value = cls.list_versions(tenant, environment).filter(version=version).first()
        if value is None:
            raise NotFound()
        return value

    @classmethod
    def rollback(
        cls, tenant_id: object, actor_id: object, environment: str, version: int, expected_version: int
    ) -> RiskConfiguration:
        source = cls.get_version(tenant_id, environment, version)
        candidate = dict(source.configuration)
        candidate["change_summary"] = f"Restored from version {version}"
        return cls.publish(
            tenant_id,
            actor_id,
            environment,
            candidate,
            expected_version,
            restored_from_version=version,
            event_type="configuration.rolled_back.v1",
        )

    @classmethod
    def export_document(cls, tenant_id: object, environment: str) -> dict[str, Any]:
        active = cls.get_active(tenant_id, environment)
        return {
            "schema": "saraise.compliance-risk.configuration",
            "schema_version": 1,
            "environment": active.environment,
            "version": active.version,
            "configuration": cls._snapshot(active),
        }

    @classmethod
    def import_document(
        cls, tenant_id: object, actor_id: object, environment: str, document: dict[str, Any], dry_run: bool
    ) -> object:
        if document.get("schema") != "saraise.compliance-risk.configuration" or document.get("schema_version") != 1:
            raise ValidationError({"document": "Unsupported configuration document schema."})
        if document.get("environment") != cls._environment(environment):
            raise ValidationError({"document": "Document environment does not match the target environment."})
        candidate = dict(document.get("configuration") or {})
        candidate["change_summary"] = "Imported configuration document"
        if dry_run:
            return cls.preview(tenant_id, actor_id, environment, candidate)
        active = cls.get_active(tenant_id, environment)
        return cls.publish(
            tenant_id,
            actor_id,
            environment,
            candidate,
            active.version,
            event_type="configuration.imported.v1",
        )

    @classmethod
    def evaluate_feature(cls, tenant_id: object, feature: str, actor_context: dict[str, Any]) -> bool:
        if feature not in FEATURE_FLAGS:
            return False
        rule = cls.get_active(tenant_id).feature_flags.get(feature, True)
        if isinstance(rule, bool):
            return rule
        if not rule.get("enabled", False):
            return False
        tenant = str(_uuid(tenant_id, "tenant_id"))
        return (
            not any(rule.get(key) for key in ("roles", "cohorts", "tenants"))
            or actor_context.get("role") in rule.get("roles", [])
            or actor_context.get("cohort") in rule.get("cohorts", [])
            or tenant in rule.get("tenants", [])
        )


class RiskAssessmentService:
    @staticmethod
    def list_risks(
        tenant_id: object, filters: dict[str, Any] | None = None, ordering: str = "risk_code"
    ) -> QuerySet[RiskAssessment]:
        tenant = _uuid(tenant_id, "tenant_id")
        qs = RiskAssessment.objects.for_tenant(tenant).filter(is_deleted=False)
        filters = filters or {}
        for field in ("category", "risk_level", "status", "owner_id"):
            if filters.get(field):
                qs = qs.filter(**{field: filters[field]})
        if filters.get("search"):
            qs = qs.filter(Q(risk_code__icontains=filters["search"]) | Q(name__icontains=filters["search"]))
        if filters.get("review_from"):
            qs = qs.filter(review_date__gte=filters["review_from"])
        if filters.get("review_to"):
            qs = qs.filter(review_date__lte=filters["review_to"])
        if ordering.lstrip("-") not in {"risk_code", "inherent_score", "review_date", "created_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_risk(tenant_id: object, risk_id: object) -> RiskAssessment:
        return _get(RiskAssessment, _uuid(tenant_id, "tenant_id"), risk_id)

    @classmethod
    def calculate_scores(
        cls,
        tenant_id: object,
        likelihood: int,
        impact: int,
        residual_likelihood: int | None = None,
        residual_impact: int | None = None,
    ) -> dict[str, Any]:
        config = RiskConfigurationService.get_active(tenant_id)
        if not 1 <= likelihood <= config.likelihood_scale_max or not 1 <= impact <= config.impact_scale_max:
            raise ValidationError({"likelihood": "Value is outside the configured scoring scale."})
        if (residual_likelihood is None) != (residual_impact is None):
            raise ValidationError("Residual likelihood and impact must be supplied together.")
        inherent = Decimal(likelihood * impact).quantize(Decimal("0.01"))
        residual = None
        if residual_likelihood is not None and residual_impact is not None:
            if (
                not 1 <= residual_likelihood <= config.likelihood_scale_max
                or not 1 <= residual_impact <= config.impact_scale_max
            ):
                raise ValidationError({"residual_likelihood": "Value is outside the configured scoring scale."})
            residual = Decimal(residual_likelihood * residual_impact).quantize(Decimal("0.01"))
        level = next((name for name in LEVELS if inherent <= Decimal(str(config.level_thresholds[name]))), "critical")
        return {
            "inherent_score": inherent,
            "residual_score": residual,
            "risk_level": level,
            "likelihood_scale_max": config.likelihood_scale_max,
            "impact_scale_max": config.impact_scale_max,
            "explanation": {
                "formula": "likelihood × impact",
                "likelihood": likelihood,
                "impact": impact,
                "threshold_version": config.version,
                "matched_upper_bound": config.level_thresholds[level],
            },
        }

    @classmethod
    def preview_score(cls, tenant_id: object, payload: dict[str, Any]) -> dict[str, Any]:
        return cls.calculate_scores(
            tenant_id,
            payload["likelihood"],
            payload["impact"],
            payload.get("residual_likelihood"),
            payload.get("residual_impact"),
        )

    @classmethod
    def create_risk(
        cls,
        tenant_id: object,
        actor_id: object,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        **legacy: Any,
    ) -> RiskAssessment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        data = dict(payload or {})
        data.update(legacy)
        # Compatibility with the original public service signature.
        if "risk_name" in data:
            data["name"] = data.pop("risk_name")
        data.pop("risk_level", None)
        key = idempotency_key or str(data.pop("idempotency_key", ""))
        with transaction.atomic(), tenant_context(tenant):
            existing = _idempotent(RiskAssessment, tenant, key)
            if existing:
                return existing
            scores = cls.calculate_scores(
                tenant,
                int(data["likelihood"]),
                int(data["impact"]),
                data.get("residual_likelihood"),
                data.get("residual_impact"),
            )
            data.update({k: scores[k] for k in ("inherent_score", "residual_score", "risk_level")})
            data["risk_code"] = str(data["risk_code"]).strip().upper()
            risk = RiskAssessment(
                tenant_id=tenant,
                created_by_id=actor,
                transition_history=[{**_history(actor, "create"), "idempotency_key": key}],
                **data,
            )
            _save(risk)
            _event(tenant, risk, "risk.created.v1", actor, "create")
            return risk

    @classmethod
    def update_risk(
        cls, tenant_id: object, actor_id: object, risk_id: object, payload: dict[str, Any]
    ) -> RiskAssessment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            risk = _get(RiskAssessment, tenant, risk_id, lock=True)
            if risk.status == "closed":
                raise ValidationError({"status": "Closed risks can only be changed by reopening them."})
            for key, value in payload.items():
                setattr(risk, key, value)
            if "risk_code" in payload:
                risk.risk_code = risk.risk_code.strip().upper()
            scores = cls.calculate_scores(
                tenant, risk.likelihood, risk.impact, risk.residual_likelihood, risk.residual_impact
            )
            for key in ("inherent_score", "residual_score", "risk_level"):
                setattr(risk, key, scores[key])
            risk.updated_by_id = actor
            risk.transition_history = [*(risk.transition_history or []), _history(actor, "update")]
            _save(risk)
            _event(tenant, risk, "risk.updated.v1", actor, "update")
            return risk

    @classmethod
    def soft_delete_risk(cls, tenant_id: object, actor_id: object, risk_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            risk = _get(RiskAssessment, tenant, risk_id, lock=True)
            _soft_delete(risk, actor)
            _event(tenant, risk, "risk.deleted.v1", actor, "delete")

    @classmethod
    def transition_risk(
        cls,
        tenant_id: object,
        actor_id: object,
        risk_id: object,
        command: str,
        transition_key: str,
        context: dict[str, Any] | None = None,
    ) -> RiskAssessment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        ctx = context or {}
        with transaction.atomic(), tenant_context(tenant):
            risk = _get(RiskAssessment, tenant, risk_id, lock=True)
            old = risk.status
            risk, changed = _transition(risk, actor, command, transition_key, transition_risk, context=ctx)
            if not changed:
                return risk
            config = RiskConfigurationService.get_active(tenant)
            if command == "accept":
                accepted = ctx.get("accepted_until")
                if not accepted:
                    raise ValidationError({"context": {"accepted_until": "Required when accepting a risk."}})
                accepted_date = date.fromisoformat(accepted) if isinstance(accepted, str) else accepted
                if accepted_date <= timezone.localdate() or accepted_date > timezone.localdate() + timedelta(
                    days=config.acceptance_max_days
                ):
                    raise ValidationError(
                        {"context": {"accepted_until": "Date is outside the configured acceptance window."}}
                    )
                risk.accepted_until = accepted_date
            if command == "close":
                if (
                    RemediationAction.objects.for_tenant(tenant)
                    .filter(risk=risk, is_deleted=False)
                    .exclude(status__in=("completed", "cancelled"))
                    .exists()
                ):
                    raise ValidationError(
                        {"command": "Required remediation must be completed before closing the risk."}
                    )
                risk.closed_at = timezone.now()
                risk.accepted_until = None
            elif command == "reopen":
                risk.closed_at = None
                risk.accepted_until = None
            _save(risk)
            _event(
                tenant,
                risk,
                "risk.transitioned.v1",
                actor,
                command,
                extra={"from_status": old, "to_status": risk.status},
            )
            return risk

    @classmethod
    def dashboard_summary(cls, tenant_id: object, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        today = timezone.localdate()
        risks = cls.list_risks(tenant, filters)
        by_level = {
            item["risk_level"]: item["count"] for item in risks.values("risk_level").annotate(count=Count("id"))
        }
        by_status = {item["status"]: item["count"] for item in risks.values("status").annotate(count=Count("id"))}
        upcoming = (
            ComplianceCalendarEntry.objects.for_tenant(tenant)
            .filter(is_deleted=False, status="upcoming", scheduled_date__gte=today)
            .order_by("scheduled_date")[:10]
        )
        upcoming_list = list(upcoming)
        overdue_work = [
            {"id": risk.id, "kind": "risk", "label": risk.risk_code, "due_date": risk.review_date}
            for risk in risks.filter(review_date__lt=today).exclude(status="closed")[:25]
        ]
        return {
            "total_risks": risks.count(),
            "critical_risks": risks.filter(risk_level="critical").count(),
            "risks_by_level": by_level,
            "risks_by_status": by_status,
            "overdue_reviews": risks.filter(review_date__lt=today).exclude(status="closed").count(),
            "overdue_controls": Control.objects.for_tenant(tenant)
            .filter(is_deleted=False, status="active", next_test_due__lt=today)
            .count(),
            "overdue_calendar": ComplianceCalendarEntry.objects.for_tenant(tenant)
            .filter(is_deleted=False, status="overdue")
            .count(),
            "overdue_remediations": RemediationAction.objects.for_tenant(tenant)
            .filter(is_deleted=False, status="overdue")
            .count(),
            "upcoming_events": len(upcoming_list),
            "upcoming_compliance_events": upcoming_list,
            "overdue_work": overdue_work,
        }

    @classmethod
    def heatmap(
        cls, tenant_id: object, category: str | None = None, owner_id: object | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        qs = cls.list_risks(tenant_id, {"category": category, "owner_id": owner_id, "status": status})
        cells: dict[tuple[int, int], list[tuple[uuid.UUID, str]]] = defaultdict(list)
        for risk in qs.only("id", "likelihood", "impact", "risk_level"):
            cells[(risk.likelihood, risk.impact)].append((risk.id, risk.risk_level))
        return [
            {
                "likelihood": key[0],
                "impact": key[1],
                "count": len(items),
                "level": items[0][1],
                "risk_ids": [item[0] for item in items],
            }
            for key, items in sorted(cells.items())
        ]


class ControlService:
    @staticmethod
    def list_controls(
        tenant_id: object, filters: dict[str, Any] | None = None, ordering: str = "control_code"
    ) -> QuerySet[Control]:
        tenant = _uuid(tenant_id, "tenant_id")
        qs = Control.objects.for_tenant(tenant).filter(is_deleted=False)
        filters = filters or {}
        for field in ("risk_id", "status", "frequency", "owner_id"):
            if filters.get(field):
                qs = qs.filter(**{field: filters[field]})
        if filters.get("due_from"):
            qs = qs.filter(next_test_due__gte=filters["due_from"])
        if filters.get("due_to"):
            qs = qs.filter(next_test_due__lte=filters["due_to"])
        if ordering.lstrip("-") not in {"control_code", "next_test_due", "created_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_control(tenant_id: object, control_id: object) -> Control:
        return _get(Control, _uuid(tenant_id, "tenant_id"), control_id)

    @classmethod
    def create_control(cls, tenant_id: object, actor_id: object, risk_id: object, payload: dict[str, Any]) -> Control:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            risk = _same_tenant(RiskAssessment, tenant, risk_id, "risk_id")
            value = Control(
                tenant_id=tenant,
                risk=risk,
                created_by_id=actor,
                transition_history=[_history(actor, "create")],
                **payload,
            )
            value.control_code = value.control_code.strip().upper()
            _save(value)
            _event(tenant, value, "control.created.v1", actor, "create")
            return value

    @classmethod
    def update_control(
        cls, tenant_id: object, actor_id: object, control_id: object, payload: dict[str, Any]
    ) -> Control:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(Control, tenant, control_id, lock=True)
            if value.status == "retired":
                raise ValidationError({"status": "Retired controls must be reactivated before editing."})
            for key, item in payload.items():
                setattr(value, key, item)
            value.updated_by_id = actor
            value.transition_history = [*(value.transition_history or []), _history(actor, "update")]
            _save(value)
            _event(tenant, value, "control.updated.v1", actor, "update")
            return value

    @classmethod
    def soft_delete_control(cls, tenant_id: object, actor_id: object, control_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(Control, tenant, control_id, lock=True)
            _soft_delete(value, actor)
            _event(tenant, value, "control.deleted.v1", actor, "delete")

    @classmethod
    def transition_control(
        cls, tenant_id: object, actor_id: object, control_id: object, command: str, transition_key: str
    ) -> Control:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(Control, tenant, control_id, lock=True)
            value, changed = _transition(value, actor, command, transition_key, transition_control)
            if changed:
                _save(value)
                _event(tenant, value, "control.transitioned.v1", actor, command)
            return value

    @classmethod
    def schedule_next_test(
        cls, tenant_id: object, actor_id: object, control_id: object, scheduled_for: date | None = None
    ) -> ControlTest:
        control = cls.get_control(tenant_id, control_id)
        target = scheduled_for or control.next_test_due
        return ControlTestService.schedule_test(
            tenant_id,
            actor_id,
            control_id,
            {"scheduled_for": target, "tester_id": control.default_tester_id or control.owner_id},
            f"recurring:{control_id}:{target}",
        )


class ControlTestService:
    @staticmethod
    def list_tests(
        tenant_id: object, filters: dict[str, Any] | None = None, ordering: str = "-scheduled_for"
    ) -> QuerySet[ControlTest]:
        tenant = _uuid(tenant_id, "tenant_id")
        qs = ControlTest.objects.for_tenant(tenant).filter(is_deleted=False)
        filters = filters or {}
        for field in ("control_id", "status", "result", "tester_id"):
            if filters.get(field):
                qs = qs.filter(**{field: filters[field]})
        if filters.get("risk_id"):
            qs = qs.filter(control__risk_id=filters["risk_id"])
        if filters.get("date_from"):
            qs = qs.filter(scheduled_for__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(scheduled_for__lte=filters["date_to"])
        if ordering.lstrip("-") not in {"scheduled_for", "completed_at", "created_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_test(tenant_id: object, test_id: object) -> ControlTest:
        return _get(ControlTest, _uuid(tenant_id, "tenant_id"), test_id)

    @classmethod
    def schedule_test(
        cls, tenant_id: object, actor_id: object, control_id: object, payload: dict[str, Any], idempotency_key: str
    ) -> ControlTest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            existing = _idempotent(ControlTest, tenant, idempotency_key)
            if existing:
                return existing
            control = _same_tenant(Control, tenant, control_id, "control_id")
            value = ControlTest(
                tenant_id=tenant,
                control=control,
                created_by_id=actor,
                transition_history=[{**_history(actor, "schedule"), "idempotency_key": idempotency_key}],
                **payload,
            )
            _save(value)
            _event(tenant, value, "control_test.scheduled.v1", actor, "schedule")
            return value

    @classmethod
    def update_scheduled_test(
        cls, tenant_id: object, actor_id: object, test_id: object, payload: dict[str, Any]
    ) -> ControlTest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ControlTest, tenant, test_id, lock=True)
            if value.status != "scheduled":
                raise ValidationError({"status": "Only scheduled tests may be edited."})
            for key, item in payload.items():
                setattr(value, key, item)
            value.updated_by_id = actor
            _save(value)
            _event(tenant, value, "control_test.updated.v1", actor, "update")
            return value

    @classmethod
    def start_test(cls, tenant_id: object, actor_id: object, test_id: object, transition_key: str) -> ControlTest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ControlTest, tenant, test_id, lock=True)
            value, changed = _transition(value, actor, "start", transition_key, transition_control_test)
            if changed:
                value.started_at = timezone.now()
                _save(value)
                _event(tenant, value, "control_test.started.v1", actor, "start")
            return value

    @staticmethod
    def validate_evidence(tenant_id: object, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _uuid(tenant_id, "tenant_id")
        if not isinstance(evidence, list):
            raise ValidationError({"evidence": "Must be a list."})
        exact = {"document_id", "version_id", "label", "checksum"}
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or set(item) != exact:
                raise ValidationError({"evidence": {index: "Evidence must use the exact document reference schema."}})
            _uuid(item["document_id"], "document_id")
            _uuid(item["version_id"], "version_id")
            if not item["label"] or not item["checksum"]:
                raise ValidationError({"evidence": {index: "Label and checksum are required."}})
        if evidence:
            from .integrations import IntegrationUnavailable, get_dms_adapter

            adapter = get_dms_adapter()
            for item in evidence:
                try:
                    verified = adapter.verify_version(
                        _uuid(tenant_id, "tenant_id"), item["document_id"], item["version_id"], item["checksum"]
                    )
                except IntegrationUnavailable as exc:
                    raise CapabilityUnavailable(capability="dms_evidence_verification") from exc
                if not verified:
                    raise ValidationError({"evidence": "A referenced DMS version could not be verified."})
        return evidence

    @classmethod
    def record_result(
        cls, tenant_id: object, actor_id: object, test_id: object, payload: dict[str, Any], transition_key: str
    ) -> ControlTest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ControlTest, tenant, test_id, lock=True)
            result = payload["result"]
            if result in ("failed", "partially_passed") and not str(payload.get("findings", "")).strip():
                raise ValidationError({"findings": "Findings are required for failed or partial results."})
            evidence = cls.validate_evidence(tenant, payload.get("evidence", []))
            value, changed = _transition(value, actor, "record_result", transition_key, transition_control_test)
            if not changed:
                return value
            value.result, value.findings, value.evidence, value.completed_at = (
                result,
                payload.get("findings", ""),
                evidence,
                timezone.now(),
            )
            if result in ("failed", "partially_passed"):
                remediation = payload.get("remediation")
                if not remediation:
                    raise ValidationError({"remediation": "A remediation action is required for this result."})
                RemediationService.create_action(
                    tenant, actor, value.control.risk_id, {**remediation, "control_test": value}
                )
            _save(value)
            _event(tenant, value, "control_test.completed.v1", actor, "record_result", extra={"result": result})
            return value

    @classmethod
    def cancel_test(
        cls, tenant_id: object, actor_id: object, test_id: object, reason: str, transition_key: str
    ) -> ControlTest:
        if not reason.strip():
            raise ValidationError({"reason": "Cancellation reason is required."})
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ControlTest, tenant, test_id, lock=True)
            value, changed = _transition(value, actor, "cancel", transition_key, transition_control_test)
            if changed:
                value.cancellation_reason = reason
                value.completed_at = timezone.now()
                _save(value)
                _event(tenant, value, "control_test.cancelled.v1", actor, "cancel")
            return value

    @classmethod
    def create_follow_up_schedule(cls, tenant_id: object, actor_id: object, completed_test_id: object) -> ControlTest:
        completed = cls.get_test(tenant_id, completed_test_id)
        if completed.status != "completed":
            raise ValidationError({"test_id": "Only completed tests can create follow-up schedules."})
        return ControlService.schedule_next_test(tenant_id, actor_id, completed.control_id)


class ComplianceRequirementService:
    @staticmethod
    def list_requirements(
        tenant_id: object, filters: dict[str, Any] | None = None, ordering: str = "regulation_code"
    ) -> QuerySet[ComplianceRequirement]:
        tenant = _uuid(tenant_id, "tenant_id")
        qs = ComplianceRequirement.objects.for_tenant(tenant).filter(is_deleted=False)
        filters = filters or {}
        for field in ("regulation_code", "applicability", "status", "owner_id"):
            if filters.get(field):
                qs = qs.filter(**{field: filters[field]})
        if filters.get("search"):
            qs = qs.filter(Q(title__icontains=filters["search"]) | Q(requirement_code__icontains=filters["search"]))
        if filters.get("due_from"):
            qs = qs.filter(due_date__gte=filters["due_from"])
        if filters.get("due_to"):
            qs = qs.filter(due_date__lte=filters["due_to"])
        if ordering.lstrip("-") not in {"regulation_code", "requirement_code", "due_date", "created_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_requirement(tenant_id: object, requirement_id: object) -> ComplianceRequirement:
        return _get(ComplianceRequirement, _uuid(tenant_id, "tenant_id"), requirement_id)

    @staticmethod
    def validate_cross_references(
        tenant_id: object, requirement_id: object | None, reference_ids: list[object]
    ) -> list[str]:
        tenant = _uuid(tenant_id, "tenant_id")
        normalized = [str(_uuid(item, "cross_references")) for item in reference_ids]
        if requirement_id and str(requirement_id) in normalized:
            raise ValidationError({"cross_references": "A requirement cannot reference itself."})
        found = set(
            str(value)
            for value in ComplianceRequirement.objects.for_tenant(tenant)
            .filter(id__in=normalized, is_deleted=False)
            .values_list("id", flat=True)
        )
        if found != set(normalized):
            raise NotFound()
        return normalized

    @classmethod
    def create_requirement(cls, tenant_id: object, actor_id: object, payload: dict[str, Any]) -> ComplianceRequirement:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        data = dict(payload)
        data["cross_references"] = cls.validate_cross_references(tenant, None, data.get("cross_references", []))
        with transaction.atomic(), tenant_context(tenant):
            value = ComplianceRequirement(
                tenant_id=tenant, created_by_id=actor, transition_history=[_history(actor, "create")], **data
            )
            _save(value)
            _event(tenant, value, "requirement.created.v1", actor, "create")
            return value

    @classmethod
    def update_requirement(
        cls, tenant_id: object, actor_id: object, requirement_id: object, payload: dict[str, Any]
    ) -> ComplianceRequirement:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceRequirement, tenant, requirement_id, lock=True)
            data = dict(payload)
            if "cross_references" in data:
                data["cross_references"] = cls.validate_cross_references(tenant, value.id, data["cross_references"])
            for key, item in data.items():
                setattr(value, key, item)
            value.updated_by_id = actor
            _save(value)
            _event(tenant, value, "requirement.updated.v1", actor, "update")
            return value

    @classmethod
    def soft_delete_requirement(cls, tenant_id: object, actor_id: object, requirement_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceRequirement, tenant, requirement_id, lock=True)
            _soft_delete(value, actor)
            _event(tenant, value, "requirement.deleted.v1", actor, "delete")

    @classmethod
    def assess_requirement(
        cls,
        tenant_id: object,
        actor_id: object,
        requirement_id: object,
        command: str,
        evidence: list[dict[str, Any]],
        rationale: str,
        transition_key: str,
    ) -> ComplianceRequirement:
        if not rationale.strip():
            raise ValidationError({"rationale": "Assessment rationale is required."})
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        ControlTestService.validate_evidence(tenant, evidence)
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceRequirement, tenant, requirement_id, lock=True)
            old = value.status
            value, changed = _transition(
                value,
                actor,
                command,
                transition_key,
                transition_requirement,
                context={"rationale": rationale, "evidence": evidence},
            )
            if changed:
                value.last_assessed_at = timezone.now()
                _save(value)
                _event(
                    tenant,
                    value,
                    "requirement.status_changed.v1",
                    actor,
                    command,
                    extra={"from_status": old, "to_status": value.status},
                )
            return value


class ComplianceCalendarService:
    @staticmethod
    def list_entries(
        tenant_id: object,
        date_from: object,
        date_to: object,
        filters: dict[str, Any] | None = None,
        ordering: str = "scheduled_date",
    ) -> QuerySet[ComplianceCalendarEntry]:
        if not date_from or not date_to:
            raise ValidationError({"date_from": "Both date_from and date_to are required."})
        tenant = _uuid(tenant_id, "tenant_id")
        qs = ComplianceCalendarEntry.objects.for_tenant(tenant).filter(
            is_deleted=False, scheduled_date__range=(date_from, date_to)
        )
        filters = filters or {}
        mapping = {
            "type": "event_type",
            "status": "status",
            "requirement": "requirement_id",
            "assignee": "assigned_to_id",
        }
        for key, field in mapping.items():
            if filters.get(key):
                qs = qs.filter(**{field: filters[key]})
        if ordering.lstrip("-") not in {"scheduled_date", "created_at", "title"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_entry(tenant_id: object, entry_id: object) -> ComplianceCalendarEntry:
        return _get(ComplianceCalendarEntry, _uuid(tenant_id, "tenant_id"), entry_id)

    @classmethod
    def create_entry(cls, tenant_id: object, actor_id: object, payload: dict[str, Any]) -> ComplianceCalendarEntry:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        data = dict(payload)
        requirement_id = getattr(data.pop("requirement", None), "id", None) or data.pop("requirement_id", None)
        requirement = _same_tenant(ComplianceRequirement, tenant, requirement_id, "requirement")
        data["reminder_days"] = sorted(set(data.get("reminder_days", [])), reverse=True)
        with transaction.atomic(), tenant_context(tenant):
            value = ComplianceCalendarEntry(
                tenant_id=tenant,
                requirement=requirement,
                created_by_id=actor,
                transition_history=[_history(actor, "create")],
                **data,
            )
            _save(value)
            _event(tenant, value, "calendar.created.v1", actor, "create")
            return value

    @classmethod
    def update_entry(
        cls, tenant_id: object, actor_id: object, entry_id: object, payload: dict[str, Any]
    ) -> ComplianceCalendarEntry:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceCalendarEntry, tenant, entry_id, lock=True)
            if value.status in ("completed", "cancelled"):
                raise ValidationError({"status": "Terminal calendar entries cannot be edited."})
            for key, item in payload.items():
                setattr(value, key, item)
            value.updated_by_id = actor
            _save(value)
            _event(tenant, value, "calendar.updated.v1", actor, "update")
            return value

    @classmethod
    def soft_delete_entry(cls, tenant_id: object, actor_id: object, entry_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceCalendarEntry, tenant, entry_id, lock=True)
            _soft_delete(value, actor)
            _event(tenant, value, "calendar.deleted.v1", actor, "delete")

    @classmethod
    def transition_entry(
        cls,
        tenant_id: object,
        actor_id: object,
        entry_id: object,
        command: str,
        transition_key: str,
        context: dict[str, Any] | None = None,
    ) -> ComplianceCalendarEntry:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        ctx = context or {}
        with transaction.atomic(), tenant_context(tenant):
            value = _get(ComplianceCalendarEntry, tenant, entry_id, lock=True)
            value, changed = _transition(value, actor, command, transition_key, transition_calendar, context=ctx)
            if changed:
                if command == "complete":
                    value.completed_date = ctx.get("completed_date") or timezone.localdate()
                    value.completion_notes = ctx.get("completion_notes", "")
                _save(value)
                _event(tenant, value, "calendar.transitioned.v1", actor, command)
            return value

    @classmethod
    def mark_overdue_batch(cls, tenant_id: object, actor_id: object, as_of: date, job_id: object) -> int:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        changed = 0
        for value in ComplianceCalendarEntry.objects.for_tenant(tenant).filter(
            is_deleted=False, status="upcoming", scheduled_date__lt=as_of
        ):
            cls.transition_entry(tenant, actor, value.id, "mark_overdue", f"job:{job_id}:{value.id}")
            changed += 1
        return changed

    @classmethod
    def enqueue_due_reminders(cls, tenant_id: object, actor_id: object, as_of: date, idempotency_key: str) -> int:
        from .integrations import get_notification_adapter

        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        adapter = get_notification_adapter()
        queued = 0
        for entry in ComplianceCalendarEntry.objects.for_tenant(tenant).filter(
            is_deleted=False, status__in=("upcoming", "overdue")
        ):
            delta = (entry.scheduled_date - as_of).days
            if delta in entry.reminder_days:
                outcome = adapter.enqueue_reminder(
                    tenant, entry.id, entry.assigned_to_id, f"{idempotency_key}:{entry.id}:{delta}"
                )
                if not outcome.accepted:
                    raise CapabilityUnavailable(capability="notification_delivery")
                queued += 1
        return queued


class RemediationService:
    @staticmethod
    def list_actions(
        tenant_id: object, filters: dict[str, Any] | None = None, ordering: str = "due_date"
    ) -> QuerySet[RemediationAction]:
        tenant = _uuid(tenant_id, "tenant_id")
        qs = RemediationAction.objects.for_tenant(tenant).filter(is_deleted=False)
        filters = filters or {}
        for field in ("risk_id", "control_test_id", "status", "priority", "assigned_to_id"):
            if filters.get(field):
                qs = qs.filter(**{field: filters[field]})
        if filters.get("due_from"):
            qs = qs.filter(due_date__gte=filters["due_from"])
        if filters.get("due_to"):
            qs = qs.filter(due_date__lte=filters["due_to"])
        if ordering.lstrip("-") not in {"due_date", "priority", "created_at", "action_code"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return qs.order_by(ordering, "id")

    @staticmethod
    def get_action(tenant_id: object, action_id: object) -> RemediationAction:
        return _get(RemediationAction, _uuid(tenant_id, "tenant_id"), action_id)

    @classmethod
    def create_action(
        cls, tenant_id: object, actor_id: object, risk_id: object, payload: dict[str, Any]
    ) -> RemediationAction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        data = dict(payload)
        risk = _same_tenant(RiskAssessment, tenant, risk_id, "risk_id")
        test = data.pop("control_test", None)
        if test is None and data.get("control_test_id"):
            test = _same_tenant(ControlTest, tenant, data.pop("control_test_id"), "control_test_id")
        if test and test.control.risk_id != risk.id:
            raise ValidationError({"control_test_id": "The test does not belong to this risk."})
        with transaction.atomic(), tenant_context(tenant):
            value = RemediationAction(
                tenant_id=tenant,
                risk=risk,
                control_test=test,
                created_by_id=actor,
                transition_history=[_history(actor, "create")],
                **data,
            )
            value.action_code = value.action_code.strip().upper()
            _save(value)
            _event(tenant, value, "remediation.created.v1", actor, "create")
            return value

    @classmethod
    def update_action(
        cls, tenant_id: object, actor_id: object, action_id: object, payload: dict[str, Any]
    ) -> RemediationAction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(RemediationAction, tenant, action_id, lock=True)
            if value.status in ("completed", "cancelled"):
                raise ValidationError({"status": "Terminal remediation actions cannot be edited."})
            for key, item in payload.items():
                setattr(value, key, item)
            value.updated_by_id = actor
            _save(value)
            _event(tenant, value, "remediation.updated.v1", actor, "update")
            return value

    @classmethod
    def soft_delete_action(cls, tenant_id: object, actor_id: object, action_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic(), tenant_context(tenant):
            value = _get(RemediationAction, tenant, action_id, lock=True)
            _soft_delete(value, actor)
            _event(tenant, value, "remediation.deleted.v1", actor, "delete")

    @classmethod
    def transition_action(
        cls,
        tenant_id: object,
        actor_id: object,
        action_id: object,
        command: str,
        transition_key: str,
        context: dict[str, Any] | None = None,
    ) -> RemediationAction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        ctx = context or {}
        with transaction.atomic(), tenant_context(tenant):
            value = _get(RemediationAction, tenant, action_id, lock=True)
            value, changed = _transition(value, actor, command, transition_key, transition_remediation, context=ctx)
            if changed:
                if command == "complete":
                    evidence = ControlTestService.validate_evidence(tenant, ctx.get("completion_evidence", []))
                    if not evidence:
                        raise ValidationError({"context": {"completion_evidence": "Completion evidence is required."}})
                    value.completion_evidence, value.completion_date = (
                        evidence,
                        ctx.get("completion_date") or timezone.localdate(),
                    )
                elif command == "cancel":
                    reason = str(ctx.get("cancellation_reason", "")).strip()
                    if not reason:
                        raise ValidationError({"context": {"cancellation_reason": "Cancellation reason is required."}})
                    value.cancellation_reason = reason
                _save(value)
                _event(tenant, value, "remediation.transitioned.v1", actor, command)
            return value

    @classmethod
    def mark_overdue_batch(cls, tenant_id: object, actor_id: object, as_of: date, job_id: object) -> int:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        changed = 0
        for value in RemediationAction.objects.for_tenant(tenant).filter(
            is_deleted=False, status__in=("planned", "in_progress"), due_date__lt=as_of
        ):
            cls.transition_action(tenant, actor, value.id, "mark_overdue", f"job:{job_id}:{value.id}")
            changed += 1
        return changed

    @staticmethod
    def recalculate_risk_state(tenant_id: object, actor_id: object, risk_id: object) -> RiskAssessment:
        del actor_id
        return RiskAssessmentService.get_risk(tenant_id, risk_id)


class ComplianceRiskService:
    """Deprecated v1 construction adapter; new callers use RiskAssessmentService."""

    @staticmethod
    def create_risk(
        tenant_id: object, risk_code: str, risk_name: str, risk_level: str, **kwargs: Any
    ) -> RiskAssessment:
        score_inputs = {
            "negligible": (1, 1),
            "low": (1, 1),
            "medium": (2, 2),
            "high": (4, 4),
            "critical": (5, 5),
        }
        likelihood, impact = score_inputs.get(risk_level, score_inputs["medium"])
        principal = uuid.UUID("00000000-0000-0000-0000-00000000c0de")
        return RiskAssessmentService.create_risk(
            tenant_id,
            principal,
            {
                "risk_code": risk_code,
                "name": risk_name,
                "category": "compliance",
                "description": kwargs.pop("description", "Legacy risk record"),
                "likelihood": likelihood,
                "impact": impact,
                "owner_id": kwargs.pop("owner_id", principal),
                "review_date": kwargs.pop("review_date", timezone.localdate() + timedelta(days=365)),
                **kwargs,
            },
            f"legacy:{risk_code}",
        )

"""Tenant-governed CRM application services.

All writes, state commands, relationship checks, forecasts, and integration
calls enter the canonical tenant context here.  HTTP views are deliberately
thin adapters over this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, QuerySet, Sum
from django.utils import timezone
from rest_framework import status

from src.core.api.results import OperationResult
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import StateMachineError
from src.core.tenancy import tenant_context

from .configuration import (
    DEFAULT_CRM_CONFIGURATION,
    DEFAULT_FEATURE_FLAGS,
    DEFAULT_ROLLOUT,
    deep_merge,
    effective_configuration,
)
from .integrations import (
    CRMIntegrationError,
    ExtensionContext,
    IntegrationUnavailable,
    InvalidIntegrationResponse,
    extension_registry,
    get_revenue_prediction_client,
    get_scoring_client,
)
from .jobs import publish_crm_event
from .models import (
    ISO_4217_CODES,
    RELATED_MODELS,
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    CRMConfiguration,
    CRMConfigurationAudit,
    CRMConfigurationVersion,
    CRMIdempotencyRecord,
    Lead,
    LeadGrade,
    LeadScoreSource,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
)
from .state_machines import apply_lead_command, apply_opportunity_command

logger = logging.getLogger("saraise.crm")

CONFIGURATION_ENVIRONMENTS = frozenset({"development", "test", "staging", "production", "self-hosted", "saas"})


class CRMServiceError(ValidationError):
    """Stable domain failure translated by the governed API boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CRM_VALIDATION_ERROR",
        http_status: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        self.error_code = code
        self.http_status = http_status
        self.public_message = message
        self.detail = dict(detail or {})
        super().__init__(message, code=code)


class StaleVersionError(CRMServiceError):
    def __init__(self, *, expected: int, current: int) -> None:
        super().__init__(
            "The record changed after it was loaded.",
            code="VERSION_CONFLICT",
            http_status=status.HTTP_409_CONFLICT,
            detail={"expected_version": expected, "current_version": current},
        )


@dataclass(frozen=True, slots=True)
class AccountHierarchyNode:
    id: UUID
    name: str
    account_type: str
    children: tuple["AccountHierarchyNode", ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateAccountResult:
    local_matches: tuple[Account, ...]
    external_matches: tuple[Mapping[str, object], ...]
    enrichment_status: str


@dataclass(frozen=True, slots=True)
class CurrencyForecast:
    currency: str
    total_pipeline_value: Decimal
    weighted_pipeline_value: Decimal
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class Forecast:
    currencies: tuple[CurrencyForecast, ...]
    period_days: int


@dataclass(frozen=True, slots=True)
class WinRate:
    win_rate: Decimal
    won_count: int
    lost_count: int
    total_closed: int
    period_days: int


@dataclass(frozen=True, slots=True)
class StageForecast:
    stage: str
    currency: str
    total_value: Decimal
    weighted_value: Decimal
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class RevenuePrediction:
    provider: str
    model: str
    amount: Decimal
    currency: str
    confidence: Decimal | None
    factors: Mapping[str, object]
    as_of: str
    period_days: int


@dataclass(frozen=True, slots=True)
class LeadConversionResult:
    lead: Lead
    account: Account
    contact: Contact | None
    opportunity: Opportunity


_IMMUTABLE_COMMON = {
    "id",
    "tenant_id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "version",
    "is_deleted",
    "deleted_at",
}


def _actor(actor_id: str | UUID | None, tenant_id: UUID | None = None) -> str | None:
    if actor_id is None:
        return None
    value = str(actor_id).strip()
    maximum = int(
        effective_configuration(tenant_id)["field_limits"]["actor_id"]
        if tenant_id is not None
        else DEFAULT_CRM_CONFIGURATION["field_limits"]["actor_id"]
    )
    if not value or len(value) > maximum:
        raise CRMServiceError("Actor identifier is invalid.", code="INVALID_ACTOR")
    return value


def _correlation(correlation_id: str | None = None, tenant_id: UUID | None = None) -> str:
    value = (correlation_id or get_correlation_id() or f"req_{uuid.uuid4().hex[:24]}").strip()
    maximum = int(
        effective_configuration(tenant_id)["field_limits"]["correlation_id"]
        if tenant_id is not None
        else DEFAULT_CRM_CONFIGURATION["field_limits"]["correlation_id"]
    )
    if not value or len(value) > maximum:
        raise CRMServiceError("Correlation identifier is invalid.", code="INVALID_CORRELATION_ID")
    return value


def _validate_version(instance: Any, expected_version: int) -> None:
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
        raise CRMServiceError("Expected version must be a positive integer.", code="INVALID_VERSION")
    if instance.version != expected_version:
        raise StaleVersionError(expected=expected_version, current=instance.version)


def _assign(instance: Any, data: Mapping[str, object], *, forbidden: set[str]) -> list[str]:
    _validate_input_limits(instance.tenant_id, instance._meta.model_name, data)
    unknown = set(data) - {field.name for field in instance._meta.fields}
    if unknown:
        raise CRMServiceError(
            "One or more fields are not supported.",
            code="UNKNOWN_FIELD",
            detail={"fields": sorted(unknown)},
        )
    denied = set(data) & (_IMMUTABLE_COMMON | forbidden)
    if denied:
        raise CRMServiceError(
            "One or more fields are immutable.",
            code="IMMUTABLE_FIELD",
            detail={"fields": sorted(denied)},
        )
    changed: list[str] = []
    for field, value in data.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    return changed


def _validate_input_limits(tenant_id: UUID, entity: str, data: Mapping[str, object]) -> None:
    limits = effective_configuration(tenant_id)["field_limits"]
    fields: dict[str, dict[str, str]] = {
        "lead": {
            "first_name": "lead_name",
            "last_name": "lead_name",
            "email": "lead_email",
            "phone": "lead_phone",
            "company": "lead_email",
            "title": "lead_name",
        },
        "account": {
            "name": "account_name",
            "industry": "account_industry",
            "billing_postal_code": "account_postal_code",
            "billing_country": "account_country",
        },
        "contact": {
            "first_name": "contact_name",
            "last_name": "contact_name",
            "email": "contact_email",
            "phone": "contact_phone",
            "mobile": "contact_phone",
            "title": "contact_name",
            "department": "contact_name",
        },
        "opportunity": {"name": "opportunity_name", "currency": "opportunity_currency"},
        "activity": {
            "subject": "activity_subject",
            "outcome": "activity_outcome",
            "external_id": "activity_external_id",
        },
    }
    for field, limit_name in fields.get(entity, {}).items():
        value = data.get(field)
        if value is not None and len(str(value)) > int(limits[limit_name]):
            raise CRMServiceError(
                f"{field} exceeds the configured length limit.",
                code="CONFIGURED_FIELD_LIMIT",
                detail={"field": field, "maximum": limits[limit_name]},
            )


def _soft_delete(instance: Any, *, actor_id: str | UUID | None, expected_version: int) -> None:
    _validate_version(instance, expected_version)
    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.updated_by = _actor(actor_id, instance.tenant_id)
    instance.save(update_fields=["is_deleted", "deleted_at", "updated_by"])


def _event(
    tenant_id: UUID,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: str | UUID | None,
    correlation_id: str | None,
    payload: Mapping[str, object] | None = None,
) -> None:
    publish_crm_event(
        tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        correlation_id=_correlation(correlation_id, tenant_id),
        payload=payload,
    )


def _log(operation: str, outcome: str, started: float, **context: object) -> None:
    logger.info(
        "crm service operation",
        extra={
            "event": "crm.service.operation",
            "module_name": "crm",
            "operation": operation,
            "outcome": outcome,
            "duration_ms": round((monotonic() - started) * 1000, 3),
            **context,
        },
    )


class CRMConfigurationService:
    """Validated, versioned, tenant-isolated configuration lifecycle."""

    @staticmethod
    def _environment(value: object) -> str:
        environment = str(value or "production").strip().lower()
        if environment not in CONFIGURATION_ENVIRONMENTS:
            raise CRMServiceError(
                "Environment is not allowed.",
                code="INVALID_CONFIGURATION",
                detail={"environment": sorted(CONFIGURATION_ENVIRONMENTS)},
            )
        return environment

    @staticmethod
    def _object(value: object, field: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise CRMServiceError(
                f"{field} must be an object.", code="INVALID_CONFIGURATION", detail={field: "object_required"}
            )
        return dict(value)

    @staticmethod
    def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise CRMServiceError(
                f"{field} must be an integer from {minimum} to {maximum}.",
                code="INVALID_CONFIGURATION",
                detail={field: {"minimum": minimum, "maximum": maximum}},
            )
        return value

    @classmethod
    def _reject_unknown(cls, supplied: Mapping[str, object], template: Mapping[str, object], path: str) -> None:
        unknown = set(supplied) - set(template)
        if unknown:
            raise CRMServiceError(
                "Configuration contains unsupported fields.",
                code="INVALID_CONFIGURATION",
                detail={"unknown_fields": [f"{path}.{field}" for field in sorted(unknown)]},
            )
        for key, value in supplied.items():
            if isinstance(value, dict) and isinstance(template.get(key), dict):
                cls._reject_unknown(value, template[key], f"{path}.{key}")

    @classmethod
    def validate_document(cls, value: object) -> dict[str, Any]:
        """Return a complete safe document or reject the entire mutation."""

        supplied = cls._object(value, "document")
        cls._reject_unknown(supplied, DEFAULT_CRM_CONFIGURATION, "document")
        document = deep_merge(DEFAULT_CRM_CONFIGURATION, supplied)
        limits = cls._object(document["field_limits"], "field_limits")
        physical_limits = DEFAULT_CRM_CONFIGURATION["field_limits"]
        for name, maximum in physical_limits.items():
            configured = limits.get(name)
            if not isinstance(maximum, int):
                continue
            cls._integer(configured, f"field_limits.{name}", 1, maximum)
        if limits["phone_min_digits"] > limits["phone_max_digits"]:
            raise CRMServiceError(
                "Minimum phone digits cannot exceed maximum phone digits.", code="INVALID_CONFIGURATION"
            )

        lead = cls._object(document["lead"], "lead")
        score_min = cls._integer(lead["score_min"], "lead.score_min", 0, 100)
        score_max = cls._integer(lead["score_max"], "lead.score_max", score_min, 100)
        cls._integer(lead["default_score"], "lead.default_score", score_min, score_max)
        if (
            lead.get("default_grade") not in LeadGrade.values
            or lead.get("default_score_source") not in LeadScoreSource.values
            or lead.get("default_status") not in LeadStatus.values
        ):
            raise CRMServiceError("Lead defaults contain an unsupported value.", code="INVALID_CONFIGURATION")
        cls._integer(lead["qualification_threshold"], "lead.qualification_threshold", score_min, score_max)
        thresholds = cls._object(lead["grade_thresholds"], "lead.grade_thresholds")
        if set(thresholds) != {"A", "B", "C", "D"}:
            raise CRMServiceError("Grade thresholds must define A, B, C, and D.", code="INVALID_CONFIGURATION")
        ordered = [
            cls._integer(thresholds[grade], f"lead.grade_thresholds.{grade}", score_min, score_max) for grade in "ABCD"
        ]
        if not (ordered[0] > ordered[1] > ordered[2] > ordered[3] == score_min):
            raise CRMServiceError(
                "Grade thresholds must strictly descend to the score minimum.", code="INVALID_CONFIGURATION"
            )
        configured_default_grade = next(
            grade for grade in "ABCD" if int(lead["default_score"]) >= int(thresholds[grade])
        )
        if lead["default_grade"] != configured_default_grade:
            raise CRMServiceError(
                "Default lead grade must match the configured default score and thresholds.",
                code="INVALID_CONFIGURATION",
            )
        for section in ("field_score_weights", "source_score_weights"):
            weights = cls._object(lead[section], f"lead.{section}")
            if not weights or any(
                isinstance(points, bool) or not isinstance(points, int) or not 0 <= points <= score_max
                for points in weights.values()
            ):
                raise CRMServiceError(f"lead.{section} contains an invalid weight.", code="INVALID_CONFIGURATION")
        cls._validate_transition_policy(
            lead,
            section="lead",
            states=set(LeadStatus.values),
            required_terminal_states={LeadStatus.CONVERTED, LeadStatus.LOST},
            template=DEFAULT_CRM_CONFIGURATION["lead"]["transitions"],
        )

        account = cls._object(document["account"], "account")
        allowed_types = account.get("allowed_types")
        if (
            not isinstance(allowed_types, list)
            or not allowed_types
            or any(value not in AccountType.values for value in allowed_types)
        ):
            raise CRMServiceError("Account types contain an unsupported value.", code="INVALID_CONFIGURATION")
        if account.get("default_type") not in allowed_types:
            raise CRMServiceError("Default account type must be allowed.", code="INVALID_CONFIGURATION")
        cls._integer(account["hierarchy_max_depth"], "account.hierarchy_max_depth", 1, 20)

        contact = cls._object(document["contact"], "contact")
        engagement_min = cls._integer(contact["engagement_score_min"], "contact.engagement_score_min", 0, 100)
        engagement_max = cls._integer(
            contact["engagement_score_max"], "contact.engagement_score_max", engagement_min, 100
        )
        cls._integer(
            contact["default_engagement_score"], "contact.default_engagement_score", engagement_min, engagement_max
        )
        cls._integer(contact["engagement_lookback_days"], "contact.engagement_lookback_days", 1, 3650)
        cls._integer(contact["engagement_points_per_interaction"], "contact.engagement_points_per_interaction", 1, 100)
        if not isinstance(contact.get("enforce_account_email_domain"), bool):
            raise CRMServiceError("Contact domain enforcement must be boolean.", code="INVALID_CONFIGURATION")

        opportunity = cls._object(document["opportunity"], "opportunity")
        probability_min = cls._integer(opportunity["probability_min"], "opportunity.probability_min", 0, 100)
        probability_max = cls._integer(
            opportunity["probability_max"], "opportunity.probability_max", probability_min, 100
        )
        cls._integer(
            opportunity["default_probability"], "opportunity.default_probability", probability_min, probability_max
        )
        stages = opportunity.get("stages")
        if not isinstance(stages, list) or {item.get("name") for item in stages if isinstance(item, dict)} != set(
            OpportunityStage.values
        ):
            raise CRMServiceError(
                "Opportunity stages must define every supported stage once.", code="INVALID_CONFIGURATION"
            )
        if len(stages) != len(OpportunityStage.values):
            raise CRMServiceError("Opportunity stages must not contain duplicates.", code="INVALID_CONFIGURATION")
        semantic_tokens = {"muted", "info", "warning", "accent", "positive", "success", "danger"}
        for item in stages:
            if not isinstance(item, dict) or item.get("semantic_token") not in semantic_tokens:
                raise CRMServiceError("Opportunity stage semantic token is invalid.", code="INVALID_CONFIGURATION")
            cls._integer(
                item.get("probability"), f"opportunity.stages.{item.get('name')}", probability_min, probability_max
            )
        if opportunity.get("default_stage") not in OpportunityStage.values:
            raise CRMServiceError("Default opportunity stage is invalid.", code="INVALID_CONFIGURATION")
        if opportunity.get("default_status") not in OpportunityStatus.values:
            raise CRMServiceError("Default opportunity status is invalid.", code="INVALID_CONFIGURATION")
        cls._validate_transition_policy(
            opportunity,
            section="opportunity",
            states=set(OpportunityStage.values),
            required_terminal_states={OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST},
            template=DEFAULT_CRM_CONFIGURATION["opportunity"]["transitions"],
        )
        currency = opportunity.get("default_currency")
        if not isinstance(currency, str) or currency not in ISO_4217_CODES:
            raise CRMServiceError("Default currency must be an allowed ISO-4217 code.", code="INVALID_CONFIGURATION")
        try:
            minimum_amount = Decimal(str(opportunity.get("minimum_amount")))
        except (ValueError, TypeError) as exc:
            raise CRMServiceError("Minimum opportunity amount is invalid.", code="INVALID_CONFIGURATION") from exc
        if minimum_amount <= 0:
            raise CRMServiceError("Minimum opportunity amount must be positive.", code="INVALID_CONFIGURATION")

        activity = cls._object(document["activity"], "activity")
        if (
            activity.get("default_type") not in ActivityType.values
            or activity.get("default_related_type") not in RelatedToType.values
        ):
            raise CRMServiceError("Activity defaults are invalid.", code="INVALID_CONFIGURATION")
        if not isinstance(activity.get("require_future_task_due_date"), bool):
            raise CRMServiceError("Task due-date policy must be boolean.", code="INVALID_CONFIGURATION")

        hierarchy = cls._object(document["hierarchy"], "hierarchy")
        cls._integer(hierarchy["max_nodes"], "hierarchy.max_nodes", 1, 5000)
        cls._integer(hierarchy["max_children"], "hierarchy.max_children", 1, 1000)
        cls._integer(hierarchy["page_size"], "hierarchy.page_size", 1, hierarchy["max_nodes"])
        forecast = cls._object(document["forecast"], "forecast")
        period_min = cls._integer(forecast["minimum_period_days"], "forecast.minimum_period_days", 1, 3650)
        period_max = cls._integer(forecast["maximum_period_days"], "forecast.maximum_period_days", period_min, 3650)
        cls._integer(forecast["default_period_days"], "forecast.default_period_days", period_min, period_max)
        jobs = cls._object(document["jobs"], "jobs")
        stale_min = cls._integer(jobs["stale_deal_min_days"], "jobs.stale_deal_min_days", 1, 3650)
        stale_max = cls._integer(jobs["stale_deal_max_days"], "jobs.stale_deal_max_days", stale_min, 3650)
        cls._integer(jobs["stale_deal_days"], "jobs.stale_deal_days", stale_min, stale_max)
        cls._integer(jobs["iterator_chunk_size"], "jobs.iterator_chunk_size", 1, 5000)
        providers = cls._object(document["providers"], "providers")
        cls._integer(providers["maximum_evidence_factors"], "providers.maximum_evidence_factors", 1, 500)
        priority_min = cls._integer(providers["extension_priority_min"], "providers.extension_priority_min", 0, 10000)
        priority_max = cls._integer(
            providers["extension_priority_max"], "providers.extension_priority_max", priority_min, 10000
        )
        cls._integer(
            providers["extension_priority_default"],
            "providers.extension_priority_default",
            priority_min,
            priority_max,
        )
        if providers["extension_schema_version"] != "1.0":
            raise CRMServiceError("Provider schema version is unsupported.", code="INVALID_CONFIGURATION")
        cls._integer(providers["retry_attempts"], "providers.retry_attempts", 1, 8)
        try:
            backoff_base = Decimal(str(providers["backoff_base_seconds"]))
            backoff_max = Decimal(str(providers["backoff_max_seconds"]))
            backoff_jitter = Decimal(str(providers["backoff_jitter_seconds"]))
        except (TypeError, ValueError) as exc:
            raise CRMServiceError(
                "Provider backoff values must be decimal strings.", code="INVALID_CONFIGURATION"
            ) from exc
        if not Decimal("0") <= backoff_base <= backoff_max <= Decimal("30"):
            raise CRMServiceError("Provider backoff bounds are invalid.", code="INVALID_CONFIGURATION")
        if not Decimal("0") <= backoff_jitter <= backoff_max:
            raise CRMServiceError("Provider backoff jitter is invalid.", code="INVALID_CONFIGURATION")
        pagination = cls._object(document["pagination"], "pagination")
        page_max = cls._integer(pagination["maximum_page_size"], "pagination.maximum_page_size", 1, 1000)
        cls._integer(pagination["default_page_size"], "pagination.default_page_size", 1, page_max)
        ui = cls._object(document["ui"], "ui")
        cls._integer(
            ui["hierarchy_auto_expand_levels"], "ui.hierarchy_auto_expand_levels", 0, account["hierarchy_max_depth"]
        )
        cls._integer(ui["hierarchy_indentation_pixels"], "ui.hierarchy_indentation_pixels", 8, 64)
        cls._integer(ui["minimum_pipeline_bar_percent"], "ui.minimum_pipeline_bar_percent", 0, 100)
        cls._integer(ui["saved_page_size"], "ui.saved_page_size", 1, page_max)
        cls._integer(ui["dashboard_forecast_period_days"], "ui.dashboard_forecast_period_days", period_min, period_max)
        cls._integer(ui["stale_deal_page_size"], "ui.stale_deal_page_size", 1, page_max)
        cls._integer(ui["pipeline_fetch_limit"], "ui.pipeline_fetch_limit", 1, page_max)
        if not isinstance(ui.get("prediction_retry_enabled"), bool):
            raise CRMServiceError("Prediction retry policy must be boolean.", code="INVALID_CONFIGURATION")
        api = cls._object(document["api"], "api")
        cls._integer(api["quota_cost"], "api.quota_cost", 1, 1000)
        health = cls._object(document["health"], "health")
        cls._integer(health["cache_timeout_seconds"], "health.cache_timeout_seconds", 1, 120)
        conversion = cls._object(document["conversion"], "conversion")
        if not isinstance(conversion["create_account_by_default"], bool) or not isinstance(
            conversion["use_current_version"], bool
        ):
            raise CRMServiceError("Conversion policies must be boolean.", code="INVALID_CONFIGURATION")
        cls._integer(conversion["close_date_offset_days"], "conversion.close_date_offset_days", 0, period_max)
        prefix = conversion["transition_key_prefix"]
        if not isinstance(prefix, str) or not prefix.strip() or len(prefix) > 64:
            raise CRMServiceError("Conversion transition-key prefix is invalid.", code="INVALID_CONFIGURATION")
        return document

    @classmethod
    def _validate_transition_policy(
        cls,
        configuration: Mapping[str, object],
        *,
        section: str,
        states: set[str],
        required_terminal_states: set[str],
        template: Mapping[str, object],
    ) -> None:
        """Validate a tenant policy that may narrow, but never expand, core transitions."""

        terminal_states = configuration.get("terminal_states")
        if (
            not isinstance(terminal_states, list)
            or not required_terminal_states.issubset(set(terminal_states))
            or any(state not in states for state in terminal_states)
        ):
            raise CRMServiceError(
                f"{section}.terminal_states must contain the protected terminal states.",
                code="INVALID_CONFIGURATION",
            )
        transitions = cls._object(configuration.get("transitions"), f"{section}.transitions")
        if set(transitions) != set(template):
            raise CRMServiceError(
                f"{section}.transitions must define every supported command.",
                code="INVALID_CONFIGURATION",
            )
        for command, configured_value in transitions.items():
            configured = cls._object(configured_value, f"{section}.transitions.{command}")
            expected = cls._object(template[command], f"{section}.transitions.{command}")
            if set(configured) != {"from", "to"} or configured.get("to") != expected["to"]:
                raise CRMServiceError(
                    f"{section}.transitions.{command} has an unsupported target.",
                    code="INVALID_CONFIGURATION",
                )
            sources = configured.get("from")
            expected_sources = expected["from"]
            if (
                not isinstance(sources, list)
                or len(sources) != len(set(sources))
                or any(source not in expected_sources for source in sources)
            ):
                raise CRMServiceError(
                    f"{section}.transitions.{command} contains an unsupported source.",
                    code="INVALID_CONFIGURATION",
                )

    @classmethod
    def validate_feature_flags(cls, value: object) -> dict[str, bool]:
        flags = deep_merge(DEFAULT_FEATURE_FLAGS, cls._object(value, "feature_flags"))
        if set(flags) != set(DEFAULT_FEATURE_FLAGS) or any(not isinstance(item, bool) for item in flags.values()):
            raise CRMServiceError("Feature flags must use the supported boolean keys.", code="INVALID_CONFIGURATION")
        return flags

    @classmethod
    def validate_rollout(cls, value: object) -> dict[str, Any]:
        rollout = deep_merge(DEFAULT_ROLLOUT, cls._object(value, "rollout"))
        if set(rollout) != set(DEFAULT_ROLLOUT) or not isinstance(rollout["enabled"], bool):
            raise CRMServiceError("Rollout contains unsupported fields.", code="INVALID_CONFIGURATION")
        cls._integer(rollout["percentage"], "rollout.percentage", 0, 100)
        for field in ("roles", "cohorts"):
            values = rollout[field]
            if (
                not isinstance(values, list)
                or len(values) > 100
                or any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in values)
            ):
                raise CRMServiceError(f"Rollout {field} are invalid.", code="INVALID_CONFIGURATION")
            rollout[field] = sorted(set(value.strip() for value in values))
        return rollout

    @staticmethod
    def _snapshot(row: CRMConfiguration | None, *, environment: str) -> dict[str, Any]:
        return {
            "id": str(row.id) if row else None,
            "environment": environment,
            "version": row.version if row else 0,
            "document": deep_merge(DEFAULT_CRM_CONFIGURATION, row.document if row else {}),
            "feature_flags": deep_merge(DEFAULT_FEATURE_FLAGS, row.feature_flags if row else {}),
            "rollout": deep_merge(DEFAULT_ROLLOUT, row.rollout if row else {}),
            "updated_at": row.updated_at.isoformat() if row else None,
        }

    @classmethod
    def get(cls, tenant_id: UUID, *, environment: str = "production") -> dict[str, Any]:
        environment = cls._environment(environment)
        with tenant_context(tenant_id):
            row = CRMConfiguration.objects.filter(tenant_id=tenant_id, environment=environment).first()
        return cls._snapshot(row, environment=environment)

    @classmethod
    def preview(cls, tenant_id: UUID, *, payload: Mapping[str, object]) -> dict[str, Any]:
        environment = cls._environment(payload.get("environment"))
        current = cls.get(tenant_id, environment=environment)
        document = cls.validate_document(
            deep_merge(current["document"], cls._object(payload.get("document", {}), "document"))
        )
        flags = cls.validate_feature_flags(
            deep_merge(current["feature_flags"], cls._object(payload.get("feature_flags", {}), "feature_flags"))
        )
        rollout = cls.validate_rollout(
            deep_merge(current["rollout"], cls._object(payload.get("rollout", {}), "rollout"))
        )
        effective = {**current, "document": document, "feature_flags": flags, "rollout": rollout}
        changed = sorted(key for key in ("document", "feature_flags", "rollout") if current[key] != effective[key])
        return {"valid": True, "diff": changed, "errors": {}, "effective": effective}

    @classmethod
    def write(
        cls,
        tenant_id: UUID,
        *,
        payload: Mapping[str, object],
        actor_id: str | UUID,
        correlation_id: str | None,
        change_type: str = "update",
        rollback_of_version: int | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        environment = cls._environment(payload.get("environment"))
        actor = _actor(actor_id, tenant_id)
        if actor is None:
            raise CRMServiceError("Configuration actor is required.", code="INVALID_ACTOR")
        correlation = _correlation(correlation_id)
        with tenant_context(tenant_id), transaction.atomic():
            row = (
                CRMConfiguration.objects.select_for_update()
                .filter(tenant_id=tenant_id, environment=environment)
                .first()
            )
            prior = cls._snapshot(row, environment=environment)
            if expected_version is not None and prior["version"] != expected_version:
                raise CRMServiceError(
                    "Configuration version is stale.",
                    code="STALE_CONFIGURATION_VERSION",
                    http_status=status.HTTP_409_CONFLICT,
                    detail={"expected_version": expected_version, "current_version": prior["version"]},
                )
            document = cls.validate_document(
                deep_merge(prior["document"], cls._object(payload.get("document", {}), "document"))
            )
            flags = cls.validate_feature_flags(
                deep_merge(prior["feature_flags"], cls._object(payload.get("feature_flags", {}), "feature_flags"))
            )
            rollout = cls.validate_rollout(
                deep_merge(prior["rollout"], cls._object(payload.get("rollout", {}), "rollout"))
            )
            if row is None:
                row = CRMConfiguration(
                    tenant_id=tenant_id,
                    environment=environment,
                    document=document,
                    feature_flags=flags,
                    rollout=rollout,
                    updated_by=actor,
                    version=1,
                )
            else:
                row.document = document
                row.feature_flags = flags
                row.rollout = rollout
                row.updated_by = actor
                row.version += 1
            row.full_clean()
            row.save()
            current = cls._snapshot(row, environment=environment)
            changed = sorted(key for key in ("document", "feature_flags", "rollout") if prior[key] != current[key])
            CRMConfigurationVersion.objects.create(
                tenant_id=tenant_id,
                environment=environment,
                version=row.version,
                actor_id=actor,
                correlation_id=correlation,
                document=document,
                feature_flags=flags,
                rollout=rollout,
                change_type=change_type,
                rollback_of_version=rollback_of_version,
            )
            CRMConfigurationAudit.objects.create(
                tenant_id=tenant_id,
                environment=environment,
                version=row.version,
                actor_id=actor,
                correlation_id=correlation,
                prior_value=prior,
                new_value=current,
                changed_fields=changed,
                action=change_type,
            )
        return current

    @classmethod
    def versions(cls, tenant_id: UUID, *, environment: str = "production") -> list[dict[str, Any]]:
        environment = cls._environment(environment)
        with tenant_context(tenant_id):
            rows = CRMConfigurationVersion.objects.filter(tenant_id=tenant_id, environment=environment).order_by(
                "-version"
            )
            return [
                {
                    "id": str(row.id),
                    "environment": row.environment,
                    "version": row.version,
                    "document": row.document,
                    "feature_flags": row.feature_flags,
                    "rollout": row.rollout,
                    "actor_id": row.actor_id,
                    "correlation_id": row.correlation_id,
                    "change_type": row.change_type,
                    "rollback_of_version": row.rollback_of_version,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    @classmethod
    def rollback(
        cls,
        tenant_id: UUID,
        *,
        environment: str,
        version: int,
        actor_id: str | UUID,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        environment = cls._environment(environment)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise CRMServiceError("Rollback version must be positive.", code="INVALID_CONFIGURATION")
        with tenant_context(tenant_id):
            target = CRMConfigurationVersion.objects.filter(
                tenant_id=tenant_id, environment=environment, version=version
            ).first()
        if target is None:
            raise CRMServiceError(
                "Configuration version was not found.", code="CONFIGURATION_VERSION_NOT_FOUND", http_status=404
            )
        return cls.write(
            tenant_id,
            payload={
                "environment": environment,
                "document": target.document,
                "feature_flags": target.feature_flags,
                "rollout": target.rollout,
            },
            actor_id=actor_id,
            correlation_id=correlation_id,
            change_type="rollback",
            rollback_of_version=version,
        )

    @classmethod
    def export(cls, tenant_id: UUID, *, environment: str = "production") -> dict[str, Any]:
        return {"schema_version": 1, "module": "crm", "configuration": cls.get(tenant_id, environment=environment)}

    @classmethod
    def import_document(
        cls,
        tenant_id: UUID,
        *,
        exported: Mapping[str, object],
        actor_id: str | UUID,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        if exported.get("schema_version") != 1 or exported.get("module") != "crm":
            raise CRMServiceError("Configuration document schema is unsupported.", code="INVALID_CONFIGURATION")
        configuration = cls._object(exported.get("configuration"), "configuration")
        return cls.write(
            tenant_id,
            payload=configuration,
            actor_id=actor_id,
            correlation_id=correlation_id,
            change_type="import",
        )


class CRMIdempotencyService:
    """Persist and replay tenant request evidence without cross-tenant keys."""

    @staticmethod
    def begin(
        tenant_id: UUID,
        *,
        key: str,
        method: str,
        path: str,
        payload: object,
    ) -> CRMIdempotencyRecord:
        maximum = int(effective_configuration(tenant_id)["field_limits"]["async_idempotency_key"])
        normalized = key.strip()
        if not normalized or len(normalized) > maximum:
            raise CRMServiceError(
                "A bounded Idempotency-Key is required.", code="IDEMPOTENCY_KEY_REQUIRED", http_status=400
            )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        fingerprint = hashlib.sha256(
            method.upper().encode("ascii") + b"\0" + path.encode("utf-8") + b"\0" + encoded
        ).hexdigest()
        with tenant_context(tenant_id), transaction.atomic():
            row, _ = CRMIdempotencyRecord.objects.select_for_update().get_or_create(
                tenant_id=tenant_id,
                idempotency_key=normalized,
                defaults={
                    "method": method.upper(),
                    "path": path,
                    "request_fingerprint": fingerprint,
                },
            )
        if row.request_fingerprint != fingerprint:
            raise CRMServiceError(
                "Idempotency-Key was already used for a different request.",
                code="IDEMPOTENCY_CONFLICT",
                http_status=409,
            )
        return row

    @staticmethod
    def complete(tenant_id: UUID, *, record_id: UUID, response_status: int, response_body: object) -> None:
        if not 100 <= response_status <= 599:
            raise CRMServiceError("Response status is invalid.", code="INVALID_IDEMPOTENCY_RESPONSE")
        canonical_body = json.loads(json.dumps(response_body, cls=DjangoJSONEncoder))
        with tenant_context(tenant_id), transaction.atomic():
            CRMIdempotencyRecord.objects.filter(tenant_id=tenant_id, id=record_id, completed=False).update(
                response_status=response_status, response_body=canonical_body, completed=True
            )


class LeadService:
    """Lead lifecycle, assignment, verified scoring, and conversion."""

    @staticmethod
    def prepare_legacy_conversion(tenant_id: UUID, lead: Lead, data: Mapping[str, object]) -> dict[str, object]:
        """Apply the configured compatibility contract outside the transport view."""

        configuration = effective_configuration(tenant_id)
        conversion = configuration["conversion"]
        payload = dict(data)
        if conversion["use_current_version"]:
            payload.setdefault("expected_version", lead.version)
        payload.setdefault("transition_key", f"{conversion['transition_key_prefix']}:{lead.id}")
        payload.setdefault("create_new_account", conversion["create_account_by_default"])
        payload.setdefault("currency", configuration["opportunity"]["default_currency"])
        payload.setdefault(
            "close_date",
            (timezone.localdate() + timedelta(days=int(conversion["close_date_offset_days"]))).isoformat(),
        )
        return payload

    @staticmethod
    def convert_legacy(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        validated_data: Mapping[str, object],
        actor_id: str | UUID | None,
    ) -> Opportunity:
        values = dict(validated_data)
        for field in ("account_id", "create_new_account", "expected_version", "transition_key"):
            values.pop(field, None)
        result = IntegrationService.convert_lead_to_opportunity(lead_id, tenant_id, values, actor_id)
        return result["opportunity"]  # type: ignore[return-value]

    @staticmethod
    def _rule_score(tenant_id: UUID, data: Mapping[str, object]) -> tuple[int, str, dict[str, object]]:
        configuration = effective_configuration(tenant_id)["lead"]
        factors: dict[str, int] = {}
        for field, points in configuration["field_score_weights"].items():
            if data.get(field):
                factors[f"has_{field}"] = int(points)
        source_points = configuration["source_score_weights"]
        source = str(data.get("source") or "").lower()
        if source in source_points:
            factors["source"] = source_points[source]
        score = min(int(configuration["default_score"]) + sum(factors.values()), int(configuration["score_max"]))
        thresholds = configuration["grade_thresholds"]
        grade = next(grade for grade in "ABCD" if score >= int(thresholds[grade]))
        return score, grade, {"method": "rules_v1", "factors": factors, "evidence_count": len(factors)}

    @classmethod
    def create_lead(
        cls,
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
    ) -> Lead:
        started = monotonic()
        configuration = effective_configuration(tenant_id)["lead"]
        actor = _actor(actor_id if actor_id is not None else created_by, tenant_id)
        correlation = _correlation(correlation_id, tenant_id)
        forbidden = set(data) & (
            _IMMUTABLE_COMMON
            | {
                "status",
                "score",
                "grade",
                "score_source",
                "score_explanation",
                "transition_history",
                "converted_at",
                "converted_to_opportunity_id",
            }
        )
        if forbidden:
            raise CRMServiceError(
                "Server-owned lead fields cannot be supplied.",
                code="IMMUTABLE_FIELD",
                detail={"fields": sorted(forbidden)},
            )
        _validate_input_limits(tenant_id, "lead", data)
        score, grade, explanation = cls._rule_score(tenant_id, data)
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead(
                tenant_id=tenant_id,
                created_by=actor,
                updated_by=actor,
                score=score,
                grade=grade,
                score_source=configuration["default_score_source"],
                status=configuration["default_status"],
                score_explanation=explanation,
                **dict(data),
            )
            lead.save()
            _event(
                tenant_id,
                event_type="crm.lead.created",
                aggregate_type="lead",
                aggregate_id=lead.id,
                actor_id=actor,
                correlation_id=correlation,
                payload={
                    "source": lead.source,
                    "score": lead.score,
                    "grade": lead.grade,
                    "score_source": lead.score_source,
                    "version": lead.version,
                },
            )
        _log(
            "create_lead",
            "succeeded",
            started,
            tenant_id=str(tenant_id),
            aggregate_id=str(lead.id),
            correlation_id=correlation,
        )
        return lead

    @staticmethod
    def update_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Lead:
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(lead, expected_version)
            changed = _assign(
                lead,
                data,
                forbidden={
                    "status",
                    "score",
                    "grade",
                    "score_source",
                    "score_explanation",
                    "transition_history",
                    "converted_at",
                    "converted_to_opportunity_id",
                },
            )
            if changed:
                lead.updated_by = _actor(actor_id, tenant_id)
                if set(changed) & {"company", "email", "phone", "title", "source", "metadata"}:
                    lead.score, lead.grade, lead.score_explanation = LeadService._rule_score(
                        tenant_id, {field.name: getattr(lead, field.name) for field in lead._meta.fields}
                    )
                    lead.score_source = LeadScoreSource.RULES
                    changed += ["score", "grade", "score_explanation", "score_source"]
                lead.save(update_fields=set(changed) | {"updated_by"})
                _event(
                    tenant_id,
                    event_type="crm.lead.updated",
                    aggregate_type="lead",
                    aggregate_id=lead.id,
                    actor_id=actor_id,
                    correlation_id=None,
                    payload={"changed_fields": sorted(set(changed)), "version": lead.version},
                )
            return lead

    @staticmethod
    def delete_lead(tenant_id: UUID, *, lead_id: UUID, expected_version: int, actor_id: str | UUID | None) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _soft_delete(lead, actor_id=actor_id, expected_version=expected_version)
            _event(
                tenant_id,
                event_type="crm.lead.deleted",
                aggregate_type="lead",
                aggregate_id=lead.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={"version": lead.version},
            )

    @staticmethod
    def transition_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        command: str,
        transition_key: str,
        context: Mapping[str, object],
        actor_id: str | UUID | None,
        expected_version: int | None = None,
    ) -> Lead:
        with tenant_context(tenant_id), transaction.atomic():
            before = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            try:
                lead = apply_lead_command(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    command=command,
                    transition_key=transition_key,
                    context=context,
                    actor_id=_actor(actor_id, tenant_id),
                    correlation_id=_correlation(),
                    expected_version=expected_version,
                )
            except StateMachineError as exc:
                raise CRMServiceError(
                    str(exc), code="ILLEGAL_TRANSITION", http_status=status.HTTP_409_CONFLICT
                ) from exc
            _event(
                tenant_id,
                event_type="crm.lead.status_changed",
                aggregate_type="lead",
                aggregate_id=lead.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={
                    "from_status": before.status,
                    "to_status": lead.status,
                    "command": command,
                    "transition_key": transition_key,
                    "version": lead.version,
                },
            )
            return lead

    @staticmethod
    def score_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
    ) -> OperationResult[Lead]:
        correlation = _correlation(correlation_id)
        with tenant_context(tenant_id):
            lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            payload = {
                "lead_id": str(lead.id),
                "company_present": bool(lead.company),
                "email_present": bool(lead.email),
                "phone_present": bool(lead.phone),
                "title_present": bool(lead.title),
                "source": lead.source,
                "current_score": lead.score,
            }
            try:
                client = get_scoring_client()
                if hasattr(client, "tenant_id"):
                    client.tenant_id = tenant_id
                result = client.score_lead(payload, correlation_id=correlation)
            except IntegrationUnavailable as exc:
                return OperationResult.unavailable(
                    capability="crm.lead_scoring",
                    message="Lead scoring provider is unavailable.",
                    detail={"code": exc.code},
                )
            except (InvalidIntegrationResponse, CRMIntegrationError) as exc:
                return OperationResult.failed(
                    code=exc.code,
                    message="Lead scoring could not be verified.",
                    detail={"provider_status": "invalid"},
                    http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            with transaction.atomic():
                lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
                lead.score = result.score
                lead.grade = result.grade
                lead.score_source = LeadScoreSource.PROVIDER
                lead.score_explanation = {
                    "provider": result.provider,
                    "model": result.model,
                    "factors": dict(result.factors),
                    "provider_request_id": result.provider_request_id,
                }
                lead.updated_by = _actor(actor_id, tenant_id)
                lead.save(update_fields=["score", "grade", "score_source", "score_explanation", "updated_by"])
                _event(
                    tenant_id,
                    event_type="crm.lead.scored",
                    aggregate_type="lead",
                    aggregate_id=lead.id,
                    actor_id=actor_id,
                    correlation_id=correlation,
                    payload={
                        "score": lead.score,
                        "grade": lead.grade,
                        "score_source": lead.score_source,
                        "provider": result.provider,
                        "model": result.model,
                        "evidence_factors": sorted(result.factors),
                        "version": lead.version,
                    },
                )
            return OperationResult.succeeded(
                lead,
                evidence={
                    "persisted_version": lead.version,
                    "provider_request_id": result.provider_request_id or correlation,
                },
                provider=result.provider,
            )

    @staticmethod
    def assign_lead(
        tenant_id: UUID, *, lead_id: UUID, owner_id: UUID, expected_version: int, actor_id: str | UUID | None
    ) -> Lead:
        if not isinstance(owner_id, UUID):
            try:
                owner_id = UUID(str(owner_id))
            except (TypeError, ValueError) as exc:
                raise CRMServiceError("Owner must be a valid assignable UUID.", code="INVALID_OWNER") from exc
        return LeadService.update_lead(
            tenant_id,
            lead_id=lead_id,
            data={"owner_id": owner_id},
            expected_version=expected_version,
            actor_id=actor_id,
        )

    @staticmethod
    def convert_lead(
        tenant_id: UUID,
        *,
        lead_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        transition_key: str,
        actor_id: str | UUID | None,
        correlation_id: str | None,
    ) -> LeadConversionResult:
        configuration = effective_configuration(tenant_id)
        correlation = _correlation(correlation_id, tenant_id)
        amount = Decimal(str(data.get("amount", "0")))
        if amount < Decimal(str(configuration["opportunity"]["minimum_amount"])):
            raise CRMServiceError("Opportunity amount must be positive.", code="INVALID_AMOUNT")
        with tenant_context(tenant_id), transaction.atomic():
            lead = Lead.objects.select_for_update().get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(lead, expected_version)
            if lead.status != LeadStatus.QUALIFIED:
                raise CRMServiceError(
                    "Only qualified leads can be converted.",
                    code="ILLEGAL_TRANSITION",
                    http_status=status.HTTP_409_CONFLICT,
                )
            account_id = data.get("account_id")
            create_new = data.get("create_new_account") is True
            if bool(account_id) == create_new:
                raise CRMServiceError(
                    "Choose exactly one existing-account or new-account decision.", code="CONVERSION_DECISION_REQUIRED"
                )
            if account_id:
                account = Account.objects.get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            else:
                if not lead.company.strip():
                    raise CRMServiceError("A company is required to create an account.", code="ACCOUNT_REQUIRED")
                existing = Account.objects.filter(
                    tenant_id=tenant_id, is_deleted=False, name__iexact=lead.company.strip()
                ).first()
                account = existing or AccountService.create_account(
                    tenant_id,
                    data={"name": lead.company, "owner_id": lead.owner_id},
                    actor_id=actor_id,
                    correlation_id=correlation,
                )
            contact = None
            if lead.email:
                contact = Contact.objects.filter(
                    tenant_id=tenant_id, account_id=account.id, email__iexact=lead.email, is_deleted=False
                ).first()
            if contact is None and (lead.email or lead.first_name or lead.last_name):
                contact = ContactService.create_contact(
                    tenant_id,
                    data={
                        "account_id": account.id,
                        "first_name": lead.first_name,
                        "last_name": lead.last_name,
                        "email": lead.email,
                        "phone": lead.phone,
                        "title": lead.title,
                        "owner_id": lead.owner_id,
                    },
                    actor_id=actor_id,
                    correlation_id=correlation,
                )
            stage_probabilities = {item["name"]: item["probability"] for item in configuration["opportunity"]["stages"]}
            opportunity = OpportunityService.create_opportunity(
                tenant_id,
                data={
                    "account_id": account.id,
                    "primary_contact_id": contact.id if contact else None,
                    "name": str(data.get("name") or f"{account.name} opportunity"),
                    "amount": amount,
                    "currency": str(data.get("currency") or configuration["opportunity"]["default_currency"]),
                    "stage": OpportunityStage.QUALIFICATION,
                    "probability": stage_probabilities[OpportunityStage.QUALIFICATION],
                    "close_date": data.get("close_date"),
                    "owner_id": lead.owner_id,
                },
                actor_id=actor_id,
                correlation_id=correlation,
            )
            lead = apply_lead_command(
                tenant_id,
                lead_id=lead.id,
                command="convert",
                transition_key=transition_key,
                context={
                    "account_id": account.id,
                    "opportunity_id": opportunity.id,
                    "opportunity_amount": amount,
                },
                actor_id=_actor(actor_id, tenant_id),
                correlation_id=correlation,
                expected_version=lead.version,
                opportunity_id=opportunity.id,
            )
            _event(
                tenant_id,
                event_type="crm.lead.converted",
                aggregate_type="lead",
                aggregate_id=lead.id,
                actor_id=actor_id,
                correlation_id=correlation,
                payload={
                    "account_id": account.id,
                    "contact_id": contact.id if contact else None,
                    "opportunity_id": opportunity.id,
                    "amount": amount,
                    "currency": opportunity.currency,
                    "transition_key": transition_key,
                    "conversion_decision": "existing" if account_id else "created",
                    "version": lead.version,
                },
            )
            return LeadConversionResult(lead, account, contact, opportunity)


class AccountService:
    @staticmethod
    def create_account(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
    ) -> Account:
        configuration = effective_configuration(tenant_id)["account"]
        actor = _actor(actor_id if actor_id is not None else created_by, tenant_id)
        values = dict(data)
        values.setdefault("account_type", configuration["default_type"])
        if values["account_type"] not in configuration["allowed_types"]:
            raise CRMServiceError("Account type is not enabled by tenant configuration.", code="INVALID_ACCOUNT_TYPE")
        _validate_input_limits(tenant_id, "account", values)
        if set(data) & _IMMUTABLE_COMMON:
            raise CRMServiceError("Server-owned account fields cannot be supplied.", code="IMMUTABLE_FIELD")
        name = str(values.get("name") or "").strip()
        with tenant_context(tenant_id), transaction.atomic():
            if Account.objects.filter(tenant_id=tenant_id, name__iexact=name, is_deleted=False).exists():
                raise CRMServiceError(
                    "An active account with this name already exists.",
                    code="DUPLICATE_ACCOUNT",
                    http_status=status.HTTP_409_CONFLICT,
                )
            account = Account(tenant_id=tenant_id, created_by=actor, updated_by=actor, **values)
            account.save()
            _event(
                tenant_id,
                event_type="crm.account.created",
                aggregate_type="account",
                aggregate_id=account.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"version": account.version, "owner_id": account.owner_id},
            )
            return account

    @staticmethod
    def update_account(
        tenant_id: UUID,
        *,
        account_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Account:
        with tenant_context(tenant_id), transaction.atomic():
            account = Account.objects.select_for_update().get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(account, expected_version)
            configured_type = data.get("account_type")
            if (
                configured_type is not None
                and configured_type not in effective_configuration(tenant_id)["account"]["allowed_types"]
            ):
                raise CRMServiceError(
                    "Account type is not enabled by tenant configuration.", code="INVALID_ACCOUNT_TYPE"
                )
            changed = _assign(account, data, forbidden=set())
            if changed:
                account.updated_by = _actor(actor_id, tenant_id)
                account.save(update_fields=set(changed) | {"updated_by"})
                _event(
                    tenant_id,
                    event_type="crm.account.updated",
                    aggregate_type="account",
                    aggregate_id=account.id,
                    actor_id=actor_id,
                    correlation_id=None,
                    payload={"changed_fields": changed, "version": account.version},
                )
            return account

    @staticmethod
    def delete_account(
        tenant_id: UUID, *, account_id: UUID, expected_version: int, actor_id: str | UUID | None
    ) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            account = Account.objects.select_for_update().get(id=account_id, tenant_id=tenant_id, is_deleted=False)
            if Account.objects.filter(tenant_id=tenant_id, parent_account_id=account.id, is_deleted=False).exists():
                raise CRMServiceError(
                    "Cannot delete an account with active child accounts.",
                    code="ACCOUNT_HAS_CHILDREN",
                    http_status=status.HTTP_409_CONFLICT,
                )
            if Opportunity.objects.filter(
                tenant_id=tenant_id, account_id=account.id, status=OpportunityStatus.OPEN, is_deleted=False
            ).exists():
                raise CRMServiceError(
                    "Cannot delete account with open opportunities.",
                    code="ACCOUNT_HAS_OPEN_OPPORTUNITIES",
                    http_status=status.HTTP_409_CONFLICT,
                )
            _soft_delete(account, actor_id=actor_id, expected_version=expected_version)
            _event(
                tenant_id,
                event_type="crm.account.deleted",
                aggregate_type="account",
                aggregate_id=account.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={"version": account.version},
            )

    @staticmethod
    def get_hierarchy(tenant_id: UUID, *, account_id: UUID) -> AccountHierarchyNode:
        configuration = effective_configuration(tenant_id)
        maximum_nodes = int(configuration["hierarchy"]["max_nodes"])
        maximum_children = int(configuration["hierarchy"]["max_children"])
        maximum_depth = int(configuration["account"]["hierarchy_max_depth"])
        with tenant_context(tenant_id):
            root = Account.objects.only("id", "name", "account_type", "parent_account_id").get(
                id=account_id,
                tenant_id=tenant_id,
                is_deleted=False,
            )
            children: dict[UUID, list[Account]] = {}
            seen = {root.id}
            frontier = [root.id]
            node_count = 1
            depth = 1
            while frontier:
                child_query = Account.objects.filter(
                    tenant_id=tenant_id,
                    parent_account_id__in=frontier,
                    is_deleted=False,
                ).only("id", "name", "account_type", "parent_account_id")
                if depth >= maximum_depth:
                    if child_query.exists():
                        raise CRMServiceError(
                            "Stored hierarchy exceeds the supported depth.",
                            code="INVALID_HIERARCHY",
                        )
                    break
                remaining = maximum_nodes - node_count
                level = list(child_query.order_by("parent_account_id", "name", "id")[: remaining + 1])
                if len(level) > remaining:
                    raise CRMServiceError(
                        "Account hierarchy exceeds the configured node limit.",
                        code="HIERARCHY_LIMIT",
                    )
                next_frontier: list[UUID] = []
                for item in level:
                    if item.id in seen:
                        raise CRMServiceError("Stored hierarchy contains a cycle.", code="INVALID_HIERARCHY")
                    seen.add(item.id)
                    siblings = children.setdefault(item.parent_account_id, [])  # type: ignore[arg-type]
                    siblings.append(item)
                    if len(siblings) > maximum_children:
                        raise CRMServiceError(
                            "Account hierarchy exceeds the configured child limit.",
                            code="HIERARCHY_LIMIT",
                        )
                    next_frontier.append(item.id)
                node_count += len(level)
                frontier = next_frontier
                depth += 1

            def node(item: Account, depth: int = 1) -> AccountHierarchyNode:
                if depth > maximum_depth:
                    raise CRMServiceError("Stored hierarchy exceeds the supported depth.", code="INVALID_HIERARCHY")
                return AccountHierarchyNode(
                    item.id,
                    item.name,
                    item.account_type,
                    tuple(node(child, depth + 1) for child in children.get(item.id, [])),
                )

            return node(root)

    get_account_hierarchy = get_hierarchy

    @staticmethod
    def find_duplicates(tenant_id: UUID, *, name: str, website: str = "") -> DuplicateAccountResult:
        normalized = name.strip()
        with tenant_context(tenant_id):
            predicate = Q(name__iexact=normalized)
            if website.strip():
                predicate |= Q(website__iexact=website.strip())
            local = tuple(
                Account.objects.filter(predicate, tenant_id=tenant_id, is_deleted=False).order_by("name", "id")
            )
            providers = extension_registry.resolve("account_enrichment")
            if not providers:
                return DuplicateAccountResult(local, (), "unavailable")
            context = ExtensionContext(
                tenant_id, None, _correlation(tenant_id=tenant_id), f"duplicates:{normalized.casefold()}"
            )
            external: list[Mapping[str, object]] = []
            domain = urlsplit(website).hostname if website else None
            try:
                for provider in providers:
                    for match in provider.find_matches(
                        context, normalized_name=normalized.casefold(), website_domain=domain
                    ):
                        external.append(
                            {
                                "external_reference": match.external_reference,
                                "confidence": str(match.confidence) if match.confidence is not None else None,
                                "evidence_codes": list(match.evidence_codes),
                            }
                        )
            except CRMIntegrationError:
                return DuplicateAccountResult(local, (), "unavailable")
            return DuplicateAccountResult(local, tuple(external), "available")


class ContactService:
    @staticmethod
    def create_contact(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
        allow_domain_override: bool = False,
    ) -> Contact:
        configuration = effective_configuration(tenant_id)["contact"]
        actor = _actor(actor_id if actor_id is not None else created_by, tenant_id)
        _validate_input_limits(tenant_id, "contact", data)
        if set(data) & (_IMMUTABLE_COMMON | {"engagement_score", "last_contacted_at"}):
            raise CRMServiceError("Server-owned contact fields cannot be supplied.", code="IMMUTABLE_FIELD")
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact(
                tenant_id=tenant_id,
                created_by=actor,
                updated_by=actor,
                engagement_score=configuration["default_engagement_score"],
                **dict(data),
            )
            contact._allow_domain_override = allow_domain_override
            contact.save()
            _event(
                tenant_id,
                event_type="crm.contact.created",
                aggregate_type="contact",
                aggregate_id=contact.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"account_id": contact.account_id, "owner_id": contact.owner_id, "version": contact.version},
            )
            return contact

    @staticmethod
    def update_contact(
        tenant_id: UUID,
        *,
        contact_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
        allow_domain_override: bool = False,
    ) -> Contact:
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(contact, expected_version)
            changed = _assign(contact, data, forbidden={"engagement_score", "last_contacted_at"})
            if changed:
                contact._allow_domain_override = allow_domain_override
                contact.updated_by = _actor(actor_id, tenant_id)
                contact.save(update_fields=set(changed) | {"updated_by"})
                _event(
                    tenant_id,
                    event_type="crm.contact.updated",
                    aggregate_type="contact",
                    aggregate_id=contact.id,
                    actor_id=actor_id,
                    correlation_id=None,
                    payload={"changed_fields": changed, "version": contact.version},
                )
            return contact

    @staticmethod
    def delete_contact(
        tenant_id: UUID, *, contact_id: UUID, expected_version: int, actor_id: str | UUID | None
    ) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            _soft_delete(contact, actor_id=actor_id, expected_version=expected_version)
            _event(
                tenant_id,
                event_type="crm.contact.deleted",
                aggregate_type="contact",
                aggregate_id=contact.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={"version": contact.version},
            )

    @staticmethod
    def recalculate_engagement(
        tenant_id: UUID, *, contact_id: UUID, as_of: datetime, actor_id: str | UUID | None
    ) -> Contact:
        if timezone.is_naive(as_of):
            raise CRMServiceError("as_of must include a timezone.", code="INVALID_DATETIME")
        with tenant_context(tenant_id), transaction.atomic():
            configuration = effective_configuration(tenant_id)["contact"]
            contact = Contact.objects.select_for_update().get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            interactions = Activity.objects.filter(
                tenant_id=tenant_id,
                related_to_type=RelatedToType.CONTACT,
                related_to_id=contact.id,
                activity_type__in=[ActivityType.CALL, ActivityType.EMAIL, ActivityType.MEETING],
                created_at__lte=as_of,
                created_at__gte=as_of - timedelta(days=int(configuration["engagement_lookback_days"])),
                is_deleted=False,
            )
            evidence = interactions.aggregate(count=Count("id"))
            contact.engagement_score = min(
                int(evidence["count"]) * int(configuration["engagement_points_per_interaction"]),
                int(configuration["engagement_score_max"]),
            )
            latest = interactions.order_by("-completed_at", "-created_at").first()
            if latest:
                contact.last_contacted_at = latest.completed_at or latest.created_at
            contact.updated_by = _actor(actor_id, tenant_id)
            contact.save(update_fields=["engagement_score", "last_contacted_at", "updated_by"])
            return contact

    update_engagement_score = recalculate_engagement

    @staticmethod
    def get_timeline(tenant_id: UUID, *, contact_id: UUID, page: int = 1) -> QuerySet[Activity]:
        if page < 1:
            raise CRMServiceError("Page must be positive.", code="INVALID_PAGE")
        with tenant_context(tenant_id):
            Contact.objects.get(id=contact_id, tenant_id=tenant_id, is_deleted=False)
            return Activity.objects.filter(
                tenant_id=tenant_id, related_to_type=RelatedToType.CONTACT, related_to_id=contact_id, is_deleted=False
            ).order_by("-created_at", "-id")


class OpportunityService:
    @staticmethod
    def create_opportunity(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
    ) -> Opportunity:
        configuration = effective_configuration(tenant_id)["opportunity"]
        actor = _actor(actor_id if actor_id is not None else created_by, tenant_id)
        forbidden = set(data) & (
            _IMMUTABLE_COMMON
            | {"status", "closed_at", "loss_reason", "converted_to_order_id", "last_activity_at", "transition_history"}
        )
        if forbidden:
            raise CRMServiceError(
                "Server-owned opportunity fields cannot be supplied.",
                code="IMMUTABLE_FIELD",
                detail={"fields": sorted(forbidden)},
            )
        values = dict(data)
        _validate_input_limits(tenant_id, "opportunity", values)
        stage_value = str(values.get("stage") or configuration["default_stage"])
        stage_probabilities = {item["name"]: item["probability"] for item in configuration["stages"]}
        values["stage"] = stage_value
        values["probability"] = int(
            values.get("probability", stage_probabilities.get(stage_value, configuration["default_probability"]))
        )
        values["currency"] = str(values.get("currency") or configuration["default_currency"])
        values["status"] = configuration["default_status"]
        if stage_value not in stage_probabilities or stage_value in {
            OpportunityStage.CLOSED_WON,
            OpportunityStage.CLOSED_LOST,
        }:
            raise CRMServiceError("New opportunities must use an open stage.", code="INVALID_STAGE")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity(tenant_id=tenant_id, created_by=actor, updated_by=actor, **values)
            opportunity.save()
            _event(
                tenant_id,
                event_type="crm.opportunity.created",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={
                    "account_id": opportunity.account_id,
                    "amount": opportunity.amount,
                    "currency": opportunity.currency,
                    "close_date": opportunity.close_date,
                    "owner_id": opportunity.owner_id,
                    "version": opportunity.version,
                },
            )
            return opportunity

    @staticmethod
    def update_opportunity(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            _validate_version(opportunity, expected_version)
            changed = _assign(
                opportunity,
                data,
                forbidden={
                    "stage",
                    "status",
                    "probability",
                    "closed_at",
                    "loss_reason",
                    "converted_to_order_id",
                    "transition_history",
                },
            )
            if changed:
                opportunity.updated_by = _actor(actor_id, tenant_id)
                opportunity.save(update_fields=set(changed) | {"updated_by"})
                _event(
                    tenant_id,
                    event_type="crm.opportunity.updated",
                    aggregate_type="opportunity",
                    aggregate_id=opportunity.id,
                    actor_id=actor_id,
                    correlation_id=None,
                    payload={"changed_fields": changed, "version": opportunity.version},
                )
            return opportunity

    @staticmethod
    def delete_opportunity(
        tenant_id: UUID, *, opportunity_id: UUID, expected_version: int, actor_id: str | UUID | None
    ) -> None:
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            _soft_delete(opportunity, actor_id=actor_id, expected_version=expected_version)
            _event(
                tenant_id,
                event_type="crm.opportunity.deleted",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={"version": opportunity.version},
            )

    @staticmethod
    def transition_stage(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        command: str,
        transition_key: str,
        expected_version: int,
        actor_id: str | UUID | None,
        reason: str | None = None,
        allow_backward: bool = False,
    ) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            before = Opportunity.objects.get(id=opportunity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(before, expected_version)
            if command.startswith("reopen_to_") and not allow_backward:
                raise CRMServiceError(
                    "Backward stage movement requires reopen-stage permission.",
                    code="REOPEN_PERMISSION_REQUIRED",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            try:
                opportunity = apply_opportunity_command(
                    tenant_id,
                    opportunity_id=opportunity_id,
                    command=command,
                    transition_key=transition_key,
                    actor_id=_actor(actor_id, tenant_id),
                    correlation_id=_correlation(),
                    expected_version=expected_version,
                    reason=reason,
                    allow_backward_transition=allow_backward,
                )
            except StateMachineError as exc:
                raise CRMServiceError(
                    str(exc), code="ILLEGAL_TRANSITION", http_status=status.HTTP_409_CONFLICT
                ) from exc
            _event(
                tenant_id,
                event_type="crm.opportunity.stage_changed",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={
                    "from_stage": before.stage,
                    "to_stage": opportunity.stage,
                    "command": command,
                    "transition_key": transition_key,
                    "version": opportunity.version,
                },
            )
            return opportunity

    @staticmethod
    def close_won(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        transition_key: str,
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Opportunity:
        with tenant_context(tenant_id), transaction.atomic():
            before = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            _validate_version(before, expected_version)
            opportunity = apply_opportunity_command(
                tenant_id,
                opportunity_id=opportunity_id,
                command="close_won",
                transition_key=transition_key,
                actor_id=_actor(actor_id, tenant_id),
                correlation_id=_correlation(),
                expected_version=expected_version,
                confirmed=True,
            )
            account = Account.objects.select_for_update().get(
                id=opportunity.account_id, tenant_id=tenant_id, is_deleted=False
            )
            if account.account_type != AccountType.CUSTOMER:
                account.account_type = AccountType.CUSTOMER
                account.updated_by = _actor(actor_id, tenant_id)
                account.save(update_fields=["account_type", "updated_by"])
            ActivityService.create_activity(
                tenant_id,
                data={
                    "activity_type": ActivityType.NOTE,
                    "related_to_type": RelatedToType.OPPORTUNITY,
                    "related_to_id": opportunity.id,
                    "subject": "Opportunity closed as won",
                    "owner_id": opportunity.owner_id,
                },
                actor_id=actor_id,
                correlation_id=None,
                allow_closed_parent=True,
            )
            _event(
                tenant_id,
                event_type="crm.opportunity.closed_won",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={
                    "account_id": account.id,
                    "amount": opportunity.amount,
                    "currency": opportunity.currency,
                    "transition_key": transition_key,
                    "version": opportunity.version,
                },
            )
            return opportunity

    @staticmethod
    def close_lost(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        loss_reason: str,
        transition_key: str,
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Opportunity:
        reason = loss_reason.strip()
        if not reason:
            raise CRMServiceError("Loss reason is required.", code="LOSS_REASON_REQUIRED")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            _validate_version(opportunity, expected_version)
            opportunity = apply_opportunity_command(
                tenant_id,
                opportunity_id=opportunity_id,
                command="close_lost",
                transition_key=transition_key,
                actor_id=_actor(actor_id, tenant_id),
                correlation_id=_correlation(),
                expected_version=expected_version,
                reason=reason,
            )
            ActivityService.create_activity(
                tenant_id,
                data={
                    "activity_type": ActivityType.NOTE,
                    "related_to_type": RelatedToType.OPPORTUNITY,
                    "related_to_id": opportunity.id,
                    "subject": "Opportunity closed as lost",
                    "outcome": "lost",
                    "owner_id": opportunity.owner_id,
                },
                actor_id=actor_id,
                correlation_id=None,
                allow_closed_parent=True,
            )
            _event(
                tenant_id,
                event_type="crm.opportunity.closed_lost",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={
                    "account_id": opportunity.account_id,
                    "amount": opportunity.amount,
                    "currency": opportunity.currency,
                    "loss_code": "seller_recorded",
                    "transition_key": transition_key,
                    "version": opportunity.version,
                },
            )
            return opportunity

    @staticmethod
    def acknowledge_sales_order(
        tenant_id: UUID,
        *,
        opportunity_id: UUID,
        order_id: UUID,
        acknowledgement_id: UUID,
        idempotency_key: str,
        actor_id: str | UUID | None,
        correlation_id: str | None,
    ) -> Opportunity:
        """Link a won deal only after a verified durable acknowledgement."""

        if not idempotency_key.strip():
            raise CRMServiceError("Acknowledgement idempotency key is required.", code="INVALID_IDEMPOTENCY_KEY")
        with tenant_context(tenant_id), transaction.atomic():
            opportunity = Opportunity.objects.select_for_update().get(
                id=opportunity_id, tenant_id=tenant_id, is_deleted=False
            )
            if opportunity.status != OpportunityStatus.WON:
                raise CRMServiceError(
                    "Only a won opportunity can be linked to a sales order.",
                    code="OPPORTUNITY_NOT_WON",
                    http_status=status.HTTP_409_CONFLICT,
                )
            stored_ack = str(opportunity.metadata.get("sales_order_acknowledgement_id") or "")
            stored_key = str(opportunity.metadata.get("sales_order_idempotency_key") or "")
            if opportunity.converted_to_order_id is not None:
                if (
                    opportunity.converted_to_order_id == order_id
                    and stored_ack == str(acknowledgement_id)
                    and stored_key == idempotency_key
                ):
                    return opportunity
                raise CRMServiceError(
                    "Opportunity is already linked to another verified acknowledgement.",
                    code="ORDER_ACKNOWLEDGEMENT_CONFLICT",
                    http_status=status.HTTP_409_CONFLICT,
                )
            opportunity.converted_to_order_id = order_id
            opportunity.metadata = {
                **opportunity.metadata,
                "sales_order_acknowledgement_id": str(acknowledgement_id),
                "sales_order_idempotency_key": idempotency_key,
            }
            opportunity.updated_by = _actor(actor_id, tenant_id)
            opportunity.save(update_fields=["converted_to_order_id", "metadata", "updated_by"])
            _event(
                tenant_id,
                event_type="crm.opportunity.order_acknowledged",
                aggregate_type="opportunity",
                aggregate_id=opportunity.id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                payload={
                    "order_id": order_id,
                    "acknowledgement_id": acknowledgement_id,
                    "opportunity_id": opportunity.id,
                    "version": opportunity.version,
                },
            )
            return opportunity


class ActivityService:
    @staticmethod
    def _validate_parent(tenant_id: UUID, related_type: str, related_id: UUID, *, allow_closed: bool = False) -> Any:
        model = RELATED_MODELS.get(related_type)
        if model is None:
            raise CRMServiceError("Unsupported related entity type.", code="INVALID_RELATION_TYPE")
        parent = model.objects.filter(id=related_id, tenant_id=tenant_id, is_deleted=False).first()
        if parent is None:
            raise CRMServiceError(
                "Related CRM record was not found.",
                code="RELATED_RECORD_NOT_FOUND",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        if isinstance(parent, Opportunity) and parent.status != OpportunityStatus.OPEN and not allow_closed:
            raise CRMServiceError(
                "Activities on closed opportunities are immutable.",
                code="ACTIVITY_IMMUTABLE",
                http_status=status.HTTP_409_CONFLICT,
            )
        return parent

    @staticmethod
    def create_activity(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str | UUID | None = None,
        correlation_id: str | None = None,
        created_by: str | UUID | None = None,
        allow_closed_parent: bool = False,
    ) -> Activity:
        configuration = effective_configuration(tenant_id)["activity"]
        actor = _actor(actor_id if actor_id is not None else created_by, tenant_id)
        values = dict(data)
        values.setdefault("activity_type", configuration["default_type"])
        values.setdefault("related_to_type", configuration["default_related_type"])
        _validate_input_limits(tenant_id, "activity", values)
        if set(data) & (_IMMUTABLE_COMMON | {"completed", "completed_at"}):
            raise CRMServiceError("Server-owned activity fields cannot be supplied.", code="IMMUTABLE_FIELD")
        related_type = str(values.get("related_to_type") or "")
        related_id = values.get("related_to_id")
        with tenant_context(tenant_id), transaction.atomic():
            parent = ActivityService._validate_parent(
                tenant_id, related_type, related_id, allow_closed=allow_closed_parent
            )
            activity = Activity(tenant_id=tenant_id, created_by=actor, updated_by=actor, **values)
            activity.save()
            now = timezone.now()
            if isinstance(parent, Opportunity):
                Opportunity.objects.filter(pk=parent.pk, tenant_id=tenant_id).update(
                    last_activity_at=now, updated_at=now, version=F("version") + 1
                )
            elif isinstance(parent, Contact) and activity.activity_type in {
                ActivityType.CALL,
                ActivityType.EMAIL,
                ActivityType.MEETING,
            }:
                ContactService.recalculate_engagement(tenant_id, contact_id=parent.id, as_of=now, actor_id=actor)
            _event(
                tenant_id,
                event_type="crm.activity.created",
                aggregate_type="activity",
                aggregate_id=activity.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={
                    "activity_type": activity.activity_type,
                    "related_to_type": activity.related_to_type,
                    "related_to_id": activity.related_to_id,
                    "owner_id": activity.owner_id,
                    "version": activity.version,
                },
            )
            return activity

    @staticmethod
    def update_activity(
        tenant_id: UUID,
        *,
        activity_id: UUID,
        data: Mapping[str, object],
        expected_version: int,
        actor_id: str | UUID | None,
    ) -> Activity:
        with tenant_context(tenant_id), transaction.atomic():
            activity = Activity.objects.select_for_update().get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
            _validate_version(activity, expected_version)
            if activity.completed:
                raise CRMServiceError(
                    "Completed activities cannot be edited.",
                    code="ACTIVITY_IMMUTABLE",
                    http_status=status.HTTP_409_CONFLICT,
                )
            ActivityService._validate_parent(tenant_id, activity.related_to_type, activity.related_to_id)
            changed = _assign(
                activity, data, forbidden={"related_to_type", "related_to_id", "completed", "completed_at"}
            )
            if changed:
                activity.updated_by = _actor(actor_id, tenant_id)
                activity.save(update_fields=set(changed) | {"updated_by"})
                _event(
                    tenant_id,
                    event_type="crm.activity.updated",
                    aggregate_type="activity",
                    aggregate_id=activity.id,
                    actor_id=actor_id,
                    correlation_id=None,
                    payload={"changed_fields": changed, "version": activity.version},
                )
            return activity

    @staticmethod
    def complete_activity(
        tenant_id: UUID, *, activity_id: UUID, transition_key: str, expected_version: int, actor_id: str | UUID | None
    ) -> Activity:
        with tenant_context(tenant_id), transaction.atomic():
            activity = Activity.objects.select_for_update().get(id=activity_id, tenant_id=tenant_id, is_deleted=False)
            existing_key = activity.metadata.get("completion_transition_key")
            if activity.completed:
                if existing_key == transition_key:
                    return activity
                raise CRMServiceError(
                    "Activity is already completed under another key.",
                    code="IDEMPOTENCY_CONFLICT",
                    http_status=status.HTTP_409_CONFLICT,
                )
            _validate_version(activity, expected_version)
            activity.completed = True
            activity.completed_at = timezone.now()
            activity.updated_by = _actor(actor_id, tenant_id)
            activity.metadata = {**activity.metadata, "completion_transition_key": transition_key}
            activity.save(update_fields=["completed", "completed_at", "updated_by", "metadata"])
            _event(
                tenant_id,
                event_type="crm.activity.completed",
                aggregate_type="activity",
                aggregate_id=activity.id,
                actor_id=actor_id,
                correlation_id=None,
                payload={"completed": True, "transition_key": transition_key, "version": activity.version},
            )
            return activity

    @staticmethod
    def delete_activity(
        tenant_id: UUID,
        *,
        activity_id: UUID,
        expected_version: int,
        actor_id: str | UUID | None,
        is_administrator: bool = False,
    ) -> None:
        del tenant_id, activity_id, expected_version, actor_id, is_administrator
        raise CRMServiceError(
            "CRM activity evidence is append-only and cannot be deleted.",
            code="ACTIVITY_EVIDENCE_IMMUTABLE",
            http_status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @staticmethod
    def get_timeline(tenant_id: UUID, *, related_to_type: str, related_to_id: UUID) -> QuerySet[Activity]:
        with tenant_context(tenant_id):
            ActivityService._validate_parent(tenant_id, related_to_type, related_to_id, allow_closed=True)
            return Activity.objects.filter(
                tenant_id=tenant_id, related_to_type=related_to_type, related_to_id=related_to_id, is_deleted=False
            ).order_by("-created_at", "-id")

    get_activity_timeline = get_timeline

    @staticmethod
    def sync_external_activity(
        tenant_id: UUID, *, event: Mapping[str, object], idempotency_key: str, correlation_id: str
    ) -> Activity:
        required = {"activity_type", "related_to_type", "related_to_id", "subject", "external_id"}
        missing = required - set(event)
        if missing:
            raise CRMServiceError(
                "External activity event is incomplete.",
                code="INVALID_EXTERNAL_EVENT",
                detail={"missing": sorted(missing)},
            )
        with tenant_context(tenant_id), transaction.atomic():
            existing = (
                Activity.objects.select_for_update()
                .filter(
                    tenant_id=tenant_id,
                    activity_type=event["activity_type"],
                    external_id=event["external_id"],
                    is_deleted=False,
                )
                .first()
            )
            if existing:
                stored_key = existing.metadata.get("external_idempotency_key")
                if stored_key == idempotency_key:
                    return existing
                raise CRMServiceError(
                    "External activity identity was reused with different delivery evidence.",
                    code="IDEMPOTENCY_CONFLICT",
                    http_status=status.HTTP_409_CONFLICT,
                )
            data = dict(event)
            data["metadata"] = {**dict(data.get("metadata") or {}), "external_idempotency_key": idempotency_key}
            activity = ActivityService.create_activity(
                tenant_id, data=data, actor_id=None, correlation_id=correlation_id
            )
            _event(
                tenant_id,
                event_type="crm.activity.external_synced",
                aggregate_type="activity",
                aggregate_id=activity.id,
                actor_id=None,
                correlation_id=correlation_id,
                payload={
                    "activity_type": activity.activity_type,
                    "external_id": activity.external_id,
                    "related_to_type": activity.related_to_type,
                    "related_to_id": activity.related_to_id,
                    "version": activity.version,
                },
            )
            return activity


class ForecastingService:
    @staticmethod
    def _period(tenant_id: UUID, period_days: int | None) -> int:
        configuration = effective_configuration(tenant_id)["forecast"]
        value = int(configuration["default_period_days"]) if period_days is None else period_days
        minimum = int(configuration["minimum_period_days"])
        maximum = int(configuration["maximum_period_days"])
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise CRMServiceError(
                f"Period must be from {minimum} to {maximum} days.",
                code="INVALID_PERIOD",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        return value

    @staticmethod
    def _open_queryset(tenant_id: UUID, owner_id: UUID | None, period_days: int) -> QuerySet[Opportunity]:
        queryset = Opportunity.objects.filter(
            tenant_id=tenant_id,
            status=OpportunityStatus.OPEN,
            is_deleted=False,
            close_date__lte=timezone.localdate() + timedelta(days=period_days),
        )
        return queryset.filter(owner_id=owner_id) if owner_id else queryset

    @classmethod
    def get_weighted_pipeline(
        cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int | None = None
    ) -> Forecast:
        period = cls._period(tenant_id, period_days)
        weighted = ExpressionWrapper(
            F("amount") * F("probability") / Decimal("100"), output_field=DecimalField(max_digits=19, decimal_places=4)
        )
        with tenant_context(tenant_id):
            rows = (
                cls._open_queryset(tenant_id, owner_id, period)
                .values("currency")
                .annotate(total=Sum("amount"), weighted=Sum(weighted), count=Count("id"))
                .order_by("currency")
            )
            return Forecast(
                tuple(
                    CurrencyForecast(
                        row["currency"], row["total"] or Decimal("0"), row["weighted"] or Decimal("0"), row["count"]
                    )
                    for row in rows
                ),
                period,
            )

    @classmethod
    def get_win_rate(cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int | None = None) -> WinRate:
        period = cls._period(tenant_id, period_days)
        since = timezone.now() - timedelta(days=period)
        with tenant_context(tenant_id):
            queryset = Opportunity.objects.filter(
                tenant_id=tenant_id,
                is_deleted=False,
                closed_at__gte=since,
                status__in=[OpportunityStatus.WON, OpportunityStatus.LOST],
            )
            if owner_id:
                queryset = queryset.filter(owner_id=owner_id)
            counts = queryset.aggregate(
                total=Count("id"),
                won=Count("id", filter=Q(status=OpportunityStatus.WON)),
                lost=Count("id", filter=Q(status=OpportunityStatus.LOST)),
            )
            total = counts["total"]
            win_rate = (
                (Decimal(counts["won"]) * Decimal("100") / Decimal(total)).quantize(Decimal("0.01"))
                if total
                else Decimal("0")
            )
            return WinRate(win_rate, counts["won"], counts["lost"], total, period)

    @classmethod
    def get_pipeline_by_stage(
        cls, tenant_id: UUID, *, owner_id: UUID | None = None, period_days: int | None = None
    ) -> list[StageForecast]:
        period = cls._period(tenant_id, period_days)
        weighted = ExpressionWrapper(
            F("amount") * F("probability") / Decimal("100"), output_field=DecimalField(max_digits=19, decimal_places=4)
        )
        with tenant_context(tenant_id):
            rows = (
                cls._open_queryset(tenant_id, owner_id, period)
                .values("stage", "currency")
                .annotate(total=Sum("amount"), weighted=Sum(weighted), count=Count("id"))
                .order_by("stage", "currency")
            )
            return [
                StageForecast(
                    row["stage"],
                    row["currency"],
                    row["total"] or Decimal("0"),
                    row["weighted"] or Decimal("0"),
                    row["count"],
                )
                for row in rows
            ]

    @classmethod
    def predict_revenue(
        cls, tenant_id: UUID, *, period_days: int | None, actor_id: str | UUID | None, correlation_id: str | None
    ) -> OperationResult[RevenuePrediction]:
        period = cls._period(tenant_id, period_days)
        correlation = _correlation(correlation_id, tenant_id)
        with tenant_context(tenant_id):
            pipeline = cls.get_weighted_pipeline(tenant_id, period_days=period)
            payload = {
                "period_days": period,
                "pipeline_by_currency": [asdict(item) for item in pipeline.currencies],
                "as_of": timezone.now().isoformat(),
            }
            try:
                client = get_revenue_prediction_client()
                if hasattr(client, "tenant_id"):
                    client.tenant_id = tenant_id
                result = client.predict_revenue(payload, correlation_id=correlation)
            except IntegrationUnavailable as exc:
                return OperationResult.unavailable(
                    capability="crm.revenue_prediction",
                    message="Revenue prediction provider is unavailable.",
                    detail={"code": exc.code},
                )
            except (InvalidIntegrationResponse, CRMIntegrationError) as exc:
                return OperationResult.failed(
                    code=exc.code,
                    message="Revenue prediction could not be verified.",
                    http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            prediction = RevenuePrediction(
                result.provider,
                result.model,
                result.amount,
                result.currency,
                result.confidence,
                dict(result.factors),
                result.as_of,
                period,
            )
            return OperationResult.succeeded(
                prediction,
                evidence={"provider_request_id": result.provider_request_id or correlation, "as_of": result.as_of},
                provider=result.provider,
            )


class IntegrationService:
    """Compatibility facade retained for open-source v1 consumers."""

    @staticmethod
    def convert_lead_to_opportunity(
        lead_id: UUID, tenant_id: UUID, opportunity_data: Mapping[str, object], user_id: str | UUID | None
    ) -> dict[str, object]:
        lead = Lead.objects.get(id=lead_id, tenant_id=tenant_id, is_deleted=False)
        if lead.status != LeadStatus.QUALIFIED:
            LeadService.transition_lead(
                tenant_id,
                lead_id=lead.id,
                command="qualify",
                transition_key=f"legacy-qualify:{lead.id}",
                context={},
                actor_id=user_id,
            )
            lead.refresh_from_db()
        result = LeadService.convert_lead(
            tenant_id,
            lead_id=lead_id,
            data={**dict(opportunity_data), "create_new_account": True},
            expected_version=lead.version,
            transition_key=f"legacy-convert:{lead.id}",
            actor_id=user_id,
            correlation_id=None,
        )
        return {
            "lead": result.lead,
            "account": result.account,
            "contact": result.contact,
            "opportunity": result.opportunity,
        }


__all__ = [
    "AccountHierarchyNode",
    "AccountService",
    "ActivityService",
    "CRMServiceError",
    "ContactService",
    "CurrencyForecast",
    "DuplicateAccountResult",
    "Forecast",
    "ForecastingService",
    "IntegrationService",
    "LeadConversionResult",
    "LeadService",
    "OpportunityService",
    "RevenuePrediction",
    "StageForecast",
    "StaleVersionError",
    "WinRate",
]

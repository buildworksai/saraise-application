"""Transactional business authority for the email-marketing runtime.

Controllers and workers deliberately share these services.  This keeps tenant
ownership, lifecycle, consent, quota, provider evidence, and idempotency rules
identical regardless of how an operation enters the system.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlparse
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import APIException, NotFound, ValidationError

from src.core.access.entitlements import (
    EntitlementService,
    Quota,
    QuotaService,
)
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import enqueue, transition
from src.core.middleware.correlation import get_correlation_id

from .adapters import OperationResult
from .models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    DeliveryEvent,
    EmailCampaign,
    EmailMarketingConfiguration,
    EmailMarketingConfigurationVersion,
    EmailTemplate,
    LifecycleTransitionAudit,
    MutationIdempotencyRecord,
    SuppressionEntry,
)
from .state_machines import (
    CAMPAIGN_STATE_MACHINE,
    RECIPIENT_STATE_MACHINE,
    TEMPLATE_STATE_MACHINE,
)

logger = logging.getLogger("saraise.email_marketing")
SYSTEM_ACTOR_ID = uuid5(NAMESPACE_URL, "saraise:email-marketing:system")

PLATFORM_DELIVERY_BACKENDS = frozenset(
    {
        "django.core.mail.backends.smtp.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.console.EmailBackend",
    }
)
PLATFORM_SEMANTICS = frozenset({"success", "error", "warning", "neutral"})
PLATFORM_WORKFLOW_EDGES = {
    "campaign": frozenset(
        {
            "schedule:draft:scheduled",
            "reschedule:scheduled:scheduled",
            "unschedule:scheduled:draft",
            "queue_send:draft:queueing",
            "queue_send:scheduled:queueing",
            "queue_send:failed:queueing",
            "start_send:queueing:sending",
            "pause:queueing:paused",
            "pause:sending:paused",
            "resume:paused:queueing",
            "complete:sending:sent",
            "fail:queueing:failed",
            "fail:sending:failed",
            "cancel:draft:cancelled",
            "cancel:scheduled:cancelled",
            "cancel:queueing:cancelled",
            "cancel:sending:cancelled",
            "cancel:paused:cancelled",
            "cancel:failed:cancelled",
        }
    ),
    "template": frozenset(
        {
            "activate:draft:active",
            "archive:draft:archived",
            "archive:active:archived",
        }
    ),
    "recipient": frozenset(
        {
            "suppress:resolved:suppressed",
            "queue:resolved:queued",
            "cancel:resolved:cancelled",
            "cancel:suppressed:cancelled",
            "start_send:queued:sending",
            "suppress:queued:suppressed",
            "cancel:queued:cancelled",
            "accepted:sending:accepted",
            "fail:sending:failed",
            "bounce:sending:bounced",
            "cancel:sending:cancelled",
            "delivered:accepted:delivered",
            "bounce:accepted:bounced",
            "fail:accepted:failed",
            "unsubscribe:accepted:unsubscribed",
            "complain:accepted:complained",
            "unsubscribe:delivered:unsubscribed",
            "complain:delivered:complained",
            "retry:failed:queued",
            "cancel:failed:cancelled",
            "queue:suppressed:queued",
        }
    ),
}

DEFAULT_CONFIGURATION_DOCUMENT: dict[str, Any] = {
    "schema_version": 1,
    "defaults": {
        "template_category": "general",
        "campaign_type": "broadcast",
        "audience_resolver": "manual",
        "delivery_gateway": "django",
        "timezone": "UTC",
        "audience_schema_version": 1,
        "consent_purpose": "marketing",
    },
    "limits": {
        "json_max_depth": 8,
        "json_max_keys": 128,
        "evidence_json_max_bytes": 16_384,
        "evidence_json_max_depth": 6,
        "evidence_json_max_keys": 96,
        "template_design_max_bytes": 131_072,
        "audience_definition_max_bytes": 32_768,
        "consent_evidence_max_bytes": 32_768,
        "personalization_max_bytes": 65_536,
        "serializer_json_max_bytes": 32_768,
        "serializer_json_max_depth": 8,
        "serializer_json_max_keys": 100,
        "json_key_max_length": 128,
        "personalization_max_keys": 100,
        "recipient_count_max": 100_000,
        "recipient_key_max_length": 255,
        "display_name_max_length": 255,
        "subject_max_length": 500,
        "preview_text_max_length": 255,
        "search_max_length": 100,
    },
    "pagination": {
        "default_page_size": 25,
        "max_page_size": 100,
        "page_size_options": [25, 50, 100],
    },
    "workflows": {
        "campaign_types": ["broadcast"],
        "audience_resolver_keys": ["manual", "inline"],
        "audience_schema_versions": [1],
        "campaign_editable_states": ["draft"],
        "campaign_archivable_states": ["draft", "failed"],
        "campaign_physical_delete_protected_states": ["sent", "cancelled"],
        "campaign_archive_blocking_recipient_states": [
            "queued",
            "sending",
            "accepted",
        ],
        "template_editable_states": ["draft"],
        "recipient_initial_states": ["resolved", "suppressed"],
        "terminal_recipient_states": [
            "delivered",
            "bounced",
            "complained",
            "unsubscribed",
        ],
        "preflight_blocking_codes": ["CONTENT_INVALID", "SENDER_INVALID"],
        "provider_acknowledgement_mapping": {
            "transport_accepted": "accepted",
            "provider_accepted": "accepted",
            "accepted": "accepted",
            "provider_delivered": "delivered",
            "delivered": "delivered",
            "failed": "failed",
            "bounced": "bounced",
        },
        "provider_event_recipient_mapping": {
            "accepted": "accepted",
            "delivered": "delivered",
            "bounced": "bounced",
            "complained": "complained",
            "unsubscribed": "unsubscribed",
        },
        "provider_event_command_mapping": {
            "accepted": "accepted",
            "delivered": "delivered",
            "bounced": "bounce",
            "complained": "complain",
            "unsubscribed": "unsubscribe",
        },
        "transitions": {name: sorted(edges) for name, edges in PLATFORM_WORKFLOW_EDGES.items()},
    },
    "compliance": {
        "suppression_scopes": ["marketing", "all"],
        "suppression_reasons": [
            "unsubscribe",
            "hard_bounce",
            "complaint",
            "manual",
            "legal",
        ],
        "suppression_sources": [
            "user",
            "provider_event",
            "administrator",
            "migration",
        ],
        "consent_sources": [
            "form",
            "import",
            "api",
            "crm_event",
            "administrator",
            "unsubscribe",
        ],
        "consent_lawful_bases": [
            "consent",
            "legitimate_interest",
            "contractual",
        ],
        "permanent_suppression_reasons": ["unsubscribe", "complaint", "legal"],
        "protected_overwrite_reasons": ["hard_bounce", "complaint"],
        "automatic_suppression_events": [
            "bounced",
            "complained",
            "unsubscribed",
        ],
        "automatic_suppression_reasons": {
            "bounced": "hard_bounce",
            "complained": "complaint",
            "unsubscribed": "unsubscribe",
        },
        "consent_required_status": "granted",
        "suppression_scopes_by_purpose": {
            "marketing": ["all", "marketing"],
            "default": ["all"],
        },
    },
    "resilience": {
        "delivery_timeout_seconds": 10,
        "circuit_failure_threshold": 3,
        "circuit_reset_seconds": 60,
        "retry_max_attempts": 3,
        "retry_base_delay_seconds": 0.25,
        "retry_max_delay_seconds": 4,
        "retry_jitter_seconds": 0.25,
        "webhook_replay_window_seconds": 300,
    },
    "tokens": {
        "preflight_receipt_seconds": 900,
        "tracking_token_days": 90,
        "unsubscribe_token_days": 365,
    },
    "integrations": {
        "allowed_delivery_backends": ["django.core.mail.backends.smtp.EmailBackend"],
        "simulated_delivery_backends": [
            "django.core.mail.backends.locmem.EmailBackend",
            "django.core.mail.backends.console.EmailBackend",
        ],
        "gateway_keys": ["django"],
    },
    "filters": {
        "default_ordering_by_resource": {
            "campaigns": "-created_at",
            "templates": "-updated_at",
            "recipients": "-created_at",
            "deliveries": "-created_at",
            "suppressions": "-suppressed_at",
            "consents": "-captured_at",
        },
        "search_fields_by_resource": {
            "campaigns": ["campaign_code", "campaign_name", "subject"],
            "templates": ["template_code", "template_name", "subject"],
            "recipients": ["email", "display_name", "recipient_key"],
            "deliveries": ["provider_status_code", "error_code"],
            "suppressions": ["email"],
            "consents": ["email", "notice_version"],
        },
    },
    "health": {"outbox_freshness_seconds": 300, "probe_staleness_seconds": 30},
    "rate_limits": {"public_per_minute": 30},
    "quotas": {
        "api_reads": 100_000,
        "api_writes": 10_000,
        "audience_resolutions": 1_000,
        "monthly_recipients": 10_000,
    },
    "feature_flags": {
        "enabled": True,
        "roles": [],
        "cohorts": [],
        "rollout_percentage": 100,
    },
    "display": {
        "status_semantics": {
            "delivered": "success",
            "accepted": "success",
            "active": "success",
            "failed": "error",
            "bounced": "error",
            "cancelled": "error",
            "paused": "warning",
            "draft": "neutral",
        }
    },
}


class DomainConflict(APIException):
    status_code = 409
    default_detail = "The operation conflicts with the current resource state."
    default_code = "conflict"


class DependencyUnavailable(APIException):
    status_code = 503
    default_detail = "Email-marketing configuration is unavailable."
    default_code = "configuration_unavailable"


def get_platform_runtime_defaults() -> dict[str, Any]:
    """Return a defensive copy used only to materialize real tenant configuration."""

    return deepcopy(DEFAULT_CONFIGURATION_DOCUMENT)


def _configuration_environment() -> str:
    environment = str(getattr(settings, "SARAISE_MODE", "")).strip()
    if environment not in {"development", "self-hosted", "saas"}:
        raise DependencyUnavailable("SARAISE_MODE is invalid; tenant configuration cannot be selected safely.")
    return environment


def _validate_shape(value: Any, template: Any, path: str) -> None:
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ValidationError({path: "Must be an object."})
        missing = set(template) - set(value)
        unknown = set(value) - set(template)
        if missing or unknown:
            detail: dict[str, str] = {}
            if missing:
                detail["missing"] = ", ".join(sorted(missing))
            if unknown:
                detail["unknown"] = ", ".join(sorted(unknown))
            raise ValidationError({path: detail})
        for key, child in template.items():
            _validate_shape(value[key], child, f"{path}.{key}")
        return
    if isinstance(template, list):
        if not isinstance(value, list):
            raise ValidationError({path: "Must be an array."})
        if template:
            for index, child in enumerate(value):
                _validate_shape(child, template[0], f"{path}[{index}]")
        return
    if isinstance(template, bool):
        if not isinstance(value, bool):
            raise ValidationError({path: "Must be a boolean."})
        return
    if isinstance(template, int):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError({path: "Must be an integer."})
        return
    if isinstance(template, float):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError({path: "Must be a number."})
        return
    if not isinstance(value, type(template)):
        raise ValidationError({path: f"Must be {type(template).__name__}."})


def validate_configuration_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the complete tenant document against platform safety ceilings."""

    candidate = deepcopy(dict(document))
    _validate_shape(candidate, DEFAULT_CONFIGURATION_DOCUMENT, "document")
    if candidate["schema_version"] != 1:
        raise ValidationError({"schema_version": "Only schema version 1 is supported."})

    ceilings = {
        "json_max_depth": 16,
        "json_max_keys": 512,
        "evidence_json_max_bytes": 65_536,
        "evidence_json_max_depth": 16,
        "evidence_json_max_keys": 512,
        "template_design_max_bytes": 1_048_576,
        "audience_definition_max_bytes": 262_144,
        "consent_evidence_max_bytes": 262_144,
        "personalization_max_bytes": 262_144,
        "serializer_json_max_bytes": 262_144,
        "serializer_json_max_depth": 16,
        "serializer_json_max_keys": 512,
        "json_key_max_length": 255,
        "personalization_max_keys": 512,
        "recipient_count_max": 1_000_000,
        "recipient_key_max_length": 255,
        "display_name_max_length": 255,
        "subject_max_length": 500,
        "preview_text_max_length": 255,
        "search_max_length": 255,
    }
    for key, ceiling in ceilings.items():
        value = candidate["limits"][key]
        if value < 1 or value > ceiling:
            raise ValidationError({f"limits.{key}": f"Must be between 1 and {ceiling}."})

    pagination = candidate["pagination"]
    if not 1 <= pagination["default_page_size"] <= pagination["max_page_size"] <= 1_000:
        raise ValidationError({"pagination": "Require 1 <= default_page_size <= max_page_size <= 1000."})
    options = pagination["page_size_options"]
    if (
        not options
        or sorted(set(options)) != options
        or any(not isinstance(item, int) or item < 1 or item > pagination["max_page_size"] for item in options)
    ):
        raise ValidationError({"pagination.page_size_options": "Options must be unique, sorted, and within max."})
    if pagination["default_page_size"] not in options:
        raise ValidationError({"pagination.page_size_options": "Options must include the default page size."})

    resilience = candidate["resilience"]
    resilience_bounds = {
        "delivery_timeout_seconds": (1, 60),
        "circuit_failure_threshold": (1, 20),
        "circuit_reset_seconds": (1, 900),
        "retry_max_attempts": (0, 5),
        "retry_base_delay_seconds": (0, 10),
        "retry_max_delay_seconds": (0, 60),
        "retry_jitter_seconds": (0, 10),
        "webhook_replay_window_seconds": (1, 900),
    }
    for key, (minimum, maximum) in resilience_bounds.items():
        value = resilience[key]
        if value < minimum or value > maximum:
            raise ValidationError({f"resilience.{key}": f"Must be between {minimum} and {maximum}."})
    if resilience["retry_base_delay_seconds"] > resilience["retry_max_delay_seconds"]:
        raise ValidationError({"resilience": "Retry base delay cannot exceed retry maximum delay."})

    tokens = candidate["tokens"]
    if not 1 <= tokens["preflight_receipt_seconds"] <= 3_600:
        raise ValidationError({"tokens.preflight_receipt_seconds": "Must be between 1 and 3600."})
    if not 1 <= tokens["tracking_token_days"] <= 365:
        raise ValidationError({"tokens.tracking_token_days": "Must be between 1 and 365."})
    if not 1 <= tokens["unsubscribe_token_days"] <= 730:
        raise ValidationError({"tokens.unsubscribe_token_days": "Must be between 1 and 730."})

    workflows = candidate["workflows"]
    for name, allowed in PLATFORM_WORKFLOW_EDGES.items():
        configured = workflows["transitions"][name]
        if not configured or len(configured) != len(set(configured)) or not set(configured).issubset(allowed):
            raise ValidationError({f"workflows.transitions.{name}": "Contains an invalid or duplicate transition."})
    if not {"sent", "cancelled"}.issubset(set(workflows["campaign_physical_delete_protected_states"])):
        raise ValidationError(
            {
                "workflows.campaign_physical_delete_protected_states": (
                    "Sent and cancelled evidence must remain protected."
                )
            }
        )
    required_acknowledgements = {
        "transport_accepted",
        "provider_accepted",
        "provider_delivered",
        "accepted",
        "delivered",
        "failed",
        "bounced",
    }
    acknowledgement_mapping = workflows["provider_acknowledgement_mapping"]
    if set(acknowledgement_mapping) != required_acknowledgements:
        raise ValidationError(
            {"workflows.provider_acknowledgement_mapping": "Every gateway acknowledgement is required."}
        )
    if not set(acknowledgement_mapping.values()).issubset({"accepted", "delivered", "failed", "bounced"}):
        raise ValidationError({"workflows.provider_acknowledgement_mapping": "Contains an invalid outcome."})

    compliance = candidate["compliance"]
    permanent = set(compliance["permanent_suppression_reasons"])
    if not {"unsubscribe", "complaint", "legal"}.issubset(permanent):
        raise ValidationError(
            {"compliance.permanent_suppression_reasons": "Mandatory legal retention reasons cannot be removed."}
        )
    if not {"all", "marketing"}.issubset(set(compliance["suppression_scopes"])):
        raise ValidationError({"compliance.suppression_scopes": "The all and marketing scopes are mandatory."})
    if compliance["consent_required_status"] != "granted":
        raise ValidationError({"compliance.consent_required_status": "Consent checks must fail closed on granted."})

    integrations = candidate["integrations"]
    configured_backends = set(integrations["allowed_delivery_backends"]) | set(
        integrations["simulated_delivery_backends"]
    )
    if not configured_backends or not configured_backends.issubset(PLATFORM_DELIVERY_BACKENDS):
        raise ValidationError({"integrations": "Contains an unsupported delivery backend."})
    if not integrations["gateway_keys"] or any(not str(value).strip() for value in integrations["gateway_keys"]):
        raise ValidationError({"integrations.gateway_keys": "At least one non-empty gateway key is required."})

    feature_flags = candidate["feature_flags"]
    if not 0 <= feature_flags["rollout_percentage"] <= 100:
        raise ValidationError({"feature_flags.rollout_percentage": "Must be between 0 and 100."})
    for key in ("roles", "cohorts"):
        values = feature_flags[key]
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValidationError(
                {
                    f"feature_flags.{key}": (
                        "Values must be unique, non-empty strings."
                    )
                }
            )
    if any(value not in PLATFORM_SEMANTICS for value in candidate["display"]["status_semantics"].values()):
        raise ValidationError({"display.status_semantics": "Only semantic design tokens are allowed."})
    if not 1 <= candidate["rate_limits"]["public_per_minute"] <= 300:
        raise ValidationError({"rate_limits.public_per_minute": "Must be between 1 and 300."})
    return candidate


def _configuration_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            changes.extend(_configuration_diff(before.get(key), after.get(key), child_path))
        return changes
    if before != after:
        return [{"path": path, "before": before, "after": after}]
    return []


def _validate_tenant_json(tenant_id: UUID, value: object, byte_limit_key: str, field: str) -> None:
    limits = get_runtime_configuration(tenant_id).document["limits"]
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Must be valid JSON."}) from exc
    if len(encoded) > limits[byte_limit_key]:
        raise ValidationError({field: "Exceeds the tenant-configured byte limit."})
    key_count = 0

    def walk(node: object, depth: int) -> None:
        nonlocal key_count
        if depth > limits["serializer_json_max_depth"]:
            raise ValidationError({field: "Exceeds the tenant-configured nesting limit."})
        if isinstance(node, Mapping):
            key_count += len(node)
            if key_count > limits["serializer_json_max_keys"]:
                raise ValidationError({field: "Exceeds the tenant-configured key limit."})
            for key, child in node.items():
                if not isinstance(key, str) or len(key) > limits["json_key_max_length"]:
                    raise ValidationError({field: "Contains an invalid or oversized key."})
                walk(child, depth + 1)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for child in node:
                walk(child, depth + 1)

    walk(value, 1)


class ConfigurationService:
    """Tenant-scoped configuration authority with immutable version history."""

    @classmethod
    @transaction.atomic
    def current(cls, tenant_id: UUID) -> EmailMarketingConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        environment = _configuration_environment()
        current = (
            EmailMarketingConfiguration.objects.select_for_update()
            .filter(tenant_id=tenant, environment=environment)
            .first()
        )
        if current is not None:
            current.document = validate_configuration_document(current.document)
            return current
        document = validate_configuration_document(get_platform_runtime_defaults())
        current = EmailMarketingConfiguration.objects.create(
            tenant_id=tenant,
            environment=environment,
            version=1,
            document=document,
            updated_by=SYSTEM_ACTOR_ID,
        )
        EmailMarketingConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=current,
            version=1,
            previous_version=None,
            change_type="materialized",
            actor_id=SYSTEM_ACTOR_ID,
            correlation_id=get_correlation_id() or f"cfg_{uuid.uuid4().hex}",
            previous_document={},
            document=document,
        )
        return current

    @classmethod
    def preview(cls, tenant_id: UUID, document: Mapping[str, Any]) -> dict[str, Any]:
        normalized = validate_configuration_document(document)
        current = cls.current(tenant_id)
        return {
            "valid": True,
            "normalized_document": normalized,
            "changes": _configuration_diff(current.document, normalized),
            "warnings": [],
        }

    @classmethod
    @transaction.atomic
    def update(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        document: Mapping[str, Any],
        expected_version: int,
        *,
        change_type: str = "updated",
        rollback_source_version: int | None = None,
    ) -> EmailMarketingConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        current = cls.current(tenant)
        current = EmailMarketingConfiguration.objects.select_for_update().get(tenant_id=tenant, pk=current.pk)
        if current.version != expected_version:
            raise DomainConflict({"expected_version": f"Current version is {current.version}; refresh before saving."})
        normalized = validate_configuration_document(document)
        if normalized == current.document:
            raise DomainConflict("The submitted configuration contains no changes.")
        previous_document = deepcopy(current.document)
        previous_version = current.version
        current.document = normalized
        current.version += 1
        current.updated_by = actor
        current.save(update_fields=["document", "version", "updated_by", "updated_at"])
        EmailMarketingConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=current,
            version=current.version,
            previous_version=previous_version,
            change_type=change_type,
            actor_id=actor,
            correlation_id=get_correlation_id() or f"cfg_{uuid.uuid4().hex}",
            previous_document=previous_document,
            document=normalized,
            rollback_source_version=rollback_source_version,
        )
        return current

    @classmethod
    def history(cls, tenant_id: UUID):
        current = cls.current(tenant_id)
        return current.versions.for_tenant(_uuid(tenant_id, "tenant_id")).order_by("-version")

    @classmethod
    def rollback(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        target_version: int,
        expected_version: int,
    ) -> EmailMarketingConfiguration:
        current = cls.current(tenant_id)
        target = current.versions.for_tenant(_uuid(tenant_id, "tenant_id")).filter(version=target_version).first()
        if target is None:
            raise NotFound("Configuration version not found.")
        return cls.update(
            tenant_id,
            actor_id,
            target.document,
            expected_version,
            change_type="rollback",
            rollback_source_version=target_version,
        )


def get_runtime_configuration(tenant_id: UUID) -> EmailMarketingConfiguration:
    """Return the validated, persisted tenant configuration or fail closed."""

    try:
        return ConfigurationService.current(tenant_id)
    except (DjangoValidationError, IntegrityError, ValidationError):
        raise
    except Exception as exc:
        logger.exception(
            "email_marketing_configuration_unavailable",
            extra={
                "correlation_id": get_correlation_id() or "",
                "tenant_id": str(tenant_id),
                "operation": "configuration.read",
                "exception_class": type(exc).__name__,
            },
        )
        raise DependencyUnavailable() from exc


def _mutation_fingerprint(data: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(data), sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_key(value: str | None, operation: str, fingerprint: str) -> str:
    if value is not None and value.strip():
        return value.strip()
    return f"service:{operation}:{uuid.uuid4().hex}"


def _existing_mutation(
    tenant_id: UUID,
    operation: str,
    key: str,
    fingerprint: str,
    model: Any,
) -> Any | None:
    record = (
        MutationIdempotencyRecord.objects.for_tenant(tenant_id).filter(operation=operation, idempotency_key=key).first()
    )
    if record is None:
        return None
    if record.request_fingerprint != fingerprint:
        raise DomainConflict("The idempotency key was already used with a different request.")
    if record.resource_id is None:
        raise DependencyUnavailable("The recorded idempotent response has no resource reference.")
    try:
        return model.objects.for_tenant(tenant_id).get(pk=record.resource_id)
    except model.DoesNotExist as exc:
        raise DependencyUnavailable("The recorded idempotent resource is unavailable.") from exc


def _record_mutation(
    tenant_id: UUID,
    actor_id: UUID,
    operation: str,
    key: str,
    fingerprint: str,
    resource: Any,
) -> None:
    MutationIdempotencyRecord.objects.create(
        tenant_id=tenant_id,
        operation=operation,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        response_status=201,
        resource_type=resource._meta.label_lower,
        resource_id=resource.pk,
        response_document={"resource_id": str(resource.pk)},
        actor_id=actor_id,
        correlation_id=get_correlation_id() or f"idem_{uuid.uuid4().hex}",
    )


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    code: str
    reason: str
    consent_record_id: UUID | None = None
    suppression_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AudienceCandidate:
    email: str
    display_name: str = ""
    recipient_key: str | None = None
    personalization_data: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AudienceResolutionResult:
    candidates: tuple[AudienceCandidate, ...]
    evidence: Mapping[str, object]
    resolver_key: str = "manual"


@dataclass(frozen=True, slots=True)
class CampaignPreflight:
    campaign_id: UUID
    generated_at: datetime
    receipt: str
    content_valid: bool
    sender_valid: bool
    audience_resolved: bool
    resolved_count: int
    eligible_count: int
    suppressed_count: int
    consent_failure_count: int
    suppression_failure_count: int
    quota_required: int
    quota_remaining: int
    quota_available: bool
    entitlement_available: bool
    schedule_valid: bool
    gateway_status: str
    blockers: tuple[Mapping[str, str], ...]
    consequences: Mapping[str, str]

    @property
    def ready(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["ready"] = self.ready
        return value


@dataclass(frozen=True, slots=True)
class CampaignAnalytics:
    campaign_id: UUID
    resolved: int
    eligible: int
    suppressed: int
    accepted: int
    delivered: int
    unique_opened: int
    unique_clicked: int
    bounced: int
    failed: int
    unsubscribed: int
    complained: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    bounce_rate: float
    counter_drift: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_email(value: str) -> str:
    """Validate an address and lowercase only its DNS domain."""

    if not isinstance(value, str) or "@" not in value:
        raise ValidationError({"email": "A valid email address is required."})
    address = value.strip()
    try:
        validate_email(address)
    except DjangoValidationError as exc:
        raise ValidationError({"email": "A valid email address is required."}) from exc
    local, domain = address.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _uuid(value: UUID | str, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({name: "Must be a valid UUID."}) from exc


def _actor_metadata(actor_id: UUID | str | None, **extra: object) -> dict[str, object]:
    return {
        "actor_id": str(actor_id) if actor_id is not None else None,
        "correlation_id": get_correlation_id() or f"op_{uuid.uuid4().hex}",
        **extra,
    }


def _publish(
    event_type: str,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    actor_id: UUID | str | None,
    payload: Mapping[str, object],
    job_id: UUID | None = None,
    causation_id: str | None = None,
) -> OutboxEvent:
    """Persist a versioned domain event without depending on a broker."""

    from .events import publish_domain_event

    return publish_domain_event(
        event_type=event_type,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        correlation_id=get_correlation_id() or f"evt_{uuid.uuid4().hex}",
        causation_id=causation_id,
        job_id=job_id,
        payload=dict(payload),
    )


def _apply_transition(
    machine: object,
    aggregate: object,
    command: str,
    tenant_id: UUID,
    key: str,
    actor_id: UUID | str | None,
    *,
    context: Mapping[str, object] | None = None,
) -> Any:
    if not key or not key.strip():
        raise ValidationError({"idempotency_key": "This field is required."})
    machine_name = str(getattr(machine, "name", ""))
    aggregate_type = machine_name.rsplit(".", 1)[-1]
    from_state = str(getattr(aggregate, "status", ""))
    configured_edges = get_runtime_configuration(tenant_id).document["workflows"]["transitions"].get(aggregate_type, [])
    matching_edges = [edge for edge in configured_edges if edge.startswith(f"{command}:{from_state}:")]
    if not matching_edges:
        raise DomainConflict(f"Transition {command!r} from {from_state!r} is disabled by tenant configuration.")
    metadata = _actor_metadata(actor_id)
    transitioned = machine.apply(  # type: ignore[attr-defined]
        aggregate,
        command,
        tenant_id=tenant_id,
        transition_key=key.strip(),
        context=dict(context or {}),
        metadata=metadata,
    )
    transitioned.updated_at = timezone.now()
    transitioned.save(update_fields=["updated_at"])
    actor = _uuid(actor_id or SYSTEM_ACTOR_ID, "actor_id")
    LifecycleTransitionAudit.objects.get_or_create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=transitioned.pk,
        transition_key=key.strip(),
        defaults={
            "action": command,
            "from_state": from_state,
            "to_state": str(getattr(transitioned, "status", "")),
            "actor_id": actor,
            "correlation_id": str(metadata["correlation_id"]),
            "context": dict(context or {}),
        },
    )
    return transitioned


class CampaignService:
    editable_fields = frozenset(
        {
            "campaign_name",
            "description",
            "campaign_type",
            "template_id",
            "subject",
            "preview_text",
            "from_name",
            "from_email",
            "reply_to_email",
            "audience_definition",
            "timezone",
            "audience_resolver_key",
            "gateway_key",
            "verifier_key",
        }
    )

    @classmethod
    @transaction.atomic
    def create_campaign(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        data: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        fingerprint = _mutation_fingerprint(data)
        key = _idempotency_key(idempotency_key, "campaign.create", fingerprint)
        existing_mutation = _existing_mutation(tenant, "campaign.create", key, fingerprint, EmailCampaign)
        if existing_mutation is not None:
            return existing_mutation
        configuration = get_runtime_configuration(tenant).document
        values = dict(data)
        values.pop("tenant_id", None)
        values.pop("status", None)
        values.setdefault("campaign_type", configuration["defaults"]["campaign_type"])
        values.setdefault(
            "audience_resolver_key",
            configuration["defaults"]["audience_resolver"],
        )
        values.setdefault("gateway_key", configuration["defaults"]["delivery_gateway"])
        values.setdefault("timezone", configuration["defaults"]["timezone"])
        if values["campaign_type"] not in configuration["workflows"]["campaign_types"]:
            raise ValidationError({"campaign_type": "This campaign type is disabled by tenant configuration."})
        if values["audience_resolver_key"] not in configuration["workflows"]["audience_resolver_keys"]:
            raise ValidationError({"audience_resolver_key": "This resolver is disabled by tenant configuration."})
        if values["gateway_key"] not in configuration["integrations"]["gateway_keys"]:
            raise ValidationError({"gateway_key": "This gateway is disabled by tenant configuration."})
        template_id = values.pop("template_id", None)
        template = None
        if template_id is not None:
            template = EmailTemplate.objects.for_tenant(tenant).filter(pk=template_id, is_deleted=False).first()
            if template is None:
                raise ValidationError({"template_id": "Template does not exist for this tenant."})
        values["campaign_code"] = str(values.get("campaign_code", "")).strip().upper()
        if not values["campaign_code"]:
            raise ValidationError({"campaign_code": "This field is required."})
        values["from_email"] = normalize_email(str(values.get("from_email", "")))
        if values.get("reply_to_email"):
            values["reply_to_email"] = normalize_email(str(values["reply_to_email"]))
        cls._validate_timezone(str(values["timezone"]))
        cls._validate_audience_definition(tenant, values.get("audience_definition", {}))
        campaign = EmailCampaign(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            template=template,
            **values,
        )
        try:
            campaign.full_clean()
            campaign.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.campaign.created.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor,
            payload={
                "campaign_code": campaign.campaign_code,
                "status": campaign.status,
            },
        )
        _record_mutation(tenant, actor, "campaign.create", key, fingerprint, campaign)
        return campaign

    @classmethod
    @transaction.atomic
    def update_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        data: Mapping[str, Any],
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        configuration = get_runtime_configuration(tenant).document
        if campaign.status not in configuration["workflows"]["campaign_editable_states"]:
            raise DomainConflict("This campaign state is not editable under tenant configuration.")
        unknown = set(data) - cls.editable_fields
        if unknown:
            raise ValidationError({field: "This field is not editable." for field in sorted(unknown)})
        values = dict(data)
        if "template_id" in values:
            template_id = values.pop("template_id")
            if template_id is None:
                campaign.template = None
            else:
                template = EmailTemplate.objects.for_tenant(tenant).filter(pk=template_id, is_deleted=False).first()
                if template is None:
                    raise ValidationError({"template_id": "Template does not exist for this tenant."})
                campaign.template = template
        if "from_email" in values:
            values["from_email"] = normalize_email(str(values["from_email"]))
        if values.get("reply_to_email"):
            values["reply_to_email"] = normalize_email(str(values["reply_to_email"]))
        if "timezone" in values:
            cls._validate_timezone(str(values["timezone"]))
        if "audience_definition" in values:
            cls._validate_audience_definition(tenant, values["audience_definition"])
            campaign.audience_snapshot_at = None
        for field, value in values.items():
            setattr(campaign, field, value)
        campaign.updated_by = _uuid(actor_id, "actor_id")
        try:
            campaign.full_clean()
            campaign.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return campaign

    @classmethod
    @transaction.atomic
    def archive_campaign(cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID) -> None:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        workflow = get_runtime_configuration(tenant).document["workflows"]
        if campaign.status not in workflow["campaign_archivable_states"]:
            raise DomainConflict("This campaign state is not archivable under tenant configuration.")
        if campaign.recipients.filter(status__in=workflow["campaign_archive_blocking_recipient_states"]).exists():
            raise DomainConflict("A campaign with active delivery work cannot be archived.")
        campaign.is_deleted = True
        campaign.deleted_at = timezone.now()
        campaign.deleted_by = _uuid(actor_id, "actor_id")
        campaign.updated_by = campaign.deleted_by
        campaign.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "deleted_by",
                "updated_by",
                "updated_at",
            ]
        )

    @classmethod
    @transaction.atomic
    def schedule_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        scheduled_at: datetime,
        timezone_name: str,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        cls._validate_schedule(scheduled_at, timezone_name)
        preflight = cls.preflight(tenant, campaign.id)
        blocking_codes = get_runtime_configuration(tenant).document["workflows"]["preflight_blocking_codes"]
        critical = [item for item in preflight.blockers if item["code"] in blocking_codes]
        if critical:
            raise DomainConflict({"preflight": critical})
        campaign.scheduled_at = scheduled_at
        campaign.timezone = timezone_name
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save(
            update_fields=[
                "scheduled_at",
                "timezone",
                "updated_by",
                "updated_at",
            ]
        )
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "schedule",
            tenant,
            idempotency_key,
            actor_id,
        )
        _publish(
            "email_marketing.campaign.scheduled.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor_id,
            payload={
                "scheduled_at": scheduled_at.isoformat(),
                "timezone": timezone_name,
            },
        )
        return transitioned

    @classmethod
    @transaction.atomic
    def reschedule_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        scheduled_at: datetime,
        timezone_name: str,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        cls._validate_schedule(scheduled_at, timezone_name)
        campaign.scheduled_at = scheduled_at
        campaign.timezone = timezone_name
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save(
            update_fields=[
                "scheduled_at",
                "timezone",
                "updated_by",
                "updated_at",
            ]
        )
        return _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "reschedule",
            tenant,
            idempotency_key,
            actor_id,
        )

    @classmethod
    @transaction.atomic
    def set_schedule(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        scheduled_at: datetime,
        timezone_name: str,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        method = cls.reschedule_campaign if campaign.status == "scheduled" else cls.schedule_campaign
        return method(
            tenant,
            campaign.id,
            actor_id,
            scheduled_at,
            timezone_name,
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def unschedule_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "unschedule",
            tenant,
            idempotency_key,
            actor_id,
        )
        transitioned.scheduled_at = None
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["scheduled_at", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def request_audience_resolution(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience can only be resolved for a draft campaign.")
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.resolve_audience",
            {"campaign_id": str(campaign.id)},
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def request_send(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
        preflight_receipt: str | None = None,
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        existing = AsyncJob.objects.for_tenant(tenant).filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
        preflight = cls.preflight(tenant, campaign.id)
        if not preflight_receipt:
            raise DomainConflict("A current preflight receipt is required before sending.")
        try:
            receipt_seconds = get_runtime_configuration(tenant).document["tokens"]["preflight_receipt_seconds"]
            submitted_preflight = signing.loads(
                preflight_receipt,
                salt="email_marketing.preflight",
                max_age=receipt_seconds,
            )
            current_preflight = signing.loads(preflight.receipt, salt="email_marketing.preflight")
        except signing.BadSignature as exc:
            raise DomainConflict("The preflight receipt is invalid or expired; run preflight again.") from exc
        if not constant_time_compare(str(submitted_preflight), str(current_preflight)):
            raise DomainConflict("The campaign changed after preflight; review the refreshed preflight before sending.")
        if not preflight.ready:
            raise DomainConflict({"preflight": list(preflight.blockers)})
        quota = QuotaService().consume(
            tenant,
            "email_marketing.monthly_recipients",
            cost=preflight.eligible_count,
        )
        if not quota.allowed:
            raise DomainConflict("Recipient quota is insufficient.")
        cls._snapshot_content(campaign)
        campaign.queue_started_at = timezone.now()
        campaign.updated_by = _uuid(actor_id, "actor_id")
        campaign.save()
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "queue_send",
            tenant,
            idempotency_key,
            actor_id,
            context={
                "preflight_ready": True,
                "entitlement_available": preflight.entitlement_available,
                "quota_available": True,
                "consent_evaluated": True,
            },
        )
        for recipient in CampaignRecipient.objects.select_for_update().filter(
            tenant_id=tenant, campaign=transitioned, status="resolved"
        ):
            queued_recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "queue",
                tenant,
                f"queue:{idempotency_key}:{recipient.id}",
                actor_id,
            )
            queued_recipient.queued_at = timezone.now()
            queued_recipient.save(update_fields=["queued_at", "updated_at"])
        job = enqueue(
            tenant,
            actor_id,
            "email_marketing.send_campaign",
            {
                "campaign_id": str(campaign.id),
                "preflight_receipt": preflight.receipt,
            },
            idempotency_key,
        )
        _publish(
            "email_marketing.campaign.send_queued.v1",
            tenant,
            "email_campaign",
            campaign.id,
            actor_id=actor_id,
            payload={"eligible_recipient_count": preflight.eligible_count},
            job_id=job.id,
        )
        return job

    @classmethod
    @transaction.atomic
    def pause_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        return _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "pause",
            tenant,
            idempotency_key,
            actor_id,
        )

    @classmethod
    @transaction.atomic
    def resume_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "resume",
            tenant,
            idempotency_key,
            actor_id,
        )
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.send_campaign",
            {"campaign_id": str(campaign.id), "resume": True},
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def cancel_campaign(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> EmailCampaign:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._locked_campaign(tenant, campaign_id)
        transitioned = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "cancel",
            tenant,
            idempotency_key,
            actor_id,
        )
        recipients = CampaignRecipient.objects.select_for_update().filter(
            tenant_id=tenant,
            campaign=campaign,
            status__in={"resolved", "queued", "sending"},
        )
        for recipient in recipients:
            _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "cancel",
                tenant,
                f"cancel:{idempotency_key}:{recipient.id}",
                actor_id,
            )
        jobs = AsyncJob.objects.for_tenant(tenant).filter(
            payload__campaign_id=str(campaign.id),
            status__in={JobStatus.QUEUED, JobStatus.RETRYING},
        )
        for job in jobs:
            transition(
                job.id,
                tenant,
                JobStatus.CANCELLED,
                reason="Campaign cancelled",
                actor_id=actor_id,
            )
        return transitioned

    @classmethod
    def preflight(cls, tenant_id: UUID, campaign_id: UUID) -> CampaignPreflight:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._campaign(tenant, campaign_id)
        counts = dict(
            CampaignRecipient.objects.for_tenant(tenant)
            .filter(campaign=campaign)
            .values_list("status")
            .annotate(total=Count("id"))
        )
        eligible = int(counts.get("resolved", 0))
        resolved = CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign).count()
        suppressed = int(counts.get("suppressed", 0))
        content_valid = bool(campaign.template_id and campaign.subject.strip())
        sender_valid = cls._sender_is_verified(tenant, campaign.from_email)
        public_url = str(getattr(settings, "SARAISE_PUBLIC_URL", "")).rstrip("/")
        public_url_valid = urlparse(public_url).scheme == "https" and bool(urlparse(public_url).netloc)
        entitlement = EntitlementService().check(tenant, "email_marketing").entitled
        quota_state = Quota.objects.filter(tenant_id=tenant, resource="email_marketing.monthly_recipients").first()
        quota_remaining = int(quota_state.remaining) if quota_state else 0
        quota_available = eligible > 0 and quota_remaining >= eligible
        gateway_status = "unavailable"
        try:
            from .adapters import get_delivery_gateway

            gateway = get_delivery_gateway(campaign.gateway_key)
            health_for_tenant = getattr(gateway, "health_for_tenant", None)
            health = health_for_tenant(tenant) if callable(health_for_tenant) else gateway.health()
            gateway_status = str(getattr(health, "code", "unavailable")) if health.available else "unavailable"
        except Exception:
            gateway_status = "unavailable"
        blockers: list[Mapping[str, str]] = []
        if not content_valid:
            blockers.append(
                {
                    "code": "CONTENT_INVALID",
                    "message": "Select a valid template and subject.",
                }
            )
        if not sender_valid:
            blockers.append(
                {
                    "code": "SENDER_INVALID",
                    "message": "Verify this sender for the tenant.",
                }
            )
        if not public_url_valid:
            blockers.append(
                {
                    "code": "PUBLIC_URL_INVALID",
                    "message": "Configure a public HTTPS URL for unsubscribe and tracking links.",
                }
            )
        if campaign.audience_snapshot_at is None:
            blockers.append(
                {
                    "code": "AUDIENCE_NOT_RESOLVED",
                    "message": "Resolve the audience before sending.",
                }
            )
        if eligible <= 0:
            blockers.append(
                {
                    "code": "NO_ELIGIBLE_RECIPIENTS",
                    "message": "No consent-eligible recipients are available.",
                }
            )
        if not entitlement:
            blockers.append(
                {
                    "code": "ENTITLEMENT_REQUIRED",
                    "message": "Email marketing entitlement is unavailable.",
                }
            )
        if not quota_available:
            blockers.append(
                {
                    "code": "QUOTA_INSUFFICIENT",
                    "message": "Recipient quota is insufficient.",
                }
            )
        if gateway_status != "ready":
            blockers.append(
                {
                    "code": "GATEWAY_UNAVAILABLE",
                    "message": "The configured delivery gateway is not ready.",
                }
            )
        generated = timezone.now()
        receipt_payload = ":".join(
            [
                str(campaign.id),
                campaign.updated_at.isoformat(),
                str(campaign.audience_snapshot_at),
                str(eligible),
                str(quota_remaining),
            ]
        )
        receipt = signing.dumps(receipt_payload, salt="email_marketing.preflight", compress=True)
        return CampaignPreflight(
            campaign_id=campaign.id,
            generated_at=generated,
            receipt=receipt,
            content_valid=content_valid,
            sender_valid=sender_valid,
            audience_resolved=campaign.audience_snapshot_at is not None,
            resolved_count=resolved,
            eligible_count=eligible,
            suppressed_count=suppressed,
            consent_failure_count=suppressed,
            suppression_failure_count=CampaignRecipient.objects.for_tenant(tenant)
            .filter(campaign=campaign, status="suppressed")
            .exclude(suppression_reason="consent_not_granted")
            .count(),
            quota_required=eligible,
            quota_remaining=quota_remaining,
            quota_available=quota_available,
            entitlement_available=entitlement,
            schedule_valid=campaign.scheduled_at is None or campaign.scheduled_at > generated,
            gateway_status=gateway_status,
            blockers=tuple(blockers),
            consequences={
                "send": f"Queues {eligible} eligible recipients and reserves the same number of quota units.",
                "pause": "Stops new provider submissions; already accepted messages cannot be recalled.",
                "resume": "Queues only recipients that remain eligible and have not been accepted.",
                "cancel": "Cancels unsent recipients and pending jobs; accepted provider messages remain immutable.",
            },
        )

    @classmethod
    def get_campaign_analytics(cls, tenant_id: UUID, campaign_id: UUID) -> CampaignAnalytics:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = cls._campaign(tenant, campaign_id)
        recipients = CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign)
        counts = {row["status"]: row["total"] for row in recipients.values("status").annotate(total=Count("id"))}
        events = DeliveryEvent.objects.for_tenant(tenant).filter(recipient__campaign=campaign)
        unique_opened = events.filter(event_type="opened").values("recipient_id").distinct().count()
        unique_clicked = events.filter(event_type="clicked").values("recipient_id").distinct().count()
        accepted = sum(int(counts.get(value, 0)) for value in ("accepted", "delivered", "bounced", "complained"))
        delivered = int(counts.get("delivered", 0))
        bounced = int(counts.get("bounced", 0))
        failed = int(counts.get("failed", 0))
        unsubscribed = int(counts.get("unsubscribed", 0))
        complained = int(counts.get("complained", 0))
        truth = {
            "sent_count": accepted,
            "delivered_count": delivered,
            "unique_opened_count": unique_opened,
            "unique_clicked_count": unique_clicked,
            "bounced_count": bounced,
            "failed_count": failed,
            "unsubscribed_count": unsubscribed,
            "complaint_count": complained,
        }
        drift = {name: int(getattr(campaign, name)) - value for name, value in truth.items()}
        return CampaignAnalytics(
            campaign_id=campaign.id,
            resolved=recipients.count(),
            eligible=int(counts.get("resolved", 0)),
            suppressed=int(counts.get("suppressed", 0)),
            accepted=accepted,
            delivered=delivered,
            unique_opened=unique_opened,
            unique_clicked=unique_clicked,
            bounced=bounced,
            failed=failed,
            unsubscribed=unsubscribed,
            complained=complained,
            delivery_rate=delivered / accepted if accepted else 0.0,
            open_rate=unique_opened / delivered if delivered else 0.0,
            click_rate=unique_clicked / delivered if delivered else 0.0,
            bounce_rate=bounced / accepted if accepted else 0.0,
            counter_drift=drift,
        )

    @staticmethod
    def _validate_timezone(value: str) -> None:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError({"timezone": "Must be a valid IANA timezone."}) from exc

    @classmethod
    def _validate_schedule(cls, scheduled_at: datetime, timezone_name: str) -> None:
        cls._validate_timezone(timezone_name)
        if timezone.is_naive(scheduled_at) or scheduled_at <= timezone.now():
            raise ValidationError({"scheduled_at": "Must be an aware future datetime."})

    @staticmethod
    def _validate_audience_definition(tenant_id: UUID, value: object) -> None:
        if not isinstance(value, Mapping):
            raise ValidationError({"audience_definition": "Must be an object."})
        _validate_tenant_json(
            tenant_id,
            value,
            "audience_definition_max_bytes",
            "audience_definition",
        )
        configured_versions = get_runtime_configuration(tenant_id).document["workflows"]["audience_schema_versions"]
        if value and value.get("version", value.get("schema_version")) not in {
            *configured_versions,
            *(str(item) for item in configured_versions),
        }:
            raise ValidationError({"audience_definition": "The schema version is disabled by tenant configuration."})
        allowed = {
            "version",
            "schema_version",
            "resolver",
            "candidates",
            "recipients",
            "industry",
        }
        if set(value) - allowed:
            raise ValidationError({"audience_definition": "Contains unsupported keys."})

    @staticmethod
    def _sender_is_verified(tenant_id: UUID, email: str) -> bool:
        configured = getattr(settings, "EMAIL_MARKETING_VERIFIED_SENDERS", {})
        if not isinstance(configured, Mapping):
            return False
        senders = configured.get(str(tenant_id), configured.get(tenant_id, ()))
        if not isinstance(senders, Sequence) or isinstance(senders, (str, bytes)):
            return False
        normalized = normalize_email(email)
        return normalized in {normalize_email(str(sender)) for sender in senders}

    @staticmethod
    def _snapshot_content(campaign: EmailCampaign) -> None:
        if campaign.template is None:
            raise DomainConflict("A template is required before sending.")
        from .adapters import sanitize_email_html

        campaign.content_snapshot_subject = campaign.subject or campaign.template.subject
        campaign.content_snapshot_html = sanitize_email_html(campaign.template.body_html)
        campaign.content_snapshot_text = campaign.template.body_text
        campaign.template_version_snapshot = campaign.template.version

    @staticmethod
    def _campaign(tenant_id: UUID, campaign_id: UUID) -> EmailCampaign:
        try:
            return (
                EmailCampaign.objects.for_tenant(tenant_id)
                .select_related("template")
                .get(pk=campaign_id, is_deleted=False)
            )
        except EmailCampaign.DoesNotExist as exc:
            raise NotFound("Campaign not found.") from exc

    @staticmethod
    def _locked_campaign(tenant_id: UUID, campaign_id: UUID) -> EmailCampaign:
        try:
            return (
                EmailCampaign.objects.select_for_update()
                .select_related("template")
                .get(tenant_id=tenant_id, pk=campaign_id, is_deleted=False)
            )
        except EmailCampaign.DoesNotExist as exc:
            raise NotFound("Campaign not found.") from exc


class TemplateService:
    editable_fields = frozenset(
        {
            "template_name",
            "description",
            "category",
            "subject",
            "preview_text",
            "body_html",
            "body_text",
            "design_json",
        }
    )

    @classmethod
    @transaction.atomic
    def create_template(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        data: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        fingerprint = _mutation_fingerprint(data)
        key = _idempotency_key(idempotency_key, "template.create", fingerprint)
        existing_mutation = _existing_mutation(tenant, "template.create", key, fingerprint, EmailTemplate)
        if existing_mutation is not None:
            return existing_mutation
        configuration = get_runtime_configuration(tenant).document
        values = dict(data)
        values.pop("tenant_id", None)
        values.pop("status", None)
        values.setdefault("category", configuration["defaults"]["template_category"])
        _validate_tenant_json(
            tenant,
            values.get("design_json", {}),
            "template_design_max_bytes",
            "design_json",
        )
        values["template_code"] = str(values.get("template_code", "")).strip().upper()
        template = EmailTemplate(
            tenant_id=tenant,
            created_by=actor,
            updated_by=actor,
            status="draft",
            is_active=False,
            **values,
        )
        try:
            template.full_clean()
            template.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _record_mutation(tenant, actor, "template.create", key, fingerprint, template)
        return template

    @classmethod
    @transaction.atomic
    def update_template(
        cls,
        tenant_id: UUID,
        template_id: UUID,
        actor_id: UUID,
        data: Mapping[str, Any],
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls._locked_template(tenant, template_id)
        if template.status not in get_runtime_configuration(tenant).document["workflows"]["template_editable_states"]:
            raise DomainConflict("This template state is not editable under tenant configuration.")
        unknown = set(data) - cls.editable_fields
        if unknown:
            raise ValidationError({field: "This field is not editable." for field in sorted(unknown)})
        for field, value in data.items():
            setattr(template, field, value)
        if "design_json" in data:
            _validate_tenant_json(
                tenant,
                data["design_json"],
                "template_design_max_bytes",
                "design_json",
            )
        template.version += 1
        template.updated_by = _uuid(actor_id, "actor_id")
        try:
            template.full_clean()
            template.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return template

    @classmethod
    @transaction.atomic
    def activate_template(
        cls,
        tenant_id: UUID,
        template_id: UUID,
        actor_id: UUID,
        transition_key: str,
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls._locked_template(tenant, template_id)
        if not template.subject.strip() or not (template.body_html.strip() or template.body_text.strip()):
            raise ValidationError("An active template requires a subject and at least one body.")
        transitioned = _apply_transition(
            TEMPLATE_STATE_MACHINE,
            template,
            "activate",
            tenant,
            transition_key,
            actor_id,
        )
        transitioned.is_active = True
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["is_active", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def archive_template(
        cls,
        tenant_id: UUID,
        template_id: UUID,
        actor_id: UUID,
        transition_key: str,
    ) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls._locked_template(tenant, template_id)
        transitioned = _apply_transition(
            TEMPLATE_STATE_MACHINE,
            template,
            "archive",
            tenant,
            transition_key,
            actor_id,
        )
        transitioned.is_active = False
        transitioned.updated_by = _uuid(actor_id, "actor_id")
        transitioned.save(update_fields=["is_active", "updated_by", "updated_at"])
        return transitioned

    @classmethod
    @transaction.atomic
    def clone_template(cls, tenant_id: UUID, template_id: UUID, actor_id: UUID, new_code: str) -> EmailTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        source = cls._template(tenant, template_id)
        return cls.create_template(
            tenant,
            actor_id,
            {
                "template_code": new_code,
                "template_name": f"{source.template_name} (copy)",
                "description": source.description,
                "category": source.category,
                "subject": source.subject,
                "preview_text": source.preview_text,
                "body_html": source.body_html,
                "body_text": source.body_text,
                "design_json": source.design_json,
            },
        )

    @classmethod
    def render_preview(
        cls,
        tenant_id: UUID,
        template_id: UUID,
        sample_data: Mapping[str, object],
    ) -> Any:
        template = cls._template(_uuid(tenant_id, "tenant_id"), template_id)
        from .adapters import get_renderer

        return get_renderer("default").render(
            {
                "subject": template.subject,
                "body_html": template.body_html,
                "body_text": template.body_text,
            },
            sample_data,
        )

    @classmethod
    @transaction.atomic
    def archive_record(cls, tenant_id: UUID, template_id: UUID, actor_id: UUID) -> None:
        template = cls._locked_template(_uuid(tenant_id, "tenant_id"), template_id)
        if template.status != "draft":
            raise DomainConflict("Only a draft template can be deleted.")
        template.is_deleted = True
        template.deleted_at = timezone.now()
        template.deleted_by = _uuid(actor_id, "actor_id")
        template.updated_by = template.deleted_by
        template.save(
            update_fields=[
                "is_deleted",
                "deleted_at",
                "deleted_by",
                "updated_by",
                "updated_at",
            ]
        )

    @staticmethod
    def _template(tenant_id: UUID, template_id: UUID) -> EmailTemplate:
        try:
            return EmailTemplate.objects.for_tenant(tenant_id).get(pk=template_id, is_deleted=False)
        except EmailTemplate.DoesNotExist as exc:
            raise NotFound("Template not found.") from exc

    @staticmethod
    def _locked_template(tenant_id: UUID, template_id: UUID) -> EmailTemplate:
        try:
            return EmailTemplate.objects.select_for_update().get(tenant_id=tenant_id, pk=template_id, is_deleted=False)
        except EmailTemplate.DoesNotExist as exc:
            raise NotFound("Template not found.") from exc


class ComplianceService:
    @classmethod
    @transaction.atomic
    def record_consent(
        cls,
        tenant_id: UUID,
        actor_id: UUID | None,
        data: Mapping[str, Any],
        capture_context: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> ConsentRecord:
        tenant = _uuid(tenant_id, "tenant_id")
        audit_actor = _uuid(actor_id, "actor_id") if actor_id else SYSTEM_ACTOR_ID
        fingerprint = _mutation_fingerprint(data)
        key = _idempotency_key(idempotency_key, "consent.create", fingerprint)
        existing_mutation = _existing_mutation(tenant, "consent.create", key, fingerprint, ConsentRecord)
        if existing_mutation is not None:
            return existing_mutation
        configuration = get_runtime_configuration(tenant).document
        values = dict(data)
        allowed = {
            "email",
            "purpose",
            "status",
            "lawful_basis",
            "source",
            "notice_version",
        }
        unknown = set(values) - allowed
        for key in unknown:
            values.pop(key, None)
        values["email"] = normalize_email(str(values.get("email", "")))
        values.setdefault("purpose", configuration["defaults"]["consent_purpose"])
        if values.get("source") not in configuration["compliance"]["consent_sources"]:
            raise ValidationError({"source": "This consent source is disabled by tenant configuration."})
        if values.get("lawful_basis") not in configuration["compliance"]["consent_lawful_bases"]:
            raise ValidationError({"lawful_basis": "This lawful basis is disabled by tenant configuration."})
        trusted_context = dict(capture_context or {})
        ip = trusted_context.get("remote_addr", "")
        user_agent = trusted_context.get("user_agent", "")
        values["captured_at"] = timezone.now()
        values["actor_id"] = audit_actor
        values["ip_hash"] = salted_hmac("email_marketing.consent.ip", ip).hexdigest() if ip else ""
        values["user_agent_hash"] = (
            salted_hmac("email_marketing.consent.user_agent", user_agent).hexdigest() if user_agent else ""
        )
        values["evidence"] = {
            "capture_channel": "authenticated_api" if actor_id else "system",
            "network_evidence_present": bool(ip),
            "user_agent_evidence_present": bool(user_agent),
        }
        previous = cls.latest_consent(tenant, values["email"], str(values["purpose"]))
        record = ConsentRecord(tenant_id=tenant, supersedes=previous, **values)
        try:
            record.full_clean()
            record.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.consent.changed.v1",
            tenant,
            "consent_record",
            record.id,
            actor_id=actor_id,
            payload={
                "purpose": record.purpose,
                "status": record.status,
                "source": record.source,
            },
        )
        _record_mutation(tenant, audit_actor, "consent.create", key, fingerprint, record)
        return record

    @classmethod
    def revoke_consent(
        cls,
        tenant_id: UUID,
        actor_id: UUID | None,
        email: str,
        purpose: str,
        source: str,
    ) -> ConsentRecord:
        previous = cls.latest_consent(_uuid(tenant_id, "tenant_id"), normalize_email(email), purpose)
        lawful_basis = previous.lawful_basis if previous else "consent"
        notice_version = previous.notice_version if previous else "revocation-v1"
        return cls.record_consent(
            tenant_id,
            actor_id,
            {
                "email": email,
                "purpose": purpose,
                "status": "revoked",
                "lawful_basis": lawful_basis,
                "source": source,
                "notice_version": notice_version,
            },
        )

    @classmethod
    @transaction.atomic
    def suppress(
        cls,
        tenant_id: UUID,
        actor_id: UUID | None,
        data: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> SuppressionEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        audit_actor = _uuid(actor_id, "actor_id") if actor_id else SYSTEM_ACTOR_ID
        fingerprint = _mutation_fingerprint(data)
        key = _idempotency_key(idempotency_key, "suppression.create", fingerprint)
        existing_mutation = _existing_mutation(tenant, "suppression.create", key, fingerprint, SuppressionEntry)
        if existing_mutation is not None:
            return existing_mutation
        compliance = get_runtime_configuration(tenant).document["compliance"]
        values = dict(data)
        values.pop("tenant_id", None)
        values["email"] = normalize_email(str(values.get("email", "")))
        values.setdefault("suppressed_at", timezone.now())
        values.setdefault("scope", compliance["suppression_scopes"][0])
        if values.get("scope") not in compliance["suppression_scopes"]:
            raise ValidationError({"scope": "This suppression scope is disabled by tenant configuration."})
        if values.get("reason") not in compliance["suppression_reasons"]:
            raise ValidationError({"reason": "This suppression reason is disabled by tenant configuration."})
        if values.get("source") not in compliance["suppression_sources"]:
            raise ValidationError({"source": "This suppression source is disabled by tenant configuration."})
        if values.get("reason") in compliance["permanent_suppression_reasons"] and values.get("expires_at") is not None:
            raise ValidationError({"expires_at": "This suppression reason cannot expire."})
        existing = (
            SuppressionEntry.objects.select_for_update()
            .filter(
                tenant_id=tenant,
                email=values["email"],
                scope=values["scope"],
                active=True,
            )
            .first()
        )
        if existing is not None:
            if existing.reason in compliance["protected_overwrite_reasons"] and existing.reason != values.get("reason"):
                raise DomainConflict("A provider-enforced suppression cannot be overwritten.")
            return existing
        entry = SuppressionEntry(
            tenant_id=tenant,
            created_by=audit_actor,
            updated_by=audit_actor,
            **values,
        )
        try:
            entry.full_clean()
            entry.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        _publish(
            "email_marketing.suppression.changed.v1",
            tenant,
            "suppression_entry",
            entry.id,
            actor_id=actor_id,
            payload={
                "scope": entry.scope,
                "reason": entry.reason,
                "active": True,
            },
        )
        _record_mutation(tenant, audit_actor, "suppression.create", key, fingerprint, entry)
        return entry

    @classmethod
    @transaction.atomic
    def deactivate_suppression(
        cls, tenant_id: UUID, suppression_id: UUID, actor_id: UUID, reason: str
    ) -> SuppressionEntry:
        if not reason.strip():
            raise ValidationError({"reason": "An audit reason is required."})
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            entry = SuppressionEntry.objects.select_for_update().get(tenant_id=tenant, pk=suppression_id, active=True)
        except SuppressionEntry.DoesNotExist as exc:
            raise NotFound("Suppression not found.") from exc
        entry.active = False
        entry.deactivated_at = timezone.now()
        entry.deactivated_by = _uuid(actor_id, "actor_id")
        entry.updated_by = entry.deactivated_by
        entry.notes = f"{entry.notes}\nDeactivation: {reason}".strip()
        entry.save()
        _publish(
            "email_marketing.suppression.changed.v1",
            tenant,
            "suppression_entry",
            entry.id,
            actor_id=actor_id,
            payload={
                "scope": entry.scope,
                "reason": entry.reason,
                "active": False,
            },
        )
        return entry

    @staticmethod
    def latest_consent(tenant_id: UUID, email: str, purpose: str) -> ConsentRecord | None:
        return (
            ConsentRecord.objects.for_tenant(_uuid(tenant_id, "tenant_id"))
            .filter(email=normalize_email(email), purpose=purpose)
            .order_by("-captured_at", "-created_at", "-id")
            .first()
        )

    @staticmethod
    def active_suppression(tenant_id: UUID, email: str, scope: str) -> SuppressionEntry | None:
        now = timezone.now()
        tenant = _uuid(tenant_id, "tenant_id")
        configured = get_runtime_configuration(tenant).document["compliance"]["suppression_scopes_by_purpose"]
        scopes = configured.get(scope, configured["default"])
        return (
            SuppressionEntry.objects.for_tenant(tenant)
            .filter(email=normalize_email(email), scope__in=scopes, active=True)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("-suppressed_at")
            .first()
        )

    @classmethod
    def is_eligible(cls, tenant_id: UUID, email: str, purpose: str) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        compliance = get_runtime_configuration(tenant).document["compliance"]
        normalized = normalize_email(email)
        suppression = cls.active_suppression(tenant, normalized, purpose)
        if suppression is not None:
            return EligibilityDecision(
                False,
                "SUPPRESSED",
                "An active suppression applies.",
                suppression_id=suppression.id,
            )
        consent = cls.latest_consent(tenant, normalized, purpose)
        if consent is None or consent.status != compliance["consent_required_status"]:
            return EligibilityDecision(
                False,
                "CONSENT_NOT_GRANTED",
                "The latest consent state does not permit marketing.",
                consent_record_id=consent.id if consent else None,
            )
        return EligibilityDecision(
            True,
            "ELIGIBLE",
            "Consent is current and no suppression applies.",
            consent.id,
        )


class AudienceService:
    @classmethod
    @transaction.atomic
    def resolve(cls, tenant_id: UUID, campaign_id: UUID, actor_id: UUID) -> AudienceResolutionResult:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = CampaignService._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience can only be resolved for a draft campaign.")
        from .adapters import get_audience_resolver

        resolver_key = getattr(campaign, "audience_resolver_key", "manual") or str(
            campaign.audience_definition.get("resolver", "manual")
        )
        definition = dict(campaign.audience_definition)
        if "version" in definition and "schema_version" not in definition:
            definition["schema_version"] = definition.pop("version")
        if "candidates" in definition and "recipients" not in definition:
            definition["recipients"] = definition.pop("candidates")
        result = get_audience_resolver(resolver_key).resolve(tenant, definition)
        candidates = tuple(
            AudienceCandidate(
                email=str(candidate.email),
                display_name=str(getattr(candidate, "display_name", "")),
                recipient_key=getattr(candidate, "recipient_key", None),
                personalization_data=(
                    getattr(candidate, "personalization_data", None) or getattr(candidate, "personalization", {}) or {}
                ),
            )
            for candidate in result.candidates
        )
        count = cls.replace_snapshot(tenant, campaign.id, actor_id, candidates)
        campaign.refresh_from_db()
        return (
            AudienceResolutionResult(candidates, dict(result.evidence), resolver_key)
            if count
            else AudienceResolutionResult((), dict(result.evidence), resolver_key)
        )

    @classmethod
    def evaluate_recipient(
        cls, tenant_id: UUID, campaign_id: UUID, candidate: AudienceCandidate
    ) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        CampaignService._campaign(tenant, campaign_id)
        normalized = normalize_email(candidate.email)
        if CampaignRecipient.objects.for_tenant(tenant).filter(campaign_id=campaign_id, email=normalized).exists():
            return EligibilityDecision(
                False,
                "DUPLICATE",
                "The normalized address is already in the snapshot.",
            )
        return ComplianceService.is_eligible(tenant, normalized, "marketing")

    @classmethod
    def recheck_before_send(cls, tenant_id: UUID, recipient_id: UUID) -> EligibilityDecision:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            recipient = CampaignRecipient.objects.for_tenant(tenant).get(pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        return ComplianceService.is_eligible(tenant, recipient.email, "marketing")

    @classmethod
    @transaction.atomic
    def replace_snapshot(
        cls,
        tenant_id: UUID,
        campaign_id: UUID,
        actor_id: UUID,
        candidates: Sequence[AudienceCandidate],
    ) -> int:
        tenant = _uuid(tenant_id, "tenant_id")
        campaign = CampaignService._locked_campaign(tenant, campaign_id)
        if campaign.status != "draft":
            raise DomainConflict("Audience snapshots are immutable after draft.")
        CampaignRecipient.objects.for_tenant(tenant).filter(campaign=campaign).delete()
        deduplicated: dict[str, AudienceCandidate] = {}
        for candidate in candidates:
            normalized = normalize_email(candidate.email)
            deduplicated.setdefault(normalized, candidate)
        records: list[CampaignRecipient] = []
        now = timezone.now()
        for email, candidate in deduplicated.items():
            decision = ComplianceService.is_eligible(tenant, email, "marketing")
            records.append(
                CampaignRecipient(
                    tenant_id=tenant,
                    campaign=campaign,
                    recipient_key=candidate.recipient_key,
                    email=email,
                    display_name=candidate.display_name,
                    personalization_data=dict(candidate.personalization_data or {}),
                    consent_record_id=decision.consent_record_id,
                    status="resolved" if decision.eligible else "suppressed",
                    suppression_reason=("" if decision.eligible else decision.code.lower()),
                    resolved_at=now,
                )
            )
        CampaignRecipient.objects.bulk_create(records)
        campaign.audience_snapshot_at = now
        campaign.resolved_recipient_count = len(records)
        campaign.updated_by = _uuid(actor_id, "actor_id")
        if hasattr(campaign, "audience_snapshot_evidence"):
            campaign.audience_snapshot_evidence = {
                "schema_version": 1,
                "deduplicated_count": len(records),
                "eligible_count": sum(record.status == "resolved" for record in records),
            }
        campaign.save()
        return len(records)


class DeliveryService:
    @classmethod
    @transaction.atomic
    def process_campaign_job(cls, job: AsyncJob) -> dict[str, object]:
        campaign_id = _uuid(job.payload.get("campaign_id"), "campaign_id")
        campaign = CampaignService._locked_campaign(job.tenant_id, campaign_id)
        if campaign.status == "paused":
            return {
                "campaign_id": str(campaign.id),
                "queued_count": 0,
                "status": "paused",
            }
        if campaign.status == "queueing":
            campaign = _apply_transition(
                CAMPAIGN_STATE_MACHINE,
                campaign,
                "start_send",
                job.tenant_id,
                f"start:{job.id}",
                job.actor_id,
            )
            campaign.send_started_at = timezone.now()
            campaign.save(update_fields=["send_started_at", "updated_at"])
        recipients = list(
            CampaignRecipient.objects.select_for_update().filter(
                tenant_id=job.tenant_id,
                campaign=campaign,
                status__in={"queued", "failed"},
            )
        )
        queued = 0
        for recipient in recipients:
            if recipient.status == "failed":
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "retry",
                    job.tenant_id,
                    f"retry:{job.id}:{recipient.id}",
                    job.actor_id,
                )
            child = enqueue(
                job.tenant_id,
                job.actor_id,
                "email_marketing.send_recipient",
                {
                    "campaign_id": str(campaign.id),
                    "recipient_id": str(recipient.id),
                },
                f"send-recipient:{campaign.id}:{recipient.id}",
            )
            queued += int(child.status in {JobStatus.QUEUED, JobStatus.RETRYING})
        return {
            "campaign_id": str(campaign.id),
            "queued_count": queued,
            "status": campaign.status,
        }

    @classmethod
    def submit_recipient(cls, tenant_id: UUID, recipient_id: UUID, job_id: UUID) -> OperationResult[DeliveryAttempt]:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            try:
                recipient = (
                    CampaignRecipient.objects.select_for_update()
                    .select_related("campaign")
                    .get(tenant_id=tenant, pk=recipient_id)
                )
            except CampaignRecipient.DoesNotExist as exc:
                raise NotFound("Recipient not found.") from exc
            existing = (
                DeliveryAttempt.objects.for_tenant(tenant)
                .filter(idempotency_key=f"recipient:{recipient.id}:job:{job_id}")
                .first()
            )
            if existing is not None:
                return OperationResult.success(existing, code="idempotent_attempt")
            if recipient.campaign.status == "paused":
                return OperationResult.failure("campaign_paused", detail="Campaign is paused.")
            decision = AudienceService.recheck_before_send(tenant, recipient.id)
            if not decision.eligible:
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "suppress",
                    tenant,
                    f"suppress:{job_id}:{recipient.id}",
                    SYSTEM_ACTOR_ID,
                )
                recipient.suppression_reason = decision.code.lower()
                recipient.save(update_fields=["suppression_reason", "updated_at"])
                return OperationResult.failure(
                    decision.code.lower(),
                    detail="Recipient is no longer eligible.",
                )
            number = (
                DeliveryAttempt.objects.for_tenant(tenant)
                .filter(recipient=recipient)
                .aggregate(total=Count("id"))["total"]
                + 1
            )
            attempt = DeliveryAttempt.objects.create(
                tenant_id=tenant,
                recipient=recipient,
                attempt_number=number,
                job_id=job_id,
                idempotency_key=f"recipient:{recipient.id}:job:{job_id}",
                gateway_key=getattr(recipient.campaign, "gateway_key", "django"),
                status="sending",
                started_at=timezone.now(),
            )
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "start_send",
                tenant,
                f"start:{attempt.id}",
                SYSTEM_ACTOR_ID,
            )

        from .adapters import (
            DeliveryMessage,
            get_delivery_gateway,
            get_renderer,
        )

        campaign = recipient.campaign
        rendered = get_renderer("default").render(
            {
                "subject": campaign.content_snapshot_subject,
                "body_html": campaign.content_snapshot_html,
                "body_text": campaign.content_snapshot_text,
            },
            recipient.personalization_data,
        )
        unsubscribe_token = signing.dumps(
            {"tenant_id": str(tenant), "recipient_id": str(recipient.id)},
            salt="email_marketing.unsubscribe",
        )
        tracking_token = signing.dumps(
            {"tenant_id": str(tenant), "recipient_id": str(recipient.id)},
            salt="email_marketing.tracking",
        )
        public_url = str(getattr(settings, "SARAISE_PUBLIC_URL", "")).rstrip("/")
        rendered = cls._instrument_rendered(rendered, public_url, tracking_token)
        unsubscribe_url = f"{public_url}/api/v2/email-marketing/public/unsubscribe/?token={unsubscribe_token}"
        message = DeliveryMessage(
            tenant_id=tenant,
            recipient=recipient.email,
            from_email=campaign.from_email,
            from_name=campaign.from_name,
            reply_to=campaign.reply_to_email,
            rendered=rendered,
            headers={
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        try:
            gateway = get_delivery_gateway(attempt.gateway_key)
            if getattr(gateway, "reconciliation_supported", False) is not True:
                result = OperationResult.failure(
                    "reconciliation_unsupported",
                    retryable=False,
                    ambiguous=False,
                    detail="The configured gateway cannot reconcile provider acceptance.",
                )
            else:
                result = gateway.submit(
                    message,
                    attempt.idempotency_key,
                    get_correlation_id() or str(job_id),
                )
        except Exception as exc:
            logger.exception(
                "email_marketing_gateway_submission_failed",
                extra={
                    "correlation_id": get_correlation_id() or str(job_id),
                    "tenant_id": str(tenant),
                    "operation": "delivery.submit",
                    "attempt_id": str(attempt.id),
                    "gateway_key": attempt.gateway_key,
                    "circuit_state": "unknown",
                    "exception_class": type(exc).__name__,
                },
            )
            result = OperationResult.failure(
                "gateway_unavailable",
                retryable=True,
                detail="Delivery gateway is unavailable.",
            )
        with transaction.atomic():
            attempt = DeliveryAttempt.objects.select_for_update().get(tenant_id=tenant, pk=attempt.id)
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient.id)
            if result.successful and result.value is not None:
                receipt = result.value
                provider_acknowledgement = str(getattr(receipt, "acknowledgement", ""))
                mapping = get_runtime_configuration(tenant).document["workflows"]["provider_acknowledgement_mapping"]
                acknowledgement = mapping.get(provider_acknowledgement)
                if acknowledgement is None:
                    attempt.status = "failed"
                    attempt.error_code = "invalid_gateway_acknowledgement"
                    attempt.error_detail = "Gateway returned an acknowledgement outside its configured contract."
                    attempt.completed_at = timezone.now()
                    attempt.save()
                    recipient = _apply_transition(
                        RECIPIENT_STATE_MACHINE,
                        recipient,
                        "fail",
                        tenant,
                        f"gateway-invalid:{attempt.id}",
                        SYSTEM_ACTOR_ID,
                    )
                    recipient.save()
                    return OperationResult.failure(
                        "invalid_gateway_acknowledgement",
                        detail="Gateway acknowledgement is not configured.",
                    )
                attempt.provider_message_id = str(getattr(receipt, "provider_message_id", ""))
                attempt.provider_status_code = provider_acknowledgement
                attempt.response_evidence = dict(getattr(receipt, "evidence", {}))
                if acknowledgement in {"accepted", "delivered"}:
                    attempt.status = acknowledgement
                    attempt.accepted_at = timezone.now()
                    if acknowledgement == "delivered":
                        attempt.completed_at = timezone.now()
                    recipient = _apply_transition(
                        RECIPIENT_STATE_MACHINE,
                        recipient,
                        acknowledgement,
                        tenant,
                        f"gateway:{attempt.id}:{acknowledgement}",
                        SYSTEM_ACTOR_ID,
                    )
                    recipient.accepted_at = attempt.accepted_at
                    if acknowledgement == "delivered":
                        recipient.delivered_at = attempt.completed_at
                    recipient.save()
                    attempt.save()
                    accepted_event = DeliveryEvent.objects.create(
                        tenant_id=tenant,
                        recipient=recipient,
                        attempt=attempt,
                        gateway_key=attempt.gateway_key,
                        provider_event_id=f"gateway:{attempt.id}:{acknowledgement}",
                        event_type=acknowledgement,
                        occurred_at=attempt.accepted_at or timezone.now(),
                        metadata={"source": "gateway_acknowledgement"},
                        correlation_id=get_correlation_id() or str(job_id),
                    )
                    cls._apply_event_truth(accepted_event, attempt)
                    _publish(
                        "email_marketing.email.sent.v1",
                        tenant,
                        "campaign_recipient",
                        recipient.id,
                        actor_id=None,
                        payload={
                            "attempt_id": str(attempt.id),
                            "gateway_key": attempt.gateway_key,
                        },
                        job_id=job_id,
                    )
                    cls._complete_campaign_if_finished(tenant, campaign.id, job_id)
                    return OperationResult.success(attempt, code="provider_acknowledged")
                attempt.status = acknowledgement
                attempt.error_code = f"provider_{acknowledgement}"[:64]
                attempt.error_detail = f"Provider reported terminal {acknowledgement}."
                attempt.completed_at = timezone.now()
                attempt.save()
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "bounce" if acknowledgement == "bounced" else "fail",
                    tenant,
                    f"gateway:{attempt.id}:{acknowledgement}",
                    SYSTEM_ACTOR_ID,
                )
                recipient.failed_at = attempt.completed_at
                recipient.last_error_code = attempt.error_code
                recipient.save()
                if acknowledgement == "bounced":
                    bounce_event = DeliveryEvent.objects.create(
                        tenant_id=tenant,
                        recipient=recipient,
                        attempt=attempt,
                        gateway_key=attempt.gateway_key,
                        provider_event_id=f"gateway:{attempt.id}:bounced",
                        event_type="bounced",
                        occurred_at=attempt.completed_at,
                        bounce_class=str(attempt.response_evidence.get("bounce_class", "hard")),
                        metadata={"source": "gateway_acknowledgement"},
                        correlation_id=get_correlation_id() or str(job_id),
                    )
                    cls._apply_event_truth(bounce_event, attempt)
                cls._complete_campaign_if_finished(tenant, campaign.id, job_id)
                return OperationResult.failure(
                    f"provider_{acknowledgement}",
                    detail=f"Provider reported {acknowledgement}.",
                )
            error_code = str(result.code or "delivery_unavailable")
            attempt.status = "timed_out" if result.ambiguous else "failed"
            attempt.error_code = error_code[:64]
            attempt.error_detail = str(result.detail or "Delivery failed.")[:1000]
            attempt.completed_at = timezone.now()
            attempt.save()
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "fail",
                tenant,
                f"fail:{attempt.id}",
                SYSTEM_ACTOR_ID,
            )
            recipient.last_error_code = attempt.error_code
            recipient.failed_at = attempt.completed_at
            recipient.save(update_fields=["last_error_code", "failed_at", "updated_at"])
            campaign.failed_count += 1
            campaign.save(update_fields=["failed_count", "updated_at"])
            cls._complete_campaign_if_finished(tenant, campaign.id, job_id)
            return OperationResult.failure(
                attempt.error_code.lower(),
                retryable=result.retryable,
                ambiguous=result.ambiguous,
                detail="Delivery gateway did not acknowledge the message.",
            )

    @classmethod
    @transaction.atomic
    def retry_recipient(
        cls,
        tenant_id: UUID,
        recipient_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
    ) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        if recipient.status != "failed" and not recipient.delivery_attempts.filter(status="deferred").exists():
            raise DomainConflict("Only failed or deferred recipients can be retried.")
        return enqueue(
            tenant,
            actor_id,
            "email_marketing.send_recipient",
            {
                "campaign_id": str(recipient.campaign_id),
                "recipient_id": str(recipient.id),
                "retry": True,
            },
            idempotency_key,
        )

    @classmethod
    @transaction.atomic
    def enqueue_verified_provider_event(cls, tenant_id: UUID, gateway_key: str, verified_event: object) -> AsyncJob:
        tenant = _uuid(tenant_id, "tenant_id")
        if gateway_key not in get_runtime_configuration(tenant).document["integrations"]["gateway_keys"]:
            raise ValidationError({"gateway_key": "This gateway is disabled by tenant configuration."})
        provider_event_id = str(getattr(verified_event, "provider_event_id", "")).strip()
        if not provider_event_id:
            raise ValidationError({"provider_event_id": "Verified provider event id is required."})
        as_mapping = getattr(verified_event, "as_mapping", None)
        if not callable(as_mapping):
            raise ValidationError({"event": "Verifier returned an unsupported event contract."})
        return enqueue(
            tenant,
            f"provider:{gateway_key}",
            "email_marketing.process_provider_event",
            {"gateway_key": gateway_key, "event": as_mapping()},
            f"provider-event:{gateway_key}:{provider_event_id}",
        )

    @classmethod
    @transaction.atomic
    def record_provider_event(cls, tenant_id: UUID, gateway_key: str, verified_event: object) -> DeliveryEvent:
        tenant = _uuid(tenant_id, "tenant_id")
        provider_event_id = str(getattr(verified_event, "provider_event_id"))
        existing = (
            DeliveryEvent.objects.for_tenant(tenant)
            .filter(gateway_key=gateway_key, provider_event_id=provider_event_id)
            .first()
        )
        if existing is not None:
            return existing
        provider_message_id = str(getattr(verified_event, "provider_message_id", ""))
        attempt = (
            DeliveryAttempt.objects.select_for_update()
            .filter(
                tenant_id=tenant,
                gateway_key=gateway_key,
                provider_message_id=provider_message_id,
            )
            .select_related("recipient__campaign")
            .first()
        )
        if attempt is None:
            raise NotFound("No tenant-bound delivery attempt matches this event.")
        event_type = str(getattr(verified_event, "event_type"))
        event = DeliveryEvent.objects.create(
            tenant_id=tenant,
            recipient=attempt.recipient,
            attempt=attempt,
            gateway_key=gateway_key,
            provider_event_id=provider_event_id,
            event_type=event_type,
            occurred_at=getattr(verified_event, "occurred_at"),
            link_url_hash=str(getattr(verified_event, "link_url_hash", "")),
            bounce_class=str(getattr(verified_event, "bounce_class", "")),
            metadata=dict(getattr(verified_event, "metadata", {}) or {}),
            correlation_id=str(
                getattr(
                    verified_event,
                    "correlation_id",
                    get_correlation_id() or "",
                )
            ),
        )
        cls._apply_event_truth(event, attempt)
        return event

    @classmethod
    def record_open(cls, tenant_id: UUID, tracking_token: str) -> DeliveryEvent:
        tenant = _uuid(tenant_id, "tenant_id")
        token_days = get_runtime_configuration(tenant).document["tokens"]["tracking_token_days"]
        payload = signing.loads(
            tracking_token,
            salt="email_marketing.tracking",
            max_age=token_days * 86_400,
        )
        if str(payload.get("tenant_id")) != str(tenant_id):
            raise NotFound("Tracking token is not valid for this tenant.")
        recipient_id = _uuid(payload.get("recipient_id"), "recipient_id")
        event_id = hashlib.sha256(f"open:{tracking_token}".encode()).hexdigest()
        event = type(
            "Verified",
            (),
            {
                "provider_event_id": event_id,
                "provider_message_id": payload.get("provider_message_id", ""),
                "event_type": "opened",
                "occurred_at": timezone.now(),
                "link_url_hash": "",
                "bounce_class": "",
                "metadata": {"source": "tracking"},
                "correlation_id": get_correlation_id() or "",
            },
        )()
        attempt = (
            DeliveryAttempt.objects.for_tenant(tenant_id)
            .filter(recipient_id=recipient_id)
            .order_by("-created_at")
            .first()
        )
        if attempt is None:
            raise NotFound("Tracking recipient has no accepted attempt.")
        event.provider_message_id = attempt.provider_message_id
        return cls.record_provider_event(tenant_id, attempt.gateway_key, event)

    @classmethod
    def record_click(cls, tenant_id: UUID, tracking_token: str, signed_destination: str) -> tuple[DeliveryEvent, str]:
        tenant = _uuid(tenant_id, "tenant_id")
        token_days = get_runtime_configuration(tenant).document["tokens"]["tracking_token_days"]
        destination = signing.loads(
            signed_destination,
            salt="email_marketing.destination",
            max_age=token_days * 86_400,
        )
        parsed = urlparse(str(destination))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("Signed destination is not a safe HTTP URL.")
        event = cls.record_open(tenant_id, tracking_token)
        # A distinct provider id keeps click truth independent of the open pixel.
        click = type(
            "Verified",
            (),
            {
                "provider_event_id": hashlib.sha256(
                    f"click:{tracking_token}:{signed_destination}".encode()
                ).hexdigest(),
                "provider_message_id": (event.attempt.provider_message_id if event.attempt else ""),
                "event_type": "clicked",
                "occurred_at": timezone.now(),
                "link_url_hash": hashlib.sha256(str(destination).encode()).hexdigest(),
                "bounce_class": "",
                "metadata": {"source": "tracking"},
                "correlation_id": get_correlation_id() or "",
            },
        )()
        return cls.record_provider_event(tenant_id, event.gateway_key, click), str(destination)

    @classmethod
    @transaction.atomic
    def unsubscribe(cls, tenant_id: UUID, signed_token: str, occurred_at: datetime) -> SuppressionEntry:
        tenant = _uuid(tenant_id, "tenant_id")
        token_days = get_runtime_configuration(tenant).document["tokens"]["unsubscribe_token_days"]
        payload = signing.loads(
            signed_token,
            salt="email_marketing.unsubscribe",
            max_age=token_days * 86_400,
        )
        if str(payload.get("tenant_id")) != str(tenant):
            raise NotFound("Unsubscribe token is not valid for this tenant.")
        recipient_id = _uuid(payload.get("recipient_id"), "recipient_id")
        try:
            recipient = CampaignRecipient.objects.select_for_update().get(tenant_id=tenant, pk=recipient_id)
        except CampaignRecipient.DoesNotExist as exc:
            raise NotFound("Recipient not found.") from exc
        configuration = get_runtime_configuration(tenant).document
        purpose = configuration["defaults"]["consent_purpose"]
        ComplianceService.revoke_consent(tenant, None, recipient.email, purpose, "unsubscribe")
        suppression = ComplianceService.suppress(
            tenant,
            SYSTEM_ACTOR_ID,
            {
                "email": recipient.email,
                "scope": configuration["compliance"]["suppression_scopes_by_purpose"][purpose][-1],
                "reason": configuration["compliance"]["automatic_suppression_reasons"]["unsubscribed"],
                "source": "user",
                "suppressed_at": occurred_at,
            },
        )
        if recipient.status not in {
            "complained",
            "bounced",
            "unsubscribed",
            "cancelled",
        }:
            if recipient.status == "sending":
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "accepted",
                    tenant,
                    f"unsubscribe-accept:{recipient.id}:{occurred_at.isoformat()}",
                    SYSTEM_ACTOR_ID,
                )
            _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                "unsubscribe",
                tenant,
                f"unsubscribe:{recipient.id}:{occurred_at.isoformat()}",
                SYSTEM_ACTOR_ID,
            )
        return suppression

    @classmethod
    def reconcile_ambiguous_attempt(cls, tenant_id: UUID, attempt_id: UUID) -> OperationResult[DeliveryAttempt]:
        tenant = _uuid(tenant_id, "tenant_id")
        try:
            attempt = DeliveryAttempt.objects.for_tenant(tenant).get(pk=attempt_id)
        except DeliveryAttempt.DoesNotExist as exc:
            raise NotFound("Delivery attempt not found.") from exc
        if attempt.status != "timed_out" or not attempt.provider_message_id:
            return OperationResult.failure(
                "not_reconcilable",
                detail="Only ambiguous attempts with a provider identifier can be reconciled.",
            )
        from .adapters import get_delivery_gateway

        result = get_delivery_gateway(attempt.gateway_key).lookup(attempt.provider_message_id)
        if not result.successful or result.value is None:
            return OperationResult.failure(
                result.code or "reconciliation_unavailable",
                retryable=result.retryable,
                ambiguous=result.ambiguous,
                detail=result.detail or "Provider reconciliation is unavailable.",
            )
        receipt = result.value
        acknowledgement = str(getattr(receipt, "acknowledgement", ""))
        if acknowledgement not in {
            "accepted",
            "delivered",
            "failed",
            "bounced",
        }:
            return OperationResult.failure(
                "ambiguous_delivery",
                ambiguous=True,
                detail="Provider status remains ambiguous.",
            )
        attempt.status = acknowledgement
        attempt.response_evidence = dict(getattr(receipt, "evidence", {}))
        attempt.completed_at = timezone.now() if acknowledgement != "accepted" else None
        attempt.save()
        return OperationResult.success(attempt, code="reconciled")

    @classmethod
    def _apply_event_truth(cls, event: DeliveryEvent, attempt: DeliveryAttempt) -> None:
        recipient = attempt.recipient
        campaign = recipient.campaign
        event_type = event.event_type
        configuration = get_runtime_configuration(event.tenant_id).document
        terminal = set(configuration["workflows"]["terminal_recipient_states"])
        status_map = configuration["workflows"]["provider_event_recipient_mapping"]
        target = status_map.get(event_type)
        if target and recipient.status not in terminal and recipient.status != target:
            command = configuration["workflows"]["provider_event_command_mapping"][event_type]
            if recipient.status == "sending" and command in {
                "delivered",
                "complain",
                "unsubscribe",
            }:
                recipient = _apply_transition(
                    RECIPIENT_STATE_MACHINE,
                    recipient,
                    "accepted",
                    event.tenant_id,
                    f"event-accepted:{event.id}",
                    SYSTEM_ACTOR_ID,
                )
            recipient = _apply_transition(
                RECIPIENT_STATE_MACHINE,
                recipient,
                command,
                event.tenant_id,
                f"event:{event.id}:{command}",
                SYSTEM_ACTOR_ID,
            )
            if target == "delivered":
                recipient.delivered_at = event.occurred_at
                recipient.save(update_fields=["delivered_at", "updated_at"])
        counter_map = {
            "accepted": "sent_count",
            "delivered": "delivered_count",
            "opened": "opened_count",
            "clicked": "clicked_count",
            "bounced": "bounced_count",
            "complained": "complaint_count",
            "unsubscribed": "unsubscribed_count",
        }
        field = counter_map.get(event_type)
        if field:
            setattr(campaign, field, int(getattr(campaign, field)) + 1)
        if (
            event_type == "opened"
            and not DeliveryEvent.objects.for_tenant(event.tenant_id)
            .filter(recipient=recipient, event_type="opened")
            .exclude(pk=event.pk)
            .exists()
        ):
            campaign.unique_opened_count += 1
        if (
            event_type == "clicked"
            and not DeliveryEvent.objects.for_tenant(event.tenant_id)
            .filter(recipient=recipient, event_type="clicked")
            .exclude(pk=event.pk)
            .exists()
        ):
            campaign.unique_clicked_count += 1
        campaign.save()
        if event_type in configuration["compliance"]["automatic_suppression_events"]:
            reason = configuration["compliance"]["automatic_suppression_reasons"][event_type]
            ComplianceService.suppress(
                event.tenant_id,
                None,
                {
                    "email": recipient.email,
                    "scope": "marketing",
                    "reason": reason,
                    "source": "provider_event",
                    "evidence_event": event,
                },
            )
        event_name = {
            "delivered": "email_marketing.email.delivered.v1",
            "opened": "email_marketing.email.opened.v1",
            "clicked": "email_marketing.email.clicked.v1",
            "bounced": "email_marketing.email.bounced.v1",
            "unsubscribed": "email_marketing.email.unsubscribed.v1",
        }.get(event_type)
        if event_name:
            _publish(
                event_name,
                event.tenant_id,
                "campaign_recipient",
                recipient.id,
                actor_id=None,
                payload={
                    "recipient_id": str(recipient.id),
                    "attempt_id": str(attempt.id),
                },
            )

    @staticmethod
    def _instrument_rendered(rendered: object, public_url: str, tracking_token: str) -> object:
        """Rewrite safe links and append an open pixel without storing raw URLs."""

        from .adapters import RenderedEmail

        html = str(getattr(rendered, "html", ""))

        def rewrite(match: re.Match[str]) -> str:
            destination = match.group(2)
            parsed = urlparse(destination)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return match.group(0)
            signed = signing.dumps(destination, salt="email_marketing.destination", compress=True)
            click_url = (
                f"{public_url}/api/v2/email-marketing/t/{quote(tracking_token, safe='')}/click/"
                f"?destination={quote(signed, safe='')}"
            )
            return f"{match.group(1)}{click_url}{match.group(3)}"

        rewritten = re.sub(
            r'(<a\b[^>]*\bhref=["\'])(https?://[^"\']+)(["\'])',
            rewrite,
            html,
            flags=re.IGNORECASE,
        )
        pixel = (
            f'<img src="{public_url}/api/v2/email-marketing/t/{quote(tracking_token, safe="")}/open.gif" '
            'width="1" height="1" alt="" style="display:none" />'
        )
        return RenderedEmail(
            subject=str(getattr(rendered, "subject")),
            html=f"{rewritten}{pixel}" if rewritten else "",
            text=str(getattr(rendered, "text", "")),
            preview_text=str(getattr(rendered, "preview_text", "")),
        )

    @classmethod
    def _complete_campaign_if_finished(cls, tenant_id: UUID, campaign_id: UUID, job_id: UUID) -> None:
        """Mark a sending campaign sent only after every recipient is terminal."""

        campaign = EmailCampaign.objects.select_for_update().get(tenant_id=tenant_id, pk=campaign_id)
        remaining = CampaignRecipient.objects.for_tenant(tenant_id).filter(
            campaign=campaign, status__in={"resolved", "queued", "sending"}
        )
        if campaign.status != "sending" or remaining.exists():
            return
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=["completed_at", "updated_at"])
        campaign = _apply_transition(
            CAMPAIGN_STATE_MACHINE,
            campaign,
            "complete",
            tenant_id,
            f"complete:{campaign.id}",
            SYSTEM_ACTOR_ID,
        )
        _publish(
            "email_marketing.campaign.sent.v1",
            tenant_id,
            "email_campaign",
            campaign.id,
            actor_id=None,
            job_id=job_id,
            payload={
                "sent_count": campaign.sent_count,
                "delivered_count": campaign.delivered_count,
                "failed_count": campaign.failed_count,
                "bounced_count": campaign.bounced_count,
                "status": campaign.status,
            },
        )


# Compatibility aliases preserve imports while routing legacy callers into the
# strict service implementation. They intentionally do not accept arbitrary
# ORM keyword arguments.
EmailCampaignService = CampaignService
EmailTemplateService = TemplateService


__all__ = [
    "AudienceCandidate",
    "AudienceResolutionResult",
    "AudienceService",
    "CampaignAnalytics",
    "CampaignPreflight",
    "CampaignService",
    "ComplianceService",
    "DeliveryService",
    "DomainConflict",
    "EligibilityDecision",
    "EmailCampaignService",
    "EmailTemplateService",
    "TemplateService",
    "normalize_email",
]

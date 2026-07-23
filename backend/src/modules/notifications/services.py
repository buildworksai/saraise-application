"""Tenant-safe notification domain services.

The API, workers, compatibility adapters, and paid modules all enter the
notification domain through these services.  This file deliberately contains
the validation and transitions: HTTP views are transport adapters only.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import re
import socket
import time as unix_time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from ipaddress import ip_address
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from src.core.async_jobs.services import enqueue as enqueue_job
from src.core.encryption import EncryptionService
from src.core.middleware.correlation import get_correlation_id

from .models import (
    Notification,
    NotificationConfiguration,
    NotificationConfigurationAudit,
    NotificationConfigurationVersion,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationEndpoint,
    NotificationPreference,
    NotificationTemplate,
    NotificationTemplateVersion,
)

logger = logging.getLogger(__name__)

CHANNELS = frozenset({"in_app", "email", "sms", "push", "webhook"})
MANDATORY_CATEGORIES = frozenset({"security_alerts", "password_reset"})
DIGEST_MODES = frozenset({"immediate", "hourly", "daily", "weekly"})
ENVIRONMENTS = frozenset({"development", "staging", "production"})
CONTENT_TYPES = frozenset({"text/plain", "text/html", "application/json"})
CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-[0-9]{3})?$")
VARIABLE_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
FORBIDDEN_TEMPLATE_RE = re.compile(r"{%|{#|\.|\[|\]|\(|\)|__|\b(import|include|extends|attr|class|self)\b")
SECRET_KEYS = frozenset({"secret", "password", "token", "credential", "api_key", "private_key"})


class NotificationServiceError(RuntimeError):
    """Stable domain failure suitable for API error translation."""

    def __init__(self, code: str, message: str, *, errors: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = dict(errors or {})


class CapabilityUnavailable(NotificationServiceError):
    """Raised when a configured provider capability is not actually available."""

    def __init__(self, message: str = "The configured notification capability is unavailable.") -> None:
        super().__init__("CAPABILITY_UNAVAILABLE", message)


@dataclass(frozen=True, slots=True)
class OperationResult:
    """A domain outcome carrying durable identifiers, never fabricated success."""

    operation_id: uuid.UUID
    status: str
    correlation_id: uuid.UUID
    object: object | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)


def _uuid(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise NotificationServiceError("INVALID_IDENTIFIER", f"{field_name} must be a UUID.") from exc


def identity_uuid(tenant_id: uuid.UUID | str, identity: object) -> uuid.UUID:
    """Map repository integer/string identities to stable tenant-bound UUIDs."""

    tenant = _uuid(tenant_id, "tenant_id")
    try:
        return _uuid(identity, "identity")  # type: ignore[arg-type]
    except NotificationServiceError:
        text = str(identity).strip()
        if not text:
            raise NotificationServiceError("ACTOR_REQUIRED", "An authenticated actor is required.")
        return uuid.uuid5(tenant, f"saraise-identity:{text}")


def _correlation_uuid() -> uuid.UUID:
    value = get_correlation_id()
    try:
        return uuid.UUID(str(value)) if value else uuid.uuid4()
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _required_text(value: object, name: str, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NotificationServiceError("VALIDATION_ERROR", f"{name} is required.", errors={name: "required"})
    normalized = value.strip()
    if maximum is not None and len(normalized) > maximum:
        raise NotificationServiceError("VALIDATION_ERROR", f"{name} exceeds {maximum} characters.", errors={name: "too_long"})
    return normalized


def _json_size(value: object) -> int:
    try:
        return len(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise NotificationServiceError("VALIDATION_ERROR", "Value must be JSON serializable.") from exc


def _schema_variables(schema: object) -> dict[str, dict[str, object]]:
    if not isinstance(schema, dict):
        raise NotificationServiceError("VALIDATION_ERROR", "variables_schema must be an object.", errors={"variables_schema": "invalid"})
    validated: dict[str, dict[str, object]] = {}
    for name, declaration in schema.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise NotificationServiceError("VALIDATION_ERROR", "Variable names must be simple identifiers.")
        if not isinstance(declaration, dict):
            raise NotificationServiceError("VALIDATION_ERROR", f"Variable {name} must have an object declaration.")
        unknown = set(declaration) - {"type", "required", "example"}
        if unknown:
            raise NotificationServiceError("VALIDATION_ERROR", f"Variable {name} contains unknown properties.")
        kind = declaration.get("type", "string")
        if kind not in {"string", "number", "integer", "boolean", "object", "array"}:
            raise NotificationServiceError("VALIDATION_ERROR", f"Variable {name} has an unsupported type.")
        validated[name] = {"type": kind, "required": bool(declaration.get("required", False)), **({"example": declaration["example"]} if "example" in declaration else {})}
    return validated


def validate_template(source: object, schema: Mapping[str, object], *, field_name: str) -> str:
    text = "" if source is None else str(source)
    if FORBIDDEN_TEMPLATE_RE.search(text):
        raise NotificationServiceError("UNSAFE_TEMPLATE", f"{field_name} uses an unsafe template expression.", errors={field_name: "unsafe_expression"})
    if text.count("{{") != text.count("}}"):
        raise NotificationServiceError("INVALID_TEMPLATE", f"{field_name} has invalid template syntax.", errors={field_name: "syntax"})
    declared = set(schema)
    referenced = set(VARIABLE_RE.findall(text))
    undeclared = referenced - declared
    if undeclared:
        raise NotificationServiceError("UNDECLARED_VARIABLE", f"Undeclared variables: {', '.join(sorted(undeclared))}.", errors={field_name: sorted(undeclared)})
    residual = VARIABLE_RE.sub("", text)
    if "{{" in residual or "}}" in residual:
        raise NotificationServiceError("INVALID_TEMPLATE", f"{field_name} has unsupported template syntax.")
    return text


def render_template(source: str, schema: Mapping[str, Mapping[str, object]], context: Mapping[str, object]) -> tuple[str, list[str], list[str]]:
    if not isinstance(context, Mapping):
        raise NotificationServiceError("VALIDATION_ERROR", "context must be an object.")
    required = {name for name, spec in schema.items() if spec.get("required")}
    referenced = set(VARIABLE_RE.findall(source))
    missing = sorted((required | referenced) - set(context))
    unused = sorted(set(context) - referenced)
    if missing:
        return source, missing, unused

    def replace(match: re.Match[str]) -> str:
        value = context[match.group(1)]
        if callable(value) or not isinstance(value, (str, int, float, bool, type(None))):
            raise NotificationServiceError("UNSAFE_CONTEXT", f"Variable {match.group(1)} is not a scalar value.")
        return "" if value is None else str(value)

    return VARIABLE_RE.sub(replace, source), [], unused


def _validate_url(url: str, allowed_hosts: Sequence[str], *, internal_allowed: bool = True) -> str:
    if not url:
        return ""
    if internal_allowed and url.startswith("/") and not url.startswith("//"):
        return url
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise NotificationServiceError("URL_NOT_ALLOWED", "URL must be an internal path or an allowlisted HTTPS URL.")
    if parsed.hostname.lower() not in {host.lower() for host in allowed_hosts}:
        raise NotificationServiceError("URL_NOT_ALLOWED", "URL host is not allowlisted.")
    return url


def _validate_public_webhook(url: str, allowed_hosts: Sequence[str]) -> str:
    value = _validate_url(url, allowed_hosts, internal_allowed=False)
    hostname = urlparse(value).hostname or ""
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise NotificationServiceError("ENDPOINT_DNS_FAILED", "Webhook hostname cannot be resolved.") from exc
    for raw in addresses:
        address = ip_address(raw)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise NotificationServiceError("ENDPOINT_PRIVATE_ADDRESS", "Webhook endpoints must resolve only to public addresses.")
    return value


def _log(event: str, **fields: object) -> None:
    safe = {key: value for key, value in fields.items() if key not in {"recipient", "body", "context", "token", "credential"}}
    logger.info(event, extra={"event": event, **safe})


class NotificationTemplateService:
    @staticmethod
    def preview_unsaved(tenant_id: uuid.UUID | str, data: Mapping[str, object], context: Mapping[str, object]) -> dict[str, object]:
        """Render proposed content without creating a template or version."""

        _uuid(tenant_id, "tenant_id")
        schema = _schema_variables(data.get("variables_schema", {}))
        subject_source = validate_template(data.get("subject_template", ""), schema, field_name="subject_template")
        body_source = validate_template(_required_text(data.get("body_template"), "body_template"), schema, field_name="body_template")
        subject, subject_missing, subject_unused = render_template(subject_source, schema, context)
        body, body_missing, body_unused = render_template(body_source, schema, context)
        missing = sorted(set(subject_missing + body_missing))
        diagnostics = [{"level": "error", "variable": name, "message": f"Required variable {name} is missing."} for name in missing]
        return {"subject": subject if not missing else "", "body": body if not missing else "", "content_type": str(data.get("content_type", "text/plain")), "missing_variables": missing, "unused_variables": sorted(set(subject_unused) & set(body_unused)), "diagnostics": diagnostics, "valid": not missing, "persisted": False}

    @staticmethod
    @transaction.atomic
    def create_template(tenant_id: uuid.UUID | str, actor_id: object, data: Mapping[str, object], idempotency_key: str) -> NotificationTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = identity_uuid(tenant, actor_id)
        _required_text(idempotency_key, "idempotency_key", 255)
        code = _required_text(data.get("code"), "code", 100).lower()
        category = _required_text(data.get("category"), "category", 100).lower()
        if not CODE_RE.fullmatch(code) or not CODE_RE.fullmatch(category):
            raise NotificationServiceError("VALIDATION_ERROR", "code and category must be lowercase identifiers.")
        channel = str(data.get("channel", ""))
        if channel not in CHANNELS:
            raise NotificationServiceError("VALIDATION_ERROR", "channel is invalid.")
        locale = str(data.get("locale", "en"))
        if not LOCALE_RE.fullmatch(locale):
            raise NotificationServiceError("VALIDATION_ERROR", "locale is invalid.")
        schema = _schema_variables(data.get("variables_schema", {}))
        subject = str(data.get("subject_template", ""))
        body = _required_text(data.get("body_template"), "body_template")
        if channel == "email" and not subject.strip():
            raise NotificationServiceError("VALIDATION_ERROR", "subject_template is required for email.")
        subject = validate_template(subject, schema, field_name="subject_template")
        body = validate_template(body, schema, field_name="body_template")
        content_type = str(data.get("content_type", "text/plain"))
        if content_type not in CONTENT_TYPES or (channel == "sms" and content_type != "text/plain"):
            raise NotificationServiceError("VALIDATION_ERROR", "content_type is not permitted for this channel.")
        try:
            template = NotificationTemplate.objects.for_tenant(tenant).create(
                tenant_id=tenant, code=code, name=_required_text(data.get("name"), "name", 255),
                category=category, channel=channel, locale=locale, created_by=actor, updated_by=actor,
            )
            version = NotificationTemplateVersion.objects.for_tenant(tenant).create(
                tenant_id=tenant, template=template, version=1, subject_template=subject,
                body_template=body, variables_schema=schema, content_type=content_type,
                created_by=actor, correlation_id=_correlation_uuid(),
            )
        except IntegrityError as exc:
            raise NotificationServiceError("CONFLICT", "An active template with this code, channel, and locale already exists.") from exc
        _log("notification.template.created", tenant_id=str(tenant), actor_id=str(actor), template_id=str(template.id), channel=channel)
        template.initial_version = version  # type: ignore[attr-defined]
        return template

    @staticmethod
    def list_templates(tenant_id: uuid.UUID | str, filters: Mapping[str, object] | None = None) -> QuerySet[NotificationTemplate]:
        tenant = _uuid(tenant_id, "tenant_id")
        query = NotificationTemplate.objects.for_tenant(tenant).select_related("active_version")
        values = filters or {}
        for field_name in ("channel", "category", "locale", "status"):
            if values.get(field_name):
                query = query.filter(**{field_name: values[field_name]})
        if values.get("search"):
            search = str(values["search"])[:100]
            query = query.filter(Q(code__icontains=search) | Q(name__icontains=search) | Q(category__icontains=search))
        return query.order_by("code", "channel", "locale")

    @staticmethod
    def get_template(tenant_id: uuid.UUID | str, template_id: uuid.UUID | str) -> NotificationTemplate:
        return NotificationTemplate.objects.for_tenant(_uuid(tenant_id, "tenant_id")).select_related("active_version").get(pk=_uuid(template_id, "template_id"))

    @classmethod
    @transaction.atomic
    def create_version(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, actor_id: object, changes: Mapping[str, object]) -> NotificationTemplateVersion:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = identity_uuid(tenant, actor_id)
        template = NotificationTemplate.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(template_id, "template_id"))
        latest = NotificationTemplateVersion.objects.for_tenant(tenant).filter(template=template).order_by("-version").first()
        if latest is None:
            raise NotificationServiceError("INTEGRITY_ERROR", "Template has no source version.")
        schema = _schema_variables(changes.get("variables_schema", latest.variables_schema))
        subject = validate_template(changes.get("subject_template", latest.subject_template), schema, field_name="subject_template")
        body = validate_template(changes.get("body_template", latest.body_template), schema, field_name="body_template")
        content_type = str(changes.get("content_type", latest.content_type))
        if template.channel == "email" and not subject.strip():
            raise NotificationServiceError("VALIDATION_ERROR", "subject_template is required for email.")
        version = NotificationTemplateVersion.objects.for_tenant(tenant).create(
            tenant_id=tenant, template=template, version=latest.version + 1,
            subject_template=subject, body_template=body, variables_schema=schema,
            content_type=content_type, created_by=actor, correlation_id=_correlation_uuid(),
        )
        if "name" in changes: template.name = _required_text(changes["name"], "name", 255)
        if "category" in changes: template.category = _required_text(changes["category"], "category", 100).lower()
        template.updated_by = actor
        template.save(update_fields=["name", "category", "updated_by", "updated_at"])
        _log("notification.template.versioned", tenant_id=str(tenant), actor_id=str(actor), template_id=str(template.id), version=version.version)
        return version

    @classmethod
    def preview(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, version_id: uuid.UUID | str | None, context: Mapping[str, object]) -> dict[str, object]:
        template = cls.get_template(tenant_id, template_id)
        versions = NotificationTemplateVersion.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(template=template)
        version = versions.get(pk=_uuid(version_id, "version_id")) if version_id else versions.order_by("-version").first()
        if version is None:
            raise NotificationServiceError("NOT_FOUND", "Template version not found.")
        subject, subject_missing, subject_unused = render_template(version.subject_template, version.variables_schema, context)
        body, body_missing, body_unused = render_template(version.body_template, version.variables_schema, context)
        missing = sorted(set(subject_missing + body_missing))
        diagnostics = [{"level": "error", "variable": name, "message": f"Required variable {name} is missing."} for name in missing]
        return {"template_id": template.id, "version_id": version.id, "subject": subject if not missing else "", "body": body if not missing else "", "content_type": version.content_type, "missing_variables": missing, "unused_variables": sorted(set(subject_unused) & set(body_unused)), "diagnostics": diagnostics, "valid": not missing}

    @classmethod
    @transaction.atomic
    def activate(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, version_id: uuid.UUID | str, actor_id: object, transition_key: str) -> NotificationTemplate:
        tenant = _uuid(tenant_id, "tenant_id")
        template = cls.get_template(tenant, template_id)
        version = NotificationTemplateVersion.objects.for_tenant(tenant).get(pk=_uuid(version_id, "version_id"), template=template)
        from .state_machines import TEMPLATE_STATE_MACHINE
        if template.status == "active":
            if any(item.get("transition_key") == transition_key and item.get("command") in {"activate", "rollback"} for item in template.transition_history):
                return template
            template.active_version = version
            template.updated_by = identity_uuid(tenant, actor_id)
            template.transition_history = [*template.transition_history, {"transition_key": transition_key, "command": "activate", "from_state": "active", "to_state": "active", "occurred_at": timezone.now().isoformat(), "metadata": {"version_id": str(version.id)}}]
            template.save(update_fields=["active_version", "updated_by", "transition_history", "updated_at"])
        else:
            template = TEMPLATE_STATE_MACHINE.apply(template, "activate", transition_key=transition_key, tenant_id=tenant, metadata={"version_id": str(version.id)})
            template.active_version = version
            template.updated_by = identity_uuid(tenant, actor_id)
            template.save(update_fields=["active_version", "updated_by", "updated_at"])
        _log("notification.template.activated", tenant_id=str(tenant), template_id=str(template.id), version=version.version)
        return template

    @classmethod
    def archive(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, actor_id: object, transition_key: str) -> NotificationTemplate:
        tenant = _uuid(tenant_id, "tenant_id"); template = cls.get_template(tenant, template_id)
        from .state_machines import TEMPLATE_STATE_MACHINE
        result = TEMPLATE_STATE_MACHINE.apply(template, "archive", transition_key=transition_key, tenant_id=tenant)
        result.updated_by = identity_uuid(tenant, actor_id); result.save(update_fields=["updated_by", "updated_at"])
        _log("notification.template.archived", tenant_id=str(tenant), template_id=str(result.id)); return result

    @classmethod
    def restore(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, actor_id: object, transition_key: str) -> NotificationTemplate:
        tenant = _uuid(tenant_id, "tenant_id"); template = cls.get_template(tenant, template_id)
        from .state_machines import TEMPLATE_STATE_MACHINE
        result = TEMPLATE_STATE_MACHINE.apply(template, "restore", transition_key=transition_key, tenant_id=tenant)
        result.active_version = None; result.updated_by = identity_uuid(tenant, actor_id); result.save(update_fields=["active_version", "updated_by", "updated_at"]); return result

    @classmethod
    def rollback(cls, tenant_id: uuid.UUID | str, template_id: uuid.UUID | str, version_id: uuid.UUID | str, actor_id: object, transition_key: str) -> NotificationTemplate:
        result = cls.activate(tenant_id, template_id, version_id, actor_id, transition_key)
        _log("notification.template.rolled_back", tenant_id=str(result.tenant_id), template_id=str(result.id), version_id=str(result.active_version_id)); return result


class NotificationConfigurationService:
    SCHEMA_VERSION = 1

    @classmethod
    def safe_default(cls) -> dict[str, object]:
        channel = {"enabled": False, "adapter_key": "unavailable", "credential_ref": "", "sender_ref": "", "timeout_seconds": 10, "retry": {"max_attempts": 3, "base_seconds": 30, "maximum_seconds": 3600}, "circuit": {"failure_threshold": 5, "reset_seconds": 60}, "rate_limit_per_minute": 60}
        channels = {name: copy.deepcopy(channel) for name in CHANNELS}
        channels["in_app"].update({"enabled": True, "adapter_key": "in_app", "timeout_seconds": 5, "credential_ref": "", "sender_ref": "system"})
        return {"schema_version": cls.SCHEMA_VERSION, "channels": channels, "preferences": {"default_enabled": True, "mandatory_categories": sorted(MANDATORY_CATEGORIES)}, "batch_size": 100, "max_attempts": 3, "backoff": {"base_seconds": 30, "maximum_seconds": 3600}, "retention": {"delivery_days": 365, "inbox_days": 365}, "limits": {"context_bytes": 32768, "metadata_bytes": 16384}, "allowed_action_url_hosts": [], "allowed_webhook_hosts": [], "feature_flags": {}, "digest_schedules": {"hourly_minute": 0, "daily_time": "09:00", "weekly_day": 1}, "quiet_hours": {"start": None, "end": None, "timezone": "UTC"}, "provider_callbacks": {"timestamp_tolerance_seconds": 300}}

    @classmethod
    def validate_document(cls, tenant_id: uuid.UUID | str, document: object) -> dict[str, str]:
        _uuid(tenant_id, "tenant_id")
        errors: dict[str, str] = {}
        if not isinstance(document, dict):
            return {"document": "must be an object"}
        allowed = set(cls.safe_default())
        missing = allowed - set(document)
        if missing:
            errors["document.required"] = f"missing properties: {', '.join(sorted(missing))}"
        if set(document) - allowed:
            errors["document"] = f"unknown properties: {', '.join(sorted(set(document) - allowed))}"
        if document.get("schema_version") != cls.SCHEMA_VERSION:
            errors["schema_version"] = f"must equal {cls.SCHEMA_VERSION}"
        def bounded(path: str, value: object, low: int, high: int) -> None:
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high: errors[path] = f"must be between {low} and {high}"
        bounded("batch_size", document.get("batch_size"), 1, 500)
        bounded("max_attempts", document.get("max_attempts"), 1, 10)
        backoff = document.get("backoff", {})
        if not isinstance(backoff, dict): errors["backoff"] = "must be an object"
        else:
            bounded("backoff.base_seconds", backoff.get("base_seconds"), 1, 3600); bounded("backoff.maximum_seconds", backoff.get("maximum_seconds"), 60, 86400)
            if isinstance(backoff.get("base_seconds"), int) and isinstance(backoff.get("maximum_seconds"), int) and backoff["base_seconds"] > backoff["maximum_seconds"]: errors["backoff.maximum_seconds"] = "must not be less than base_seconds"
        retention = document.get("retention", {})
        if isinstance(retention, dict):
            bounded("retention.delivery_days", retention.get("delivery_days"), 7, 3650); bounded("retention.inbox_days", retention.get("inbox_days"), 7, 3650)
        else: errors["retention"] = "must be an object"
        limits = document.get("limits", {})
        if isinstance(limits, dict):
            bounded("limits.context_bytes", limits.get("context_bytes"), 16384, 65536); bounded("limits.metadata_bytes", limits.get("metadata_bytes"), 16384, 65536)
        else: errors["limits"] = "must be an object"
        channels = document.get("channels")
        if not isinstance(channels, dict) or set(channels) != CHANNELS: errors["channels"] = "must declare every canonical channel"
        else:
            for name, raw in channels.items():
                if not isinstance(raw, dict): errors[f"channels.{name}"] = "must be an object"; continue
                required = {"enabled", "adapter_key", "credential_ref", "sender_ref", "timeout_seconds", "retry", "circuit", "rate_limit_per_minute"}
                permitted = required | {"allowed_hosts", "base_url", "from_email"}
                if set(raw) - permitted: errors[f"channels.{name}.unknown"] = "contains unknown channel settings"
                if not required.issubset(raw): errors[f"channels.{name}"] = "missing required channel settings"
                if not isinstance(raw.get("enabled"), bool): errors[f"channels.{name}.enabled"] = "must be a boolean"
                adapter_key = raw.get("adapter_key")
                if not isinstance(adapter_key, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", adapter_key): errors[f"channels.{name}.adapter_key"] = "must be a registered adapter identifier"
                for ref_name in ("credential_ref", "sender_ref"):
                    reference = raw.get(ref_name)
                    if not isinstance(reference, str) or len(reference) > 255: errors[f"channels.{name}.{ref_name}"] = "must be a string of at most 255 characters"
                credential_ref = raw.get("credential_ref")
                if credential_ref and not re.fullmatch(r"(?:vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+", str(credential_ref)): errors[f"channels.{name}.credential_ref"] = "must use an approved secret-manager URI"
                bounded(f"channels.{name}.timeout_seconds", raw.get("timeout_seconds"), 1, 120); bounded(f"channels.{name}.rate_limit_per_minute", raw.get("rate_limit_per_minute"), 1, 100000)
                retry = raw.get("retry")
                if not isinstance(retry, dict) or set(retry) != {"max_attempts", "base_seconds", "maximum_seconds"}: errors[f"channels.{name}.retry"] = "must declare max_attempts, base_seconds, and maximum_seconds"
                else:
                    bounded(f"channels.{name}.retry.max_attempts", retry.get("max_attempts"), 1, 10); bounded(f"channels.{name}.retry.base_seconds", retry.get("base_seconds"), 1, 3600); bounded(f"channels.{name}.retry.maximum_seconds", retry.get("maximum_seconds"), 60, 86400)
                    if isinstance(retry.get("base_seconds"), int) and isinstance(retry.get("maximum_seconds"), int) and retry["base_seconds"] > retry["maximum_seconds"]: errors[f"channels.{name}.retry.maximum_seconds"] = "must not be less than base_seconds"
                circuit = raw.get("circuit")
                if not isinstance(circuit, dict) or set(circuit) != {"failure_threshold", "reset_seconds"}: errors[f"channels.{name}.circuit"] = "must declare failure_threshold and reset_seconds"
                else:
                    bounded(f"channels.{name}.circuit.failure_threshold", circuit.get("failure_threshold"), 1, 100); bounded(f"channels.{name}.circuit.reset_seconds", circuit.get("reset_seconds"), 1, 86400)
                hosts = raw.get("allowed_hosts")
                if hosts is not None and (not isinstance(hosts, list) or any(not isinstance(host, str) or not host or "/" in host for host in hosts)): errors[f"channels.{name}.allowed_hosts"] = "must be a hostname list"
                for key in raw:
                    if key.lower() in SECRET_KEYS or any(word in key.lower() for word in ("password", "token", "api_key")): errors[f"channels.{name}.{key}"] = "inline credentials are forbidden"
        for key in ("allowed_action_url_hosts", "allowed_webhook_hosts"):
            hosts = document.get(key)
            if not isinstance(hosts, list) or any(not isinstance(host, str) or not host or "/" in host for host in hosts): errors[key] = "must be a hostname list"
        preferences = document.get("preferences")
        if not isinstance(preferences, dict) or set(preferences) != {"default_enabled", "mandatory_categories"}: errors["preferences"] = "must declare default_enabled and mandatory_categories"
        else:
            if not isinstance(preferences.get("default_enabled"), bool): errors["preferences.default_enabled"] = "must be a boolean"
            mandatory = preferences.get("mandatory_categories")
            if not isinstance(mandatory, list) or any(not isinstance(item, str) or not CODE_RE.fullmatch(item) for item in mandatory): errors["preferences.mandatory_categories"] = "must be a list of category identifiers"
            elif not MANDATORY_CATEGORIES.issubset(mandatory): errors["preferences.mandatory_categories"] = "must include the platform security categories"
        flags = document.get("feature_flags")
        if not isinstance(flags, dict): errors["feature_flags"] = "must be an object"
        else:
            for name, rule in flags.items():
                if not isinstance(name, str) or not CODE_RE.fullmatch(name) or not isinstance(rule, dict) or set(rule) != {"enabled", "tenant_ids", "roles", "cohorts"}: errors[f"feature_flags.{name}"] = "must be a closed rollout object"; continue
                if not isinstance(rule.get("enabled"), bool): errors[f"feature_flags.{name}.enabled"] = "must be a boolean"
                for target in ("tenant_ids", "roles", "cohorts"):
                    if not isinstance(rule.get(target), list) or any(not isinstance(item, str) or not item for item in rule[target]): errors[f"feature_flags.{name}.{target}"] = "must be a string list"
        digest = document.get("digest_schedules")
        if not isinstance(digest, dict) or set(digest) != {"hourly_minute", "daily_time", "weekly_day"}: errors["digest_schedules"] = "must declare hourly_minute, daily_time, and weekly_day"
        else:
            bounded("digest_schedules.hourly_minute", digest.get("hourly_minute"), 0, 59); bounded("digest_schedules.weekly_day", digest.get("weekly_day"), 1, 7)
            if not isinstance(digest.get("daily_time"), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", digest["daily_time"]): errors["digest_schedules.daily_time"] = "must be HH:MM"
        quiet = document.get("quiet_hours", {})
        if not isinstance(quiet, dict): errors["quiet_hours"] = "must be an object"
        else:
            start, end = quiet.get("start"), quiet.get("end")
            if (start is None) != (end is None): errors["quiet_hours"] = "start and end must both be set or null"
            for field_name, value in (("start", start), ("end", end)):
                if value is not None and (not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)): errors[f"quiet_hours.{field_name}"] = "must be HH:MM or null"
            try: ZoneInfo(str(quiet.get("timezone", "")))
            except (ValueError, ZoneInfoNotFoundError): errors["quiet_hours.timezone"] = "must be an IANA timezone"
        callbacks = document.get("provider_callbacks", {})
        if not isinstance(callbacks, dict): errors["provider_callbacks"] = "must be an object"
        else: bounded("provider_callbacks.timestamp_tolerance_seconds", callbacks.get("timestamp_tolerance_seconds"), 30, 900)
        if _json_size(document) > 262144: errors["document"] = "configuration exceeds 256 KiB"
        return errors

    @classmethod
    @transaction.atomic
    def get_or_create_default(cls, tenant_id: uuid.UUID | str, environment: str, actor_id: object) -> NotificationConfiguration:
        tenant = _uuid(tenant_id, "tenant_id"); actor = identity_uuid(tenant, actor_id)
        if environment not in ENVIRONMENTS: raise NotificationServiceError("VALIDATION_ERROR", "environment is invalid.")
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        if config: return config
        return cls._write_new(tenant, environment, actor, cls.safe_default(), "Initial safe configuration", "created")

    @classmethod
    def _diff(cls, before: object, after: object) -> list[dict[str, object]]:
        if before == after: return []
        if isinstance(before, dict) and isinstance(after, dict):
            result: list[dict[str, object]] = []
            for key in sorted(set(before) | set(after)):
                path = f"/{key.replace('~', '~0').replace('/', '~1')}"
                if key not in before: result.append({"op": "add", "path": path, "value": after[key]})
                elif key not in after: result.append({"op": "remove", "path": path})
                elif before[key] != after[key]: result.append({"op": "replace", "path": path, "value": after[key]})
            return result
        return [{"op": "replace", "path": "/", "value": after}]

    @classmethod
    def _write_new(cls, tenant: uuid.UUID, environment: str, actor: uuid.UUID, document: dict[str, object], reason: str, action: str) -> NotificationConfiguration:
        errors = cls.validate_document(tenant, document)
        if errors: raise NotificationServiceError("CONFIGURATION_INVALID", "Configuration is invalid.", errors=errors)
        config = NotificationConfiguration.objects.for_tenant(tenant).select_for_update().filter(environment=environment).first()
        prior = copy.deepcopy(config.document) if config else {}
        version_number = (config.active_version + 1) if config else 1
        if config is None:
            config = NotificationConfiguration.objects.create(tenant_id=tenant, environment=environment, active_version=version_number, document=document, created_by=actor, updated_by=actor)
        else:
            config.active_version = version_number; config.document = document; config.updated_by = actor; config.save(update_fields=["active_version", "document", "updated_by", "updated_at"])
        previous = NotificationConfigurationVersion.objects.for_tenant(tenant).filter(configuration=config).order_by("-version").first()
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        version = NotificationConfigurationVersion.objects.create(tenant_id=tenant, configuration=config, version=version_number, document=document, checksum=hashlib.sha256(raw).hexdigest(), previous_version_id=previous.id if previous else None, created_by=actor, correlation_id=_correlation_uuid(), change_reason=reason)
        NotificationConfigurationAudit.objects.create(tenant_id=tenant, configuration=config, version=version, action=action, diff=cls._diff(prior, document), actor_id=actor, correlation_id=version.correlation_id)
        _log(f"notification.configuration.{action}", tenant_id=str(tenant), actor_id=str(actor), configuration_id=str(config.id), version=version_number)
        return config

    @classmethod
    @transaction.atomic
    def update(cls, tenant_id: uuid.UUID | str, environment: str, actor_id: object, document: object, reason: str) -> NotificationConfiguration:
        tenant = _uuid(tenant_id, "tenant_id"); actor = identity_uuid(tenant, actor_id)
        if environment not in ENVIRONMENTS or not isinstance(document, dict): raise NotificationServiceError("VALIDATION_ERROR", "Invalid environment or document.")
        return cls._write_new(tenant, environment, actor, copy.deepcopy(document), _required_text(reason, "reason", 500), "updated")

    @classmethod
    def simulate(cls, tenant_id: uuid.UUID | str, proposed_document: object, scenario: Mapping[str, object]) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id"); errors = cls.validate_document(tenant, proposed_document)
        if errors: return {"valid": False, "errors": errors, "diff": [], "changes": [], "outcome": "rejected", "decision": "rejected", "warnings": list(errors.values())}
        current = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=scenario.get("environment", "production")).first()
        channel = str(scenario.get("channel", "in_app")); doc = proposed_document if isinstance(proposed_document, dict) else {}
        enabled = bool(doc.get("channels", {}).get(channel, {}).get("enabled", False)) if isinstance(doc.get("channels"), dict) else False
        diff = cls._diff(current.document if current else {}, doc)
        changes = [{"path": item["path"], "before": None, "after": item.get("value"), "impact": "configuration policy changes"} for item in diff]
        return {"valid": True, "errors": {}, "diff": diff, "changes": changes, "outcome": "dispatch" if enabled else "suppressed", "decision": "dispatch" if enabled else "suppressed", "warnings": [], "channel": channel}

    @classmethod
    def history(cls, tenant_id: uuid.UUID | str, environment: str) -> QuerySet[NotificationConfigurationVersion]:
        tenant = _uuid(tenant_id, "tenant_id")
        return NotificationConfigurationVersion.objects.for_tenant(tenant).filter(configuration__tenant_id=tenant, configuration__environment=environment).order_by("-version")

    @classmethod
    @transaction.atomic
    def rollback(cls, tenant_id: uuid.UUID | str, environment: str, version: int, actor_id: object, reason: str) -> NotificationConfiguration:
        tenant = _uuid(tenant_id, "tenant_id"); actor = identity_uuid(tenant, actor_id)
        source = cls.history(tenant, environment).get(version=version)
        return cls._write_new(tenant, environment, actor, copy.deepcopy(source.document), _required_text(reason, "reason", 500), "rolled_back")

    @classmethod
    def export_document(cls, tenant_id: uuid.UUID | str, environment: str) -> dict[str, object]:
        config = NotificationConfiguration.objects.for_tenant(_uuid(tenant_id, "tenant_id")).get(environment=environment)
        document = copy.deepcopy(config.document)
        for channel in document.get("channels", {}).values() if isinstance(document.get("channels"), dict) else []:
            if isinstance(channel, dict) and channel.get("credential_ref"): channel["credential_ref"] = "[configured]"
        version = NotificationConfigurationVersion.objects.for_tenant(config.tenant_id).filter(configuration=config, version=config.active_version).first()
        return {"schema_version": cls.SCHEMA_VERSION, "environment": environment, "configuration": document, "checksum": version.checksum if version else "", "exported_at": timezone.now().isoformat()}

    @classmethod
    def import_document(cls, tenant_id: uuid.UUID | str, environment: str, actor_id: object, document: object, dry_run: bool) -> dict[str, object] | NotificationConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        payload = document.get("configuration") if isinstance(document, dict) and "configuration" in document else document
        errors = cls.validate_document(tenant, payload)
        if dry_run:
            diff = cls._diff(
                NotificationConfiguration.objects.for_tenant(tenant).filter(environment=environment).values_list("document", flat=True).first() or {},
                payload if isinstance(payload, dict) else {},
            )
            result: dict[str, object] = {"valid": not errors, "errors": errors, "would_write": False, "diff": diff, "changes": [{"path": item["path"], "before": None, "after": item.get("value"), "impact": "configuration import"} for item in diff], "decision": "accepted" if not errors else "rejected", "warnings": list(errors.values())}
            if not errors and isinstance(payload, dict): result["document"] = copy.deepcopy(payload)
            return result
        if errors or not isinstance(payload, dict): raise NotificationServiceError("CONFIGURATION_INVALID", "Configuration import is invalid.", errors=errors)
        with transaction.atomic(): return cls._write_new(tenant, environment, identity_uuid(tenant, actor_id), copy.deepcopy(payload), "Imported configuration", "imported")

    @classmethod
    def effective_feature_flags(cls, tenant_id: uuid.UUID | str, identity: Mapping[str, object]) -> dict[str, bool]:
        tenant = _uuid(tenant_id, "tenant_id"); environment = str(identity.get("environment", "production"))
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=environment).first()
        if not config: return {}
        result: dict[str, bool] = {}
        roles = set(identity.get("roles", [])) if isinstance(identity.get("roles"), list) else set()
        cohorts = set(identity.get("cohorts", [])) if isinstance(identity.get("cohorts"), list) else set()
        for name, rule in config.document.get("feature_flags", {}).items():
            if not isinstance(rule, dict): continue
            result[name] = bool(rule.get("enabled")) and (not rule.get("roles") or bool(roles & set(rule["roles"]))) and (not rule.get("cohorts") or bool(cohorts & set(rule["cohorts"])))
        return result


class NotificationPreferenceService:
    @staticmethod
    def list_for_user(tenant_id: uuid.UUID | str, user_id: object) -> QuerySet[NotificationPreference]:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id)
        return NotificationPreference.objects.for_tenant(tenant).filter(user_id=user).order_by("channel", "category")

    @classmethod
    def get_effective(cls, tenant_id: uuid.UUID | str, user_id: object, channel: str, category: str) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id)
        if channel not in CHANNELS: raise NotificationServiceError("VALIDATION_ERROR", "channel is invalid.")
        stored = NotificationPreference.objects.for_tenant(tenant).filter(user_id=user, channel=channel, category=category).first()
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        defaults = (config.document.get("preferences", {}) if config else NotificationConfigurationService.safe_default()["preferences"])
        enabled = bool(defaults.get("default_enabled", True)) if isinstance(defaults, dict) else True
        data = {"channel": channel, "category": category, "enabled": enabled, "digest_mode": "immediate", "quiet_hours_start": None, "quiet_hours_end": None, "timezone": "UTC", "is_default": stored is None}
        if stored:
            data.update({"enabled": stored.enabled, "digest_mode": stored.digest_mode, "quiet_hours_start": stored.quiet_hours_start, "quiet_hours_end": stored.quiet_hours_end, "timezone": stored.timezone})
        if category in MANDATORY_CATEGORIES: data["enabled"] = True; data["mandatory"] = True
        return data

    @classmethod
    def _validate(cls, data: Mapping[str, object]) -> dict[str, object]:
        channel = str(data.get("channel", "")); category = _required_text(data.get("category"), "category", 100).lower(); digest = str(data.get("digest_mode", "immediate"))
        if channel not in CHANNELS or digest not in DIGEST_MODES or not CODE_RE.fullmatch(category): raise NotificationServiceError("VALIDATION_ERROR", "Invalid channel, category, or digest_mode.")
        enabled = bool(data.get("enabled", True))
        if category in MANDATORY_CATEGORIES and not enabled: raise NotificationServiceError("MANDATORY_CATEGORY", "Mandatory security categories cannot be disabled.")
        start, end = data.get("quiet_hours_start"), data.get("quiet_hours_end")
        if (start is None) != (end is None): raise NotificationServiceError("VALIDATION_ERROR", "Quiet hour start and end must both be set or null.")
        tz = str(data.get("timezone", "UTC"))
        try: ZoneInfo(tz)
        except (ValueError, ZoneInfoNotFoundError) as exc: raise NotificationServiceError("VALIDATION_ERROR", "timezone must be a valid IANA name.") from exc
        return {"channel": channel, "category": category, "enabled": enabled, "digest_mode": digest, "quiet_hours_start": start, "quiet_hours_end": end, "timezone": tz}

    @classmethod
    @transaction.atomic
    def upsert(cls, tenant_id: uuid.UUID | str, user_id: object, actor_id: object, data: Mapping[str, object]) -> NotificationPreference:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); identity_uuid(tenant, actor_id); values = cls._validate(data)
        preference, _ = NotificationPreference.objects.for_tenant(tenant).update_or_create(user_id=user, channel=values.pop("channel"), category=values.pop("category"), defaults={"tenant_id": tenant, **values})
        _log("notification.preference.updated", tenant_id=str(tenant), user_id=str(user), channel=preference.channel, category=preference.category); return preference

    @classmethod
    @transaction.atomic
    def bulk_replace(cls, tenant_id: uuid.UUID | str, user_id: object, actor_id: object, preferences: Sequence[Mapping[str, object]]) -> list[NotificationPreference]:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); identity_uuid(tenant, actor_id)
        if not isinstance(preferences, Sequence) or len(preferences) > 500: raise NotificationServiceError("VALIDATION_ERROR", "preferences must contain at most 500 rows.")
        validated = [cls._validate(item) for item in preferences]
        keys = [(item["channel"], item["category"]) for item in validated]
        if len(keys) != len(set(keys)): raise NotificationServiceError("VALIDATION_ERROR", "Preference document contains duplicates.")
        NotificationPreference.objects.for_tenant(tenant).filter(user_id=user).delete()
        return [NotificationPreference.objects.create(tenant_id=tenant, user_id=user, **item) for item in validated]

    @classmethod
    @transaction.atomic
    def reset(cls, tenant_id: uuid.UUID | str, user_id: object, actor_id: object) -> list[dict[str, object]]:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); identity_uuid(tenant, actor_id)
        NotificationPreference.objects.for_tenant(tenant).filter(user_id=user).delete(); _log("notification.preference.reset", tenant_id=str(tenant), user_id=str(user))
        return [cls.get_effective(tenant, user, channel, "general") for channel in sorted(CHANNELS)]


class NotificationEndpointService:
    @staticmethod
    def _fingerprint(tenant: uuid.UUID, value: str) -> str:
        key = str(getattr(settings, "SECRET_KEY", "")).encode()
        if not key: raise CapabilityUnavailable("Endpoint fingerprinting is unavailable because the server secret is not configured.")
        return hmac.new(key, tenant.bytes + value.encode(), hashlib.sha256).hexdigest()

    @classmethod
    @transaction.atomic
    def register(cls, tenant_id: uuid.UUID | str, user_id: object, actor_id: object, data: Mapping[str, object]) -> NotificationEndpoint:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); actor = identity_uuid(tenant, actor_id)
        kind = str(data.get("kind", "")); address = _required_text(data.get("address"), "address", 4096)
        if kind not in {"push", "webhook"}: raise NotificationServiceError("VALIDATION_ERROR", "kind must be push or webhook.")
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        if kind == "webhook": _validate_public_webhook(address, (config.document if config else NotificationConfigurationService.safe_default()).get("allowed_webhook_hosts", []))
        device_type = str(data.get("device_type", ""))
        if kind == "push" and device_type not in {"web", "android", "ios"}: raise NotificationServiceError("VALIDATION_ERROR", "device_type is required for push endpoints.")
        secret_ref = str(data.get("secret_ref", ""))
        if kind == "webhook" and not re.fullmatch(r"(?:vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+", secret_ref): raise NotificationServiceError("VALIDATION_ERROR", "secret_ref must use an approved secret-manager URI.")
        fingerprint = cls._fingerprint(tenant, address)
        endpoint, created = NotificationEndpoint.objects.for_tenant(tenant).get_or_create(kind=kind, fingerprint=fingerprint, defaults={"tenant_id": tenant, "user_id": user if kind == "push" else data.get("user_id", user), "device_type": device_type, "address_ciphertext": EncryptionService.encrypt(address), "display_name": _required_text(data.get("display_name"), "display_name", 255), "secret_ref": secret_ref, "created_by": actor})
        if not created and not endpoint.is_active: endpoint.is_active = True; endpoint.save(update_fields=["is_active", "updated_at"])
        _log("notification.endpoint.registered", tenant_id=str(tenant), endpoint_id=str(endpoint.id), kind=kind); return endpoint

    @staticmethod
    def list_for_user(tenant_id: uuid.UUID | str, user_id: object) -> QuerySet[NotificationEndpoint]:
        tenant = _uuid(tenant_id, "tenant_id"); return NotificationEndpoint.objects.for_tenant(tenant).filter(user_id=identity_uuid(tenant, user_id)).order_by("kind", "display_name")

    @classmethod
    @transaction.atomic
    def update(cls, tenant_id: uuid.UUID | str, endpoint_id: uuid.UUID | str, actor_id: object, data: Mapping[str, object]) -> NotificationEndpoint:
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); endpoint = NotificationEndpoint.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(endpoint_id, "endpoint_id"))
        if "display_name" in data: endpoint.display_name = _required_text(data["display_name"], "display_name", 255)
        if "is_active" in data: endpoint.is_active = bool(data["is_active"])
        if "secret_ref" in data:
            secret_ref = str(data["secret_ref"])
            if secret_ref and not re.fullmatch(r"(?:secret|vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+", secret_ref): raise NotificationServiceError("VALIDATION_ERROR", "secret_ref must use an approved secret-manager URI.")
            endpoint.secret_ref = secret_ref
        endpoint.save(update_fields=["display_name", "is_active", "secret_ref", "updated_at"]); return endpoint

    @classmethod
    def verify(cls, tenant_id: uuid.UUID | str, endpoint_id: uuid.UUID | str, actor_id: object) -> NotificationEndpoint:
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); endpoint = NotificationEndpoint.objects.for_tenant(tenant).get(pk=_uuid(endpoint_id, "endpoint_id"), is_active=True)
        from .adapters import EndpointVerificationCommand, get_adapter
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        channel = "push" if endpoint.kind == "push" else "webhook"; channel_config = (config.document if config else NotificationConfigurationService.safe_default())["channels"][channel]
        adapter = get_adapter(str(channel_config["adapter_key"])); result = adapter.verify_endpoint(EndpointVerificationCommand(tenant_id=tenant, endpoint_id=endpoint.id, address=EncryptionService.decrypt(endpoint.address_ciphertext), configuration=channel_config, correlation_id=_correlation_uuid()))
        if not result.verified: raise CapabilityUnavailable(result.error_code or "Endpoint verification failed.")
        endpoint.last_verified_at = timezone.now(); endpoint.save(update_fields=["last_verified_at", "updated_at"]); _log("notification.endpoint.verified", tenant_id=str(tenant), endpoint_id=str(endpoint.id)); return endpoint

    @classmethod
    @transaction.atomic
    def revoke(cls, tenant_id: uuid.UUID | str, endpoint_id: uuid.UUID | str, actor_id: object) -> NotificationEndpoint:
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); endpoint = NotificationEndpoint.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(endpoint_id, "endpoint_id")); endpoint.is_active = False; endpoint.save(update_fields=["is_active", "updated_at"]); _log("notification.endpoint.revoked", tenant_id=str(tenant), endpoint_id=str(endpoint.id)); return endpoint

    @classmethod
    @transaction.atomic
    def rotate_secret_ref(cls, tenant_id: uuid.UUID | str, endpoint_id: uuid.UUID | str, actor_id: object, secret_ref: str) -> NotificationEndpoint:
        if not re.fullmatch(r"(?:vault|aws-secrets|gcp-secrets|azure-keyvault)://[A-Za-z0-9_./-]+", secret_ref): raise NotificationServiceError("VALIDATION_ERROR", "secret_ref must use an approved secret-manager URI.")
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); endpoint = NotificationEndpoint.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(endpoint_id, "endpoint_id")); endpoint.secret_ref = secret_ref; endpoint.save(update_fields=["secret_ref", "updated_at"]); return endpoint


class NotificationInboxService:
    @staticmethod
    def list_for_user(tenant_id: uuid.UUID | str, user_id: object, filters: Mapping[str, object] | None = None) -> QuerySet[Notification]:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); values = filters or {}; now = timezone.now()
        query = Notification.objects.for_tenant(tenant).filter(user_id=user).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        if not values.get("status"): query = query.exclude(status="archived")
        for key, field_name in (("status", "status"), ("type", "notification_type"), ("category", "category")):
            if values.get(key): query = query.filter(**{field_name: values[key]})
        if values.get("created_after"): query = query.filter(created_at__gte=values["created_after"])
        if values.get("created_before"): query = query.filter(created_at__lte=values["created_before"])
        if values.get("search"):
            search = str(values["search"])[:100]; query = query.filter(Q(title__icontains=search) | Q(message__icontains=search))
        ordering = str(values.get("ordering", "-created_at")); allowed = {"created_at", "-created_at", "status", "-status"}
        return query.order_by(ordering if ordering in allowed else "-created_at")

    @staticmethod
    def get_for_user(tenant_id: uuid.UUID | str, user_id: object, notification_id: uuid.UUID | str) -> Notification:
        tenant = _uuid(tenant_id, "tenant_id"); return Notification.objects.for_tenant(tenant).get(pk=_uuid(notification_id, "notification_id"), user_id=identity_uuid(tenant, user_id))

    @staticmethod
    @transaction.atomic
    def create_in_app(tenant_id: uuid.UUID | str, delivery: NotificationDelivery) -> Notification:
        tenant = _uuid(tenant_id, "tenant_id")
        if delivery.tenant_id != tenant or delivery.channel != "in_app" or delivery.status not in {"sent", "delivered"} or not delivery.recipient_user_id: raise NotificationServiceError("INVALID_DELIVERY", "Only accepted in-app deliveries can enter the inbox.")
        notification, _ = Notification.objects.for_tenant(tenant).get_or_create(delivery=delivery, defaults={"tenant_id": tenant, "user_id": delivery.recipient_user_id, "notification_type": "info", "category": delivery.category, "title": delivery.rendered_subject or delivery.category.replace("_", " ").title(), "message": delivery.rendered_body})
        return notification

    @classmethod
    def _transition(cls, tenant_id: uuid.UUID | str, user_id: object, notification_id: uuid.UUID | str, command: str, key: str) -> Notification:
        tenant = _uuid(tenant_id, "tenant_id"); item = cls.get_for_user(tenant, user_id, notification_id)
        if any(record.get("transition_key") == key and record.get("command") == command for record in item.transition_history): return item
        target = {"mark_read": "read", "mark_unread": "unread", "archive": "archived"}[command]
        legal = {"mark_read": {"unread"}, "mark_unread": {"read"}, "archive": {"unread", "read"}}
        if item.status not in legal[command]: raise NotificationServiceError("ILLEGAL_TRANSITION", f"Cannot {command.replace('_', ' ')} from {item.status}.")
        with transaction.atomic():
            item = Notification.objects.for_tenant(tenant).select_for_update().get(pk=item.pk, user_id=item.user_id)
            previous = item.status; item.status = target; item.read_at = timezone.now() if target == "read" else None; item.transition_history = [*item.transition_history, {"transition_key": key, "command": command, "from_state": previous, "to_state": target, "occurred_at": timezone.now().isoformat(), "metadata": {}}]; item.save(update_fields=["status", "read_at", "transition_history", "updated_at"])
        return item

    @classmethod
    def mark_read(cls, tenant_id: uuid.UUID | str, user_id: object, notification_id: uuid.UUID | str, transition_key: str) -> Notification: return cls._transition(tenant_id, user_id, notification_id, "mark_read", transition_key)
    @classmethod
    def mark_unread(cls, tenant_id: uuid.UUID | str, user_id: object, notification_id: uuid.UUID | str, transition_key: str) -> Notification: return cls._transition(tenant_id, user_id, notification_id, "mark_unread", transition_key)
    @classmethod
    def archive(cls, tenant_id: uuid.UUID | str, user_id: object, notification_id: uuid.UUID | str, transition_key: str) -> Notification: return cls._transition(tenant_id, user_id, notification_id, "archive", transition_key)

    @classmethod
    @transaction.atomic
    def mark_all_read(cls, tenant_id: uuid.UUID | str, user_id: object, transition_key: str) -> int:
        tenant = _uuid(tenant_id, "tenant_id"); user = identity_uuid(tenant, user_id); now = timezone.now(); items = list(Notification.objects.for_tenant(tenant).select_for_update().filter(user_id=user, status="unread").filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)))
        for item in items:
            item.status = "read"; item.read_at = now; item.transition_history = [*item.transition_history, {"transition_key": f"{transition_key}:{item.id}", "command": "mark_read", "from_state": "unread", "to_state": "read", "occurred_at": now.isoformat(), "metadata": {"bulk": True}}]
        Notification.objects.bulk_update(items, ["status", "read_at", "transition_history", "updated_at"])
        return len(items)

    @staticmethod
    def unread_count(tenant_id: uuid.UUID | str, user_id: object) -> int:
        tenant = _uuid(tenant_id, "tenant_id"); now = timezone.now(); return Notification.objects.for_tenant(tenant).filter(user_id=identity_uuid(tenant, user_id), status="unread").filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).count()


class NotificationProviderCallbackService:
    """Verify signed provider callbacks and enqueue normalized confirmation jobs."""

    @staticmethod
    @transaction.atomic
    def accept(callback_key: str, headers: Mapping[str, object], raw_body: bytes) -> dict[str, object]:
        routes = getattr(settings, "NOTIFICATION_CALLBACK_ENDPOINTS", {})
        route = routes.get(callback_key) if isinstance(routes, Mapping) else None
        if not isinstance(route, Mapping):
            raise NotificationServiceError("CALLBACK_NOT_FOUND", "Provider callback endpoint was not found.")
        tenant = _uuid(route.get("tenant_id"), "tenant_id")
        endpoint = NotificationEndpoint.objects.for_tenant(tenant).filter(pk=_uuid(route.get("endpoint_id"), "endpoint_id"), kind="webhook", is_active=True).first()
        if endpoint is None: raise NotificationServiceError("CALLBACK_NOT_FOUND", "Provider callback endpoint was not found.")
        secrets = getattr(settings, "NOTIFICATION_PROVIDER_CALLBACK_SECRETS", {})
        secret = secrets.get(endpoint.secret_ref) if isinstance(secrets, Mapping) else None
        if not isinstance(secret, str) or not secret:
            raise CapabilityUnavailable("Provider callback signature verification is unavailable.")
        timestamp_text = str(headers.get("X-Notification-Timestamp", "")); signature = str(headers.get("X-Notification-Signature", "")); event_id = _required_text(headers.get("X-Notification-Event-ID"), "X-Notification-Event-ID", 255)
        try: timestamp_value = int(timestamp_text)
        except ValueError as exc: raise NotificationServiceError("INVALID_CALLBACK_TIMESTAMP", "Callback timestamp is invalid.") from exc
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        if config is None: raise NotificationServiceError("CONFIGURATION_MISSING", "Notification configuration is not configured.")
        tolerance = int(config.document["provider_callbacks"]["timestamp_tolerance_seconds"])
        if abs(int(unix_time.time()) - timestamp_value) > tolerance: raise NotificationServiceError("CALLBACK_TIMESTAMP_EXPIRED", "Callback timestamp is outside the configured tolerance.")
        expected = hmac.new(secret.encode(), f"{timestamp_text}.".encode() + raw_body, hashlib.sha256).hexdigest()
        supplied = signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, supplied): raise NotificationServiceError("INVALID_SIGNATURE", "Provider callback signature verification failed.")
        try: payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise NotificationServiceError("INVALID_CALLBACK_BODY", "Callback body must be valid JSON.") from exc
        if not isinstance(payload, dict): raise NotificationServiceError("INVALID_CALLBACK_BODY", "Callback body must be an object.")
        delivery = NotificationDelivery.objects.for_tenant(tenant).filter(pk=_uuid(payload.get("delivery_id"), "delivery_id")).first()
        if delivery is None: raise NotificationServiceError("CALLBACK_NOT_FOUND", "Delivery was not found.")
        normalized = {"event_id": event_id, "event_type": _required_text(payload.get("event_type"), "event_type", 100), "occurred_at": payload.get("occurred_at"), "provider_message_id": _required_text(payload.get("provider_message_id"), "provider_message_id", 255), "signature_verified": True}
        idempotency_key = f"notifications:callback:{callback_key}:{event_id}"
        from src.core.async_jobs.models import AsyncJob
        existing = AsyncJob.objects.for_tenant(tenant).filter(idempotency_key=idempotency_key).first()
        job = enqueue_job(tenant, identity_uuid(tenant, f"provider:{callback_key}"), "notifications.delivery.confirm", {"tenant_id": str(tenant), "delivery_id": str(delivery.id), "provider_event": normalized, "idempotency_key": event_id}, idempotency_key)
        return {"accepted": True, "replayed": existing is not None, "job_id": job.id, "correlation_id": job.correlation_id}


class NotificationDispatchService:
    @staticmethod
    def _policy_schedule(configuration: NotificationConfiguration, preference: Mapping[str, object], now: datetime) -> tuple[datetime | None, str | None]:
        """Return the next policy time for quiet hours or digest delivery."""

        tz_name = str(preference.get("timezone") or configuration.document.get("quiet_hours", {}).get("timezone", "UTC"))
        zone = ZoneInfo(tz_name)
        local_now = now.astimezone(zone)
        start = preference.get("quiet_hours_start")
        end = preference.get("quiet_hours_end")
        if start is None and end is None:
            quiet = configuration.document.get("quiet_hours", {})
            if isinstance(quiet, dict): start, end = quiet.get("start"), quiet.get("end")
        def as_time(value: object) -> time | None:
            if isinstance(value, time): return value
            if isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value):
                return time.fromisoformat(value)
            return None
        start_time, end_time = as_time(start), as_time(end)
        if start_time and end_time:
            current = local_now.timetz().replace(tzinfo=None)
            within = start_time <= current < end_time if start_time < end_time else (current >= start_time or current < end_time)
            if within:
                end_date = local_now.date()
                if start_time >= end_time and current >= start_time: end_date += timedelta(days=1)
                return datetime.combine(end_date, end_time, zone).astimezone(datetime_timezone.utc), "quiet_hours"
        digest = str(preference.get("digest_mode", "immediate"))
        schedules = configuration.document.get("digest_schedules", {})
        if digest == "hourly":
            minute = int(schedules.get("hourly_minute", 0)); target = local_now.replace(minute=minute, second=0, microsecond=0)
            if target <= local_now: target += timedelta(hours=1)
            return target.astimezone(datetime_timezone.utc), "digest_hourly"
        if digest == "daily":
            target_time = time.fromisoformat(str(schedules.get("daily_time", "09:00"))); target = datetime.combine(local_now.date(), target_time, zone)
            if target <= local_now: target += timedelta(days=1)
            return target.astimezone(datetime_timezone.utc), "digest_daily"
        if digest == "weekly":
            target_time = time.fromisoformat(str(schedules.get("daily_time", "09:00"))); weekday = int(schedules.get("weekly_day", 1)); days = (weekday - local_now.weekday()) % 7; target = datetime.combine(local_now.date() + timedelta(days=days), target_time, zone)
            if target <= local_now: target += timedelta(days=7)
            return target.astimezone(datetime_timezone.utc), "digest_weekly"
        return None, None

    @classmethod
    def preview_dispatch(cls, tenant_id: uuid.UUID | str, actor_id: object, request: Mapping[str, object]) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); template = NotificationTemplateService.get_template(tenant, request.get("template_id"))
        if template.status != "active" or not template.active_version_id: raise NotificationServiceError("TEMPLATE_INACTIVE", "Only active templates can dispatch.")
        recipient_type = str(request.get("recipient_type", "")); user_id = request.get("recipient_user_id")
        if recipient_type not in {"user", "email", "phone", "push_endpoint", "webhook_endpoint"}: raise NotificationServiceError("VALIDATION_ERROR", "recipient_type is invalid.")
        config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=str(request.get("environment", getattr(settings, "SARAISE_ENVIRONMENT", "development")))).first()
        if config is None: raise NotificationServiceError("CONFIGURATION_MISSING", "Notification configuration is not configured.")
        channel_config = config.document["channels"][template.channel]
        if not channel_config["enabled"]: return {"will_dispatch": False, "reason": "channel_disabled", "channel": template.channel}
        priority = int(request.get("priority", 5))
        if priority == 1 and not request.get("urgent_authorized"):
            raise NotificationServiceError("URGENT_PERMISSION_REQUIRED", "Priority 1 delivery requires urgent dispatch authorization.")
        preference: dict[str, object] = {"enabled": True, "digest_mode": "immediate", "timezone": "UTC", "quiet_hours_start": None, "quiet_hours_end": None}
        if user_id:
            preference = NotificationPreferenceService.get_effective(tenant, user_id, template.channel, template.category)
            if not preference["enabled"]: return {"will_dispatch": False, "reason": "preference_disabled", "channel": template.channel}
        rendered = NotificationTemplateService.preview(tenant, template.id, template.active_version_id, request.get("context", {}))
        if not rendered["valid"]: raise NotificationServiceError("MISSING_VARIABLES", "Required template variables are missing.", errors={"missing_variables": rendered["missing_variables"]})
        context_limit = int(config.document["limits"]["context_bytes"])
        if _json_size(request.get("context", {})) > context_limit:
            raise NotificationServiceError("CONTEXT_TOO_LARGE", "Dispatch context exceeds the configured byte limit.")
        scheduled_at, policy_reason = (None, None) if priority == 1 else cls._policy_schedule(config, preference, timezone.now())
        decision = "mandatory" if template.category in MANDATORY_CATEGORIES else ("quiet_hours" if policy_reason == "quiet_hours" else "allowed")
        return {"will_dispatch": True, "reason": policy_reason or "eligible", "deferred": scheduled_at is not None, "scheduled_at": scheduled_at, "channel": template.channel, "effective_channel": template.channel, "category": template.category, "rendered_subject": rendered["subject"], "rendered_body": rendered["body"], "subject": rendered["subject"], "body": rendered["body"], "content_type": rendered["content_type"], "diagnostics": rendered["diagnostics"], "preference_decision": decision, "configuration_version": config.active_version, "masked_recipient": cls._masked(request), "recipient_display": cls._masked(request)}

    @staticmethod
    def _masked(request: Mapping[str, object]) -> str:
        value = str(request.get("recipient", request.get("recipient_user_id", "")))
        if not value: return ""
        if "@" in value:
            local, domain = value.rsplit("@", 1); return f"{local[:1]}***@{domain}"
        return f"***{value[-4:]}" if len(value) > 4 else "****"

    @classmethod
    @transaction.atomic
    def enqueue(cls, tenant_id: uuid.UUID | str, actor_id: object, request: Mapping[str, object], idempotency_key: str) -> OperationResult:
        tenant = _uuid(tenant_id, "tenant_id"); actor = identity_uuid(tenant, actor_id); key = _required_text(idempotency_key, "idempotency_key", 255)
        existing = NotificationDelivery.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing: return OperationResult(existing.id, existing.status, existing.correlation_id, existing, {"job_id": str(existing.job_id), "replayed": True})
        preview = cls.preview_dispatch(tenant, actor, request)
        template = NotificationTemplateService.get_template(tenant, request.get("template_id")); config = NotificationConfiguration.objects.for_tenant(tenant).select_for_update().get(environment=str(request.get("environment", getattr(settings, "SARAISE_ENVIRONMENT", "development"))))
        channel_limit = int(config.document["channels"][template.channel]["rate_limit_per_minute"])
        recent_count = NotificationDelivery.objects.for_tenant(tenant).filter(channel=template.channel, created_at__gte=timezone.now() - timedelta(minutes=1)).count()
        if recent_count >= channel_limit:
            raise NotificationServiceError("CHANNEL_RATE_LIMITED", "The configured channel rate limit has been reached.")
        if not preview["will_dispatch"]:
            delivery = NotificationDelivery.objects.create(tenant_id=tenant, template_version=template.active_version, job_id=None, idempotency_key=key, recipient_type=str(request.get("recipient_type")), recipient_user_id=identity_uuid(tenant, request["recipient_user_id"]) if request.get("recipient_user_id") else None, recipient_ciphertext="", recipient_fingerprint=hashlib.sha256(f"{tenant}:{key}".encode()).hexdigest(), recipient_display=cls._masked(request), channel=template.channel, category=template.category, priority=int(request.get("priority", 5)), status="skipped", context_data={}, rendered_subject="", rendered_body="", max_attempts=int(config.document["max_attempts"]), failure_code=str(preview["reason"]), created_by=actor, correlation_id=_correlation_uuid())
            return OperationResult(delivery.id, delivery.status, delivery.correlation_id, delivery, {"reason": preview["reason"]})
        recipient = str(request.get("recipient", "")); ciphertext = EncryptionService.encrypt(recipient) if recipient else ""; correlation = _correlation_uuid()
        effective_schedule = preview.get("scheduled_at") or request.get("scheduled_at")
        delivery = NotificationDelivery.objects.create(tenant_id=tenant, template_version=template.active_version, job_id=None, idempotency_key=key, recipient_type=str(request.get("recipient_type")), recipient_user_id=identity_uuid(tenant, request["recipient_user_id"]) if request.get("recipient_user_id") else None, recipient_ciphertext=ciphertext, recipient_fingerprint=NotificationEndpointService._fingerprint(tenant, recipient or str(request.get("recipient_user_id"))), recipient_display=cls._masked(request), channel=template.channel, category=template.category, priority=int(request.get("priority", 5)), status="pending", context_data=request.get("context", {}), rendered_subject=str(preview["rendered_subject"]), rendered_body=str(preview["rendered_body"]), scheduled_at=effective_schedule, max_attempts=int(config.document["max_attempts"]), created_by=actor, correlation_id=correlation)
        job = enqueue_job(tenant, actor, "notifications.delivery.execute", {"tenant_id": str(tenant), "delivery_id": str(delivery.id)}, f"notifications:delivery:{key}")
        if effective_schedule and effective_schedule > timezone.now():
            from src.core.async_jobs.models import OutboxEvent
            OutboxEvent.objects.for_tenant(tenant).filter(aggregate_id=job.id).update(available_at=effective_schedule)
        delivery.job_id = job.id; delivery.status = "queued"; delivery.transition_history = [{"transition_key": f"enqueue:{key}", "command": "enqueue", "from_state": "pending", "to_state": "queued", "occurred_at": timezone.now().isoformat(), "metadata": {"job_id": str(job.id), "available_at": effective_schedule.isoformat() if effective_schedule else None}}]; delivery.save(update_fields=["job_id", "status", "transition_history", "updated_at"])
        _log("notification.delivery.queued", tenant_id=str(tenant), actor_id=str(actor), delivery_id=str(delivery.id), job_id=str(job.id), channel=delivery.channel)
        return OperationResult(delivery.id, delivery.status, correlation, delivery, {"job_id": str(job.id), "outbox_durable": True})

    @classmethod
    @transaction.atomic
    def enqueue_bulk(cls, tenant_id: uuid.UUID | str, actor_id: object, requests: Sequence[Mapping[str, object]], idempotency_key: str) -> list[OperationResult]:
        tenant = _uuid(tenant_id, "tenant_id"); config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        if not config: raise NotificationServiceError("CONFIGURATION_MISSING", "Notification configuration is not configured.")
        if not requests or len(requests) > int(config.document["batch_size"]): raise NotificationServiceError("BATCH_LIMIT", "Batch is empty or exceeds configured batch size.")
        for item in requests: cls.preview_dispatch(tenant, actor_id, item)
        return [cls.enqueue(tenant, actor_id, item, f"{idempotency_key}:{index}") for index, item in enumerate(requests)]

    @classmethod
    def execute_delivery(cls, tenant_id: uuid.UUID | str, delivery_id: uuid.UUID | str) -> NotificationDelivery:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            delivery = NotificationDelivery.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(delivery_id, "delivery_id"))
            if delivery.status in {"cancelled", "delivered", "failed", "skipped"}: return delivery
            if delivery.status not in {"queued", "retry_wait"}: raise NotificationServiceError("ILLEGAL_TRANSITION", "Delivery is not executable.")
            from .state_machines import DELIVERY_STATE_MACHINE
            if delivery.status == "retry_wait":
                delivery = DELIVERY_STATE_MACHINE.apply(delivery, "requeue", transition_key=f"worker-requeue:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant)
            delivery = DELIVERY_STATE_MACHINE.apply(delivery, "claim", transition_key=f"worker-claim:{delivery.job_id}:{delivery.attempt_count + 1}", tenant_id=tenant)
            delivery.attempt_count += 1; delivery.save(update_fields=["attempt_count", "updated_at"])
            started = timezone.now()
            try:
                from .adapters import DeliveryCommand, get_adapter
                config = NotificationConfiguration.objects.for_tenant(tenant).get(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")); channel_config = config.document["channels"][delivery.channel]
                adapter = get_adapter(channel_config["adapter_key"])
                result = adapter.send(DeliveryCommand(tenant_id=tenant, delivery_id=delivery.id, idempotency_token=str(delivery.job_id), recipient=EncryptionService.decrypt(delivery.recipient_ciphertext) if delivery.recipient_ciphertext else str(delivery.recipient_user_id), subject=delivery.rendered_subject, body=delivery.rendered_body, configuration=channel_config, correlation_id=delivery.correlation_id, channel=delivery.channel, recipient_type=delivery.recipient_type, content_type=delivery.template_version.content_type))
                latency = max(0, int((timezone.now() - started).total_seconds() * 1000))
                outcome = "accepted" if result.accepted else ("retryable_failure" if result.retryable else "permanent_failure")
                NotificationDeliveryAttempt.objects.create(tenant_id=tenant, delivery=delivery, attempt_number=delivery.attempt_count, adapter_key=adapter.key, outcome=outcome, provider_message_id=result.provider_message_id or "", error_code=result.error_code or "", latency_ms=latency, started_at=started, completed_at=timezone.now(), correlation_id=delivery.correlation_id)
                if not result.accepted:
                    if result.retryable and delivery.attempt_count < delivery.max_attempts:
                        retry = channel_config["retry"]
                        delay = min(int(retry["maximum_seconds"]), int(retry["base_seconds"]) * (2 ** max(0, delivery.attempt_count - 1)))
                        delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay); delivery.failure_code = result.error_code or "ADAPTER_RETRYABLE_FAILURE"
                        delivery.save(update_fields=["next_attempt_at", "failure_code", "updated_at"])
                        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "retry", transition_key=f"worker-retry:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant, metadata={"next_attempt_at": delivery.next_attempt_at.isoformat()})
                    else:
                        delivery.failure_code = result.error_code or "ADAPTER_PERMANENT_FAILURE"; delivery.failure_message = "The delivery provider rejected the notification."
                        delivery.save(update_fields=["failure_code", "failure_message", "updated_at"])
                        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "exhaust", transition_key=f"worker-exhaust:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant)
                else:
                    delivery.provider_message_id = _required_text(result.provider_message_id, "provider_message_id", 255); delivery.sent_at = timezone.now()
                    delivery.save(update_fields=["provider_message_id", "sent_at", "updated_at"])
                    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "acknowledge", transition_key=f"worker-ack:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant, metadata={"provider_message_id": delivery.provider_message_id})
                    if not result.confirmation_supported:
                        delivery.delivered_at = delivery.sent_at; delivery.save(update_fields=["delivered_at", "updated_at"])
                        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "complete_unconfirmed", transition_key=f"worker-complete:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant)
                if delivery.channel == "in_app" and delivery.status in {"sent", "delivered"}: NotificationInboxService.create_in_app(tenant, delivery)
                _log(f"notification.delivery.{delivery.status}", tenant_id=str(tenant), delivery_id=str(delivery.id), state=delivery.status, channel=delivery.channel, adapter_key=adapter.key, retryable=bool(getattr(result, "retryable", False)), error_code=delivery.failure_code)
                return delivery
            except Exception as exc:
                timed_out = isinstance(exc, TimeoutError)
                error_code = "ADAPTER_TIMEOUT" if timed_out else ("CAPABILITY_UNAVAILABLE" if exc.__class__.__name__ == "CapabilityUnavailable" else "ADAPTER_EXECUTION_FAILED")
                latency = max(0, int((timezone.now() - started).total_seconds() * 1000)); NotificationDeliveryAttempt.objects.create(tenant_id=tenant, delivery=delivery, attempt_number=delivery.attempt_count, adapter_key="unavailable", outcome="timeout" if timed_out else "permanent_failure", error_code=error_code, latency_ms=latency, started_at=started, completed_at=timezone.now(), correlation_id=delivery.correlation_id)
                if timed_out and delivery.attempt_count < delivery.max_attempts:
                    retry = config.document["channels"][delivery.channel]["retry"]
                    delay = min(int(retry["maximum_seconds"]), int(retry["base_seconds"]) * (2 ** max(0, delivery.attempt_count - 1)))
                    delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay); delivery.failure_code = error_code
                    delivery.save(update_fields=["next_attempt_at", "failure_code", "updated_at"])
                    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "retry", transition_key=f"worker-exception-retry:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant)
                else:
                    delivery.failure_code = error_code; delivery.failure_message = "Delivery failed without provider acknowledgement."
                    delivery.save(update_fields=["failure_code", "failure_message", "updated_at"])
                    delivery = DELIVERY_STATE_MACHINE.apply(delivery, "exhaust", transition_key=f"worker-exception-exhaust:{delivery.job_id}:{delivery.attempt_count}", tenant_id=tenant)
                _log("notification.delivery.provider_failure", tenant_id=str(tenant), delivery_id=str(delivery.id), state=delivery.status, error_code=error_code)
                return delivery

    @classmethod
    @transaction.atomic
    def retry(cls, tenant_id: uuid.UUID | str, delivery_id: uuid.UUID | str, actor_id: object, idempotency_key: str) -> OperationResult:
        tenant = _uuid(tenant_id, "tenant_id"); actor = identity_uuid(tenant, actor_id); delivery = NotificationDelivery.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(delivery_id, "delivery_id"))
        if delivery.status not in {"failed", "retry_wait"}: raise NotificationServiceError("ILLEGAL_TRANSITION", "Only failed or retry-wait deliveries can be retried.")
        job = enqueue_job(tenant, actor, "notifications.delivery.execute", {"tenant_id": str(tenant), "delivery_id": str(delivery.id)}, f"notifications:retry:{_required_text(idempotency_key, 'idempotency_key', 255)}")
        delivery.job_id = job.id; delivery.failure_code = ""; delivery.failure_message = ""; delivery.next_attempt_at = None; delivery.save(update_fields=["job_id", "failure_code", "failure_message", "next_attempt_at", "updated_at"])
        from .state_machines import DELIVERY_STATE_MACHINE
        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "requeue", transition_key=f"retry:{idempotency_key}", tenant_id=tenant, metadata={"job_id": str(job.id)})
        return OperationResult(delivery.id, delivery.status, delivery.correlation_id, delivery, {"job_id": str(job.id)})

    @classmethod
    @transaction.atomic
    def cancel(cls, tenant_id: uuid.UUID | str, delivery_id: uuid.UUID | str, actor_id: object, transition_key: str) -> NotificationDelivery:
        tenant = _uuid(tenant_id, "tenant_id"); identity_uuid(tenant, actor_id); delivery = NotificationDelivery.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(delivery_id, "delivery_id"))
        from .state_machines import DELIVERY_STATE_MACHINE
        try: delivery = DELIVERY_STATE_MACHINE.apply(delivery, "cancel", transition_key=transition_key, tenant_id=tenant)
        except Exception as exc:
            if any(record.get("transition_key") == transition_key and record.get("command") == "cancel" for record in delivery.transition_history): return delivery
            raise NotificationServiceError("ILLEGAL_TRANSITION", "Delivery can no longer be cancelled.") from exc
        _log("notification.delivery.cancelled", tenant_id=str(tenant), delivery_id=str(delivery.id)); return delivery

    @classmethod
    @transaction.atomic
    def confirm_delivery(cls, tenant_id: uuid.UUID | str, delivery_id: uuid.UUID | str, provider_event: Mapping[str, object], idempotency_key: str) -> NotificationDelivery:
        tenant = _uuid(tenant_id, "tenant_id"); delivery = NotificationDelivery.objects.for_tenant(tenant).select_for_update().get(pk=_uuid(delivery_id, "delivery_id"))
        if delivery.status == "delivered": return delivery
        if delivery.status != "sent" or provider_event.get("provider_message_id") != delivery.provider_message_id: raise NotificationServiceError("INVALID_CONFIRMATION", "Confirmation does not match an accepted delivery.")
        if not provider_event.get("signature_verified"): raise NotificationServiceError("INVALID_SIGNATURE", "Provider signature verification failed.")
        delivery.delivered_at = timezone.now(); delivery.save(update_fields=["delivered_at", "updated_at"])
        from .state_machines import DELIVERY_STATE_MACHINE
        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "confirm", transition_key=idempotency_key, tenant_id=tenant)
        _log("notification.delivery.delivered", tenant_id=str(tenant), delivery_id=str(delivery.id)); return delivery

    @classmethod
    def process_due(cls, tenant_id: uuid.UUID | str, limit: int) -> list[OperationResult]:
        tenant = _uuid(tenant_id, "tenant_id"); bounded = max(1, min(int(limit), 500)); results: list[OperationResult] = []
        with transaction.atomic():
            due = list(NotificationDelivery.objects.for_tenant(tenant).select_for_update(skip_locked=True).filter(status__in=["pending", "retry_wait"]).filter(Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=timezone.now())).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now())).order_by("priority", "created_at")[:bounded])
            for delivery in due:
                if delivery.status == "retry_wait":
                    results.append(cls.retry(tenant, delivery.id, delivery.created_by, f"due:{delivery.id}:{delivery.attempt_count}"))
                    continue
                job = enqueue_job(
                    tenant,
                    delivery.created_by,
                    "notifications.delivery.execute",
                    {"tenant_id": str(tenant), "delivery_id": str(delivery.id)},
                    f"notifications:due:{delivery.id}:{delivery.attempt_count}",
                )
                delivery.job_id = job.id
                delivery.status = "queued"
                delivery.save(update_fields=["job_id", "status", "updated_at"])
                results.append(OperationResult(delivery.id, delivery.status, delivery.correlation_id, delivery, {"job_id": str(job.id), "outbox_durable": True}))
        return results

    @staticmethod
    @transaction.atomic
    def purge_expired(tenant_id: uuid.UUID | str, cutoff: datetime) -> dict[str, int]:
        tenant = _uuid(tenant_id, "tenant_id"); config = NotificationConfiguration.objects.for_tenant(tenant).filter(environment=getattr(settings, "SARAISE_ENVIRONMENT", "development")).first()
        if not config: raise NotificationServiceError("CONFIGURATION_MISSING", "Retention configuration is missing.")
        oldest = timezone.now() - timedelta(days=int(config.document["retention"]["inbox_days"])); effective = min(cutoff, oldest)
        inbox, _ = Notification.objects.for_tenant(tenant).filter(created_at__lt=effective).delete()
        return {"inbox_deleted": inbox, "deliveries_deleted": 0, "immutable_evidence_preserved": 1}


# Backward-compatible façade: it delegates to canonical services and has no
# independent persistence path.
class NotificationService:
    @staticmethod
    def create_notification(tenant_id: uuid.UUID | str, user_id: object, title: str, message: str, notification_type: str = "info", **kwargs: object) -> Notification:
        tenant = _uuid(tenant_id, "tenant_id")
        return Notification.objects.for_tenant(tenant).create(tenant_id=tenant, user_id=identity_uuid(tenant, user_id), title=_required_text(title, "title", 255), message=_required_text(message, "message"), notification_type=notification_type, category=str(kwargs.pop("category", "general")), **kwargs)

    @staticmethod
    def mark_as_read(notification: Notification) -> Notification:
        return NotificationInboxService.mark_read(notification.tenant_id, notification.user_id, notification.id, f"legacy:{uuid.uuid4()}")

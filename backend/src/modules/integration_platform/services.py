"""Tenant-first transactional services for integration-platform aggregates."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from jsonschema import Draft202012Validator
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound

from src.core.access.entitlements import EntitlementService, QuotaService
from src.core.api.results import CapabilityUnavailable, OperationFailed, OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue, recover_stale_jobs
from src.core.encryption.service import EncryptionConfigurationError, EncryptionService
from src.core.observability import get_correlation_id
from src.core.resilience.http import ResilientHttpClient
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError

from .adapter_registry import AdapterUnavailableError, connector_adapter_registry, transformation_registry
from .adapters import ConnectorAdapter, CredentialBundle, RecordBatch, RecordCursor
from .configuration import default_configuration, setting, validate_configuration
from .models import (
    Connector,
    ConnectorAccessPolicy,
    ConnectorCapability,
    CredentialStatus,
    CredentialType,
    DataMapping,
    DeliveryStatus,
    Integration,
    IntegrationCredential,
    IntegrationStatus,
    IntegrationPlatformConfiguration,
    IntegrationPlatformConfigurationAudit,
    IntegrationPlatformConfigurationVersion,
    Webhook,
    WebhookDelivery,
    WebhookDeliveryAttempt,
    WebhookDirection,
    WebhookStatus,
)
from .state_machines import (
    CREDENTIAL_STATE_MACHINE,
    DELIVERY_STATE_MACHINE,
    INTEGRATION_STATE_MACHINE,
    WEBHOOK_STATE_MACHINE,
)

logger = logging.getLogger("saraise.integration_platform")
INBOUND_TIMESTAMP_HEADER = "X-SARAISE-Webhook-Timestamp"
INBOUND_NONCE_HEADER = "X-SARAISE-Webhook-Nonce"
INBOUND_SIGNATURE_HEADER = "X-SARAISE-Webhook-Signature"
INBOUND_SIGNATURE_VERSION = "v1"


class IntegrationPlatformError(OperationFailed):
    """Stable governed domain exception."""

    def __init__(self, code: str, message: str, *, status_code: int = 422, detail: object | None = None) -> None:
        super().__init__(error_code=code, message=message, http_status=status_code, detail=detail)


@dataclass(frozen=True, slots=True)
class SecretOnce:
    record: Webhook
    secret: str


@dataclass(frozen=True, slots=True)
class MappingFailure:
    record_index: int
    mapping_id: UUID
    source_field: str
    target_field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TransformResult:
    records: tuple[dict[str, object], ...]
    failures: tuple[MappingFailure, ...]


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise IntegrationPlatformError("invalid_uuid", f"{field} must be a valid UUID.", status_code=400) from exc


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntegrationPlatformError("validation_error", f"{field} is required.", status_code=400)
    normalized = value.strip()
    if len(normalized) > maximum:
        raise IntegrationPlatformError("validation_error", f"{field} exceeds {maximum} characters.", status_code=400)
    return normalized


def _configured_text(
    tenant_id: UUID,
    value: object,
    field: str,
    setting_path: str = "validation.name_max_length",
) -> str:
    return _text(value, field, int(setting(runtime_configuration(tenant_id), setting_path)))


def _encrypt_secret(value: str, capability: str) -> str:
    try:
        return EncryptionService.encrypt(value)
    except EncryptionConfigurationError as exc:
        raise CapabilityUnavailable(capability=capability) from exc


def _safe_mapping(tenant_id: UUID, value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise IntegrationPlatformError("validation_error", f"{field} must be an object.", status_code=400)
    result = dict(value)
    policy = runtime_configuration(tenant_id)
    secret_keys = frozenset(str(item) for item in setting(policy, "security.secret_field_names"))
    _reject_secrets(result, field, secret_keys)
    try:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise IntegrationPlatformError("validation_error", f"{field} must contain JSON values.", status_code=400) from exc
    maximum = int(setting(policy, "security.payload_max_bytes"))
    if len(encoded.encode("utf-8")) > maximum:
        raise IntegrationPlatformError("payload_too_large", f"{field} exceeds {maximum} bytes.", status_code=413)
    return result


def _reject_secrets(value: object, field: str, secret_keys: frozenset[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in secret_keys:
                raise IntegrationPlatformError("secret_in_config", f"{field} cannot contain credential-like keys.", status_code=400)
            _reject_secrets(child, field, secret_keys)
    elif isinstance(value, list):
        for child in value:
            _reject_secrets(child, field, secret_keys)


def _redact(value: object, secret_keys: frozenset[str]) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower().replace("-", "_") in secret_keys else _redact(child, secret_keys)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child, secret_keys) for child in value]
    return value


def _correlation_id() -> str:
    # Correlation is generated by core middleware/job orchestration, never here.
    return get_correlation_id() or "correlation-unavailable"


def _transition_metadata(actor_id: UUID | None, reason: str, **evidence: object) -> dict[str, object]:
    return {"actor_id": str(actor_id) if actor_id else "system", "reason": reason, "correlation_id": _correlation_id(), **evidence}


def _publish(tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, payload: Mapping[str, object]) -> OutboxEvent:
    secret_keys = frozenset(str(value) for value in setting(runtime_configuration(tenant_id), "security.secret_field_names"))
    safe = _redact(dict(payload), secret_keys)
    assert isinstance(safe, dict)
    safe["correlation_id"] = _correlation_id()
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=safe,
    )


def _active(model: type[Any], tenant_id: UUID, identifier: UUID | str) -> Any:
    filters: dict[str, object] = {"pk": identifier}
    if any(field.name == "is_deleted" for field in model._meta.fields):
        filters["is_deleted"] = False
    value = model.objects.for_tenant(tenant_id).filter(**filters).first()
    if value is None:
        raise NotFound()
    return value


def _model_validation(instance: Any) -> None:
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise IntegrationPlatformError("validation_error", "The domain record is invalid.", status_code=400, detail=exc.message_dict) from exc


def _validate_schema(instance: Mapping[str, object], schema: Mapping[str, object], field: str = "config") -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda error: tuple(str(part) for part in error.path))
    if errors:
        raise IntegrationPlatformError(
            "schema_validation_failed",
            f"{field} does not satisfy the connector schema.",
            status_code=400,
            detail={"path": [str(part) for part in errors[0].path], "message": errors[0].message},
        )


def _unwrap(result: OperationResult[Any]) -> Any:
    if not isinstance(result, OperationResult):
        raise IntegrationPlatformError("invalid_adapter_result", "The adapter returned invalid evidence.", status_code=503)
    return result.unwrap()


def runtime_configuration(tenant_id: UUID, environment: str = "default") -> dict[str, object]:
    """Return tenant policy or the reviewed safe default document.

    The default contains an explicit fail-closed connector access policy and
    disables capabilities that have no governed data source, so absence never
    bypasses a security decision.
    """

    tenant_id = _uuid(tenant_id, "tenant_id")
    record = (
        IntegrationPlatformConfiguration.objects.for_tenant(tenant_id)
        .filter(environment=environment)
        .only("document")
        .first()
    )
    return validate_configuration(record.document if record is not None else default_configuration())


def durable_job_receipt(job: object) -> dict[str, object]:
    """Prove durable acceptance and expose only the public polling contract."""

    if not isinstance(job, AsyncJob) or job.pk is None:
        raise OperationFailed(
            error_code="DURABLE_JOB_UNAVAILABLE",
            message="The operation was not durably accepted.",
            http_status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    durable = AsyncJob.objects.filter(pk=job.pk, tenant_id=job.tenant_id).exists()
    outbox = OutboxEvent.objects.filter(
        tenant_id=job.tenant_id,
        aggregate_type="async_job",
        aggregate_id=job.pk,
    ).exists()
    if not durable or not outbox:
        raise OperationFailed(
            error_code="DURABLE_JOB_UNAVAILABLE",
            message="The operation was not durably accepted.",
            http_status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return {
        "job_id": job.id,
        "status": job.status,
        "correlation_id": job.correlation_id,
        "accepted_at": job.created_at,
        "poll_after_ms": int(setting(runtime_configuration(job.tenant_id), "jobs.poll_after_ms")),
    }


def durable_job_state(job: object) -> dict[str, object]:
    """Interpret durable worker state as the stable public evidence contract."""

    payload = durable_job_receipt(job)
    assert isinstance(job, AsyncJob)
    operations = {
        "integration_platform.test": "integration_test",
        "integration_platform.integration_test": "integration_test",
        "integration_platform.sync": "integration_sync",
        "integration_platform.integration_sync": "integration_sync",
        "integration_platform.webhook_delivery": "webhook_delivery",
        "integration_platform.deliver_webhook": "webhook_delivery",
    }
    operation = getattr(job, "operation", None) or operations.get(str(job.command))
    if operation is None:
        raise OperationFailed(
            error_code="JOB_STATE_UNAVAILABLE",
            message="The durable job operation cannot be represented safely.",
            http_status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    result = job.result if isinstance(job.result, Mapping) else {}
    policy = runtime_configuration(job.tenant_id)
    progress_min = int(setting(policy, "jobs.progress_min"))
    progress_max = int(setting(policy, "jobs.progress_max"))
    raw_progress = result.get("progress_percent")
    progress = raw_progress if isinstance(raw_progress, int) and progress_min <= raw_progress <= progress_max else None
    terminal = {"succeeded", "failed", "cancelled", "timed_out"}
    if progress is None:
        progress = int(setting(policy, "jobs.terminal_progress")) if job.status in terminal else progress_min
    evidence_keys = {
        "outcome",
        "occurred_at",
        "correlation_id",
        "job_id",
        "duration_ms",
        "error_code",
        "error_message",
        "records_read",
        "records_written",
        "records_failed",
        "zero_source_proven",
    }
    evidence = {key: result[key] for key in evidence_keys if key in result}
    payload.update(
        {
            "operation": operation,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "progress_percent": progress,
            "evidence": evidence or None,
        }
    )
    return payload


def _apply_transition(
    machine: Any,
    workflow_key: str,
    instance: Any,
    command: str,
    *,
    tenant_id: UUID,
    **kwargs: object,
) -> Any:
    """Interpret the configured tenant graph before invoking the core engine."""

    current = str(instance.status)
    edge = next(
        (
            transition
            for transition in machine.transitions
            if transition.command == command and transition.source == current
        ),
        None,
    )
    if edge is None:
        raise IntegrationPlatformError("invalid_transition", "The lifecycle command is not available.", status_code=409)
    graph = setting(runtime_configuration(tenant_id), f"workflows.{workflow_key}")
    allowed = graph.get(current, []) if isinstance(graph, Mapping) else []
    if edge.target not in allowed:
        raise IntegrationPlatformError(
            "workflow_policy_denied",
            "The tenant workflow configuration denies this lifecycle transition.",
            status_code=409,
        )
    return machine.apply(instance, command, tenant_id=tenant_id, **kwargs)


class ConfigurationService:
    """Transactional authority for tenant configuration and its evidence."""

    def get(self, tenant_id: UUID, environment: str = "default") -> dict[str, object]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        record = (
            IntegrationPlatformConfiguration.objects.for_tenant(tenant_id)
            .filter(environment=_text(environment, "environment", 64))
            .first()
        )
        if record is None:
            return {
                "id": None,
                "tenant_id": tenant_id,
                "environment": environment,
                "version": 0,
                "document": default_configuration(),
                "updated_at": None,
                "updated_by": None,
            }
        return self._payload(record)

    @staticmethod
    def _payload(record: IntegrationPlatformConfiguration) -> dict[str, object]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "environment": record.environment,
            "version": record.version,
            "document": record.document,
            "updated_at": record.updated_at,
            "updated_by": record.updated_by,
        }

    @staticmethod
    def _correlation(correlation_id: str | None) -> str:
        value = correlation_id or _correlation_id()
        if not value or value == "correlation-unavailable":
            raise IntegrationPlatformError(
                "correlation_unavailable",
                "A correlation identifier is required for configuration changes.",
                status_code=503,
            )
        return _text(value, "correlation_id", 64)

    def preview(
        self,
        tenant_id: UUID,
        document: object,
        environment: str = "default",
    ) -> dict[str, object]:
        current = self.get(tenant_id, environment)
        validated = validate_configuration(document)
        before = current["document"]
        assert isinstance(before, Mapping)
        changed = sorted(
            key for key in validated if before.get(key) != validated.get(key)
        )
        return {
            "valid": True,
            "environment": environment,
            "from_version": current["version"],
            "to_version": int(current["version"]) + 1,
            "changed_sections": changed,
            "before": dict(before),
            "after": validated,
        }

    def save(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        document: object,
        *,
        environment: str = "default",
        correlation_id: str | None = None,
        action: str = "update",
    ) -> dict[str, object]:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        environment = _text(environment, "environment", 64)
        validated = validate_configuration(document)
        correlation = self._correlation(correlation_id)
        with transaction.atomic():
            record = (
                IntegrationPlatformConfiguration.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(environment=environment)
                .first()
            )
            before = None if record is None else dict(record.document)
            from_version = None if record is None else record.version
            if record is None:
                record = IntegrationPlatformConfiguration(
                    tenant_id=tenant_id,
                    environment=environment,
                    version=1,
                    document=validated,
                    updated_by=actor_id,
                )
            else:
                record.version += 1
                record.document = validated
                record.updated_by = actor_id
            _model_validation(record)
            record.save()
            IntegrationPlatformConfigurationVersion.objects.create(
                tenant_id=tenant_id,
                configuration=record,
                environment=environment,
                version=record.version,
                document=validated,
                created_by=actor_id,
                correlation_id=correlation,
            )
            IntegrationPlatformConfigurationAudit.objects.create(
                tenant_id=tenant_id,
                configuration=record,
                environment=environment,
                action=action,
                from_version=from_version,
                to_version=record.version,
                before=before,
                after=validated,
                changed_by=actor_id,
                correlation_id=correlation,
            )
            _publish(
                tenant_id,
                "integration_platform_configuration",
                record.id,
                f"configuration.{action}",
                {
                    "actor_id": str(actor_id),
                    "environment": environment,
                    "from_version": from_version,
                    "to_version": record.version,
                    "correlation_id": correlation,
                },
            )
        return self._payload(record)

    def rollback(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        version: int,
        *,
        environment: str = "default",
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        snapshot = (
            IntegrationPlatformConfigurationVersion.objects.for_tenant(tenant_id)
            .filter(environment=environment, version=version)
            .only("document")
            .first()
        )
        if snapshot is None:
            raise NotFound()
        return self.save(
            tenant_id,
            actor_id,
            snapshot.document,
            environment=environment,
            correlation_id=correlation_id,
            action="rollback",
        )

    def versions(self, tenant_id: UUID, environment: str = "default") -> QuerySet[IntegrationPlatformConfigurationVersion]:
        return IntegrationPlatformConfigurationVersion.objects.for_tenant(
            _uuid(tenant_id, "tenant_id")
        ).filter(environment=environment).order_by("-version")

    def audits(self, tenant_id: UUID, environment: str = "default") -> QuerySet[IntegrationPlatformConfigurationAudit]:
        return IntegrationPlatformConfigurationAudit.objects.for_tenant(
            _uuid(tenant_id, "tenant_id")
        ).filter(environment=environment).order_by("-created_at", "-to_version")


class ConnectorService:
    def __init__(self, *, entitlements: EntitlementService | None = None) -> None:
        self.entitlements = entitlements or EntitlementService()

    def _entitled(self, tenant_id: UUID, connector: Connector) -> bool:
        if connector.access_policy == ConnectorAccessPolicy.PUBLIC:
            return True
        if connector.access_policy != ConnectorAccessPolicy.ENTITLEMENT_REQUIRED or not connector.required_entitlement:
            raise CapabilityUnavailable(
                capability="connector_access_policy",
                message="Connector entitlement policy is unavailable.",
            )
        try:
            return self.entitlements.check(tenant_id, connector.required_entitlement).entitled
        except Exception as exc:
            raise CapabilityUnavailable(capability="entitlement_state", message="Connector entitlement state is unavailable.") from exc

    def _descriptor(self, tenant_id: UUID, connector: Connector) -> dict[str, object]:
        entitled = self._entitled(tenant_id, connector)
        registered = connector_adapter_registry.is_registered(connector.adapter_key)
        reason = "available" if entitled and registered else "entitlement_required" if not entitled else connector_adapter_registry.availability_reason(connector.adapter_key)
        return {
            "connector": connector,
            "id": connector.id,
            "key": connector.key,
            "name": connector.name,
            "connector_type": connector.connector_type,
            "adapter_key": connector.adapter_key,
            "version": connector.version,
            "schema": connector.schema,
            "credential_schema": connector.credential_schema,
            "capabilities": connector.capabilities,
            "module_id": connector.module_id,
            "required_entitlement": connector.required_entitlement,
            "is_active": connector.is_active,
            "created_at": connector.created_at,
            "updated_at": connector.updated_at,
            "available": entitled and registered,
            "adapter_available": registered,
            "entitled": entitled,
            "is_entitled": entitled,
            "adapter_registered": registered,
            "availability_reason": reason,
            "entitlement_reason": "entitled" if entitled else "entitlement_required",
        }

    def list_connectors(self, tenant_id: UUID, filters: Mapping[str, object] | None = None) -> list[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        criteria = dict(filters or {})
        queryset = Connector.objects.filter(is_active=True)
        for field in ("connector_type", "module_id"):
            if criteria.get(field):
                queryset = queryset.filter(**{field: criteria[field]})
        if criteria.get("is_active") is not None:
            queryset = queryset.filter(is_active=bool(criteria["is_active"]))
        search = criteria.get("search")
        if isinstance(search, str) and search.strip():
            queryset = queryset.filter(Q(name__icontains=search.strip()) | Q(key__icontains=search.strip()))
        return [self._descriptor(tenant_id, connector) for connector in queryset]

    def get_connector(self, tenant_id: UUID, connector_id: UUID) -> dict[str, object]:
        tenant_id, connector_id = _uuid(tenant_id, "tenant_id"), _uuid(connector_id, "connector_id")
        connector = Connector.objects.filter(pk=connector_id, is_active=True).first()
        if connector is None:
            raise NotFound()
        descriptor = self._descriptor(tenant_id, connector)
        if not descriptor["entitled"]:
            raise NotFound()
        return descriptor

    def get_schema(self, tenant_id: UUID, connector_id: UUID) -> dict[str, object]:
        connector = self.get_connector(tenant_id, connector_id)["connector"]
        assert isinstance(connector, Connector)
        return {"connector_id": connector.id, "config_schema": connector.schema, "credential_schema": connector.credential_schema}

    def adapter_health(self, tenant_id: UUID, connector_id: UUID) -> OperationResult[Mapping[str, object]]:
        descriptor = self.get_connector(tenant_id, connector_id)
        connector = descriptor["connector"]
        assert isinstance(connector, Connector)
        try:
            adapter = connector_adapter_registry.get(connector.adapter_key)
        except AdapterUnavailableError:
            return OperationResult.unavailable(capability="connector_adapter", detail={"reason": descriptor["availability_reason"]})
        result = adapter.health()
        if not isinstance(result, OperationResult):
            return OperationResult.unavailable(capability="connector_adapter", message="The adapter health contract is invalid.")
        return result


class CredentialService:
    @staticmethod
    def _plaintext(value: object, maximum: int) -> str:
        if isinstance(value, str):
            if not value:
                raise IntegrationPlatformError("validation_error", "Credential plaintext is required.", status_code=400)
            raw = value
        else:
            try:
                raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise IntegrationPlatformError("validation_error", "Credential plaintext must be text or JSON.", status_code=400) from exc
        if len(raw) > maximum:
            raise IntegrationPlatformError("validation_error", f"Credential plaintext exceeds {maximum} characters.", status_code=400)
        return raw

    @staticmethod
    def _hint(tenant_id: UUID, plaintext: str) -> str:
        visible = int(setting(runtime_configuration(tenant_id), "security.credential_hint_characters"))
        return f"••••{plaintext[-visible:]}" if visible and len(plaintext) >= visible else "••••"

    def create(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        integration_id: UUID,
        credential_type: str,
        plaintext: object,
        expires_at: datetime | None = None,
    ) -> IntegrationCredential:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        if credential_type not in CredentialType.values:
            raise IntegrationPlatformError("validation_error", "Unsupported credential type.", status_code=400)
        raw = self._plaintext(plaintext, int(setting(runtime_configuration(tenant_id), "validation.credential_max_length")))
        with transaction.atomic():
            if IntegrationCredential.objects.for_tenant(tenant_id).filter(integration=integration, credential_type=credential_type, status=CredentialStatus.ACTIVE).exists():
                raise IntegrationPlatformError("active_credential_exists", "Rotate the active credential instead.", status_code=409)
            credential = IntegrationCredential(
                tenant_id=tenant_id,
                integration=integration,
                credential_type=credential_type,
                encrypted_value=_encrypt_secret(raw, "credential_encryption"),
                display_hint=self._hint(tenant_id, raw),
                expires_at=expires_at,
                created_by=actor_id,
            )
            _model_validation(credential)
            credential.save()
            _publish(tenant_id, "integration_credential", credential.id, "credential.created", {"actor_id": str(actor_id), "integration_id": str(integration.id), "credential_type": credential_type, "version": 1})
            return credential

    def list_metadata(self, tenant_id: UUID, integration_id: UUID) -> QuerySet[IntegrationCredential]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        integration = _active(Integration, tenant_id, integration_id)
        return IntegrationCredential.objects.for_tenant(tenant_id).filter(integration=integration).defer("encrypted_value")

    def rotate(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        credential_id: UUID,
        plaintext: object,
        idempotency_key: str,
        expires_at: datetime | None = None,
    ) -> IntegrationCredential:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        raw = self._plaintext(plaintext, int(setting(runtime_configuration(tenant_id), "validation.credential_max_length")))
        key = _configured_text(tenant_id, idempotency_key, "idempotency_key")
        with transaction.atomic():
            old = IntegrationCredential.objects.select_for_update().for_tenant(tenant_id).filter(pk=credential_id).first()
            if old is None:
                raise NotFound()
            existing_transition = next((item for item in old.transition_history if item.get("transition_key") == key), None)
            if existing_transition:
                if existing_transition.get("command") != "rotate":
                    raise IdempotencyConflictError(f"Transition key {key!r} belongs to another command")
                existing = IntegrationCredential.objects.for_tenant(tenant_id).filter(
                    integration=old.integration,
                    credential_type=old.credential_type,
                    version=old.version + 1,
                ).first()
                if existing is None:
                    raise IntegrationPlatformError("rotation_incomplete", "Credential rotation evidence is incomplete.", status_code=409)
                return existing
            old.rotated_at = timezone.now()
            old.revoked_at = old.rotated_at
            old.revoked_by = actor_id
            old.save(update_fields=("rotated_at", "revoked_at", "revoked_by", "updated_at"))
            _apply_transition(CREDENTIAL_STATE_MACHINE, "credential_transitions", old, "rotate", tenant_id=tenant_id, transition_key=key, metadata=_transition_metadata(actor_id, "Credential rotated"))
            new = IntegrationCredential(
                tenant_id=tenant_id,
                integration=old.integration,
                credential_type=old.credential_type,
                encrypted_value=_encrypt_secret(raw, "credential_encryption"),
                display_hint=self._hint(tenant_id, raw),
                version=old.version + 1,
                expires_at=expires_at if expires_at is not None else old.expires_at,
                created_by=actor_id,
            )
            _model_validation(new)
            new.save()
            _publish(tenant_id, "integration_credential", new.id, "credential.rotated", {"actor_id": str(actor_id), "integration_id": str(old.integration_id), "previous_id": str(old.id), "version": new.version})
            return new

    def revoke(self, tenant_id: UUID, actor_id: UUID, credential_id: UUID, transition_key: str) -> IntegrationCredential:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        credential = IntegrationCredential.objects.for_tenant(tenant_id).filter(pk=credential_id).first()
        if credential is None:
            raise NotFound()
        with transaction.atomic():
            credential.revoked_at, credential.revoked_by = timezone.now(), actor_id
            credential.save(update_fields=("revoked_at", "revoked_by", "updated_at"))
            credential = _apply_transition(CREDENTIAL_STATE_MACHINE, "credential_transitions", credential, "revoke", tenant_id=tenant_id, transition_key=_configured_text(tenant_id, transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Credential revoked"))
            _publish(tenant_id, "integration_credential", credential.id, "credential.revoked", {"actor_id": str(actor_id), "integration_id": str(credential.integration_id), "credential_type": credential.credential_type})
            return credential

    def resolve_active(self, tenant_id: UUID, integration_id: UUID, credential_type: str) -> CredentialBundle:
        tenant_id = _uuid(tenant_id, "tenant_id")
        credential = IntegrationCredential.objects.for_tenant(tenant_id).filter(
            integration_id=integration_id,
            credential_type=credential_type,
            status=CredentialStatus.ACTIVE,
        ).first()
        if credential is None:
            raise IntegrationPlatformError("credential_missing", "An active credential is required.", status_code=422)
        if credential.expires_at and credential.expires_at <= timezone.now():
            _apply_transition(CREDENTIAL_STATE_MACHINE, "credential_transitions", credential, "expire", tenant_id=tenant_id, transition_key=f"expire:{credential.id}:{credential.expires_at.isoformat()}", metadata=_transition_metadata(None, "Credential expired"))
            raise IntegrationPlatformError("credential_expired", "The active credential has expired.", status_code=422)
        try:
            plaintext = EncryptionService.decrypt(credential.encrypted_value)
        except Exception as exc:
            raise IntegrationPlatformError("credential_decryption_failed", "Credential material is unavailable.", status_code=503) from exc
        try:
            value: object = json.loads(plaintext)
        except json.JSONDecodeError:
            value = plaintext
        return CredentialBundle(credential.credential_type, value, credential.version, credential.expires_at)

    def resolve_any_active(self, tenant_id: UUID, integration_id: UUID) -> CredentialBundle | None:
        credential = IntegrationCredential.objects.for_tenant(tenant_id).filter(integration_id=integration_id, status=CredentialStatus.ACTIVE).order_by("credential_type").first()
        if credential is None:
            return None
        return self.resolve_active(tenant_id, integration_id, credential.credential_type)


class IntegrationService:
    TEST_COMMAND = "integration_platform.integration.test"
    SYNC_COMMAND = "integration_platform.integration.sync"

    def __init__(self, *, entitlements: EntitlementService | None = None, quotas: QuotaService | None = None, credentials: CredentialService | None = None) -> None:
        self.entitlements = entitlements or EntitlementService()
        self.quotas = quotas or QuotaService()
        self.credentials = credentials or CredentialService()

    def _connector(self, tenant_id: UUID, connector_id: UUID) -> Connector:
        connector = Connector.objects.filter(pk=connector_id, is_active=True).first()
        if connector is None:
            raise NotFound()
        if connector.access_policy == ConnectorAccessPolicy.PUBLIC:
            return connector
        if connector.access_policy != ConnectorAccessPolicy.ENTITLEMENT_REQUIRED or not connector.required_entitlement:
            raise CapabilityUnavailable(capability="connector_access_policy")
        try:
            entitled = self.entitlements.check(tenant_id, connector.required_entitlement).entitled
        except Exception as exc:
            raise CapabilityUnavailable(capability="entitlement_state") from exc
        if not entitled:
            raise IntegrationPlatformError("entitlement_required", "The connector requires an entitlement.", status_code=403)
        return connector

    @staticmethod
    def _adapter(connector: Connector, capability: str) -> ConnectorAdapter:
        try:
            adapter = connector_adapter_registry.get(connector.adapter_key)
        except AdapterUnavailableError as exc:
            raise CapabilityUnavailable(capability="connector_adapter", detail={"adapter_key": connector.adapter_key, "reason": exc.reason}) from exc
        if capability not in connector.capabilities or capability not in adapter.descriptor.capabilities:
            raise CapabilityUnavailable(capability=f"connector_{capability}", detail={"adapter_key": connector.adapter_key})
        return adapter

    def create(self, tenant_id: UUID, actor_id: UUID, data: Mapping[str, object]) -> Integration:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        connector_input = data.get("connector_id", data.get("connector"))
        connector_id = connector_input.id if isinstance(connector_input, Connector) else connector_input
        connector = self._connector(tenant_id, _uuid(connector_id, "connector_id"))
        config = _safe_mapping(tenant_id, data.get("config", {}), "config")
        _validate_schema(config, connector.schema)
        if data.get("integration_type", connector.connector_type) != connector.connector_type:
            raise IntegrationPlatformError("connector_type_mismatch", "Integration type must match the connector.", status_code=400)
        # Adapter validation is authoritative when an adapter is installed.
        adapter = self._adapter(connector, ConnectorCapability.TEST)
        normalized = _unwrap(adapter.validate_config(config))
        if not isinstance(normalized, Mapping):
            raise IntegrationPlatformError("invalid_adapter_result", "Adapter configuration validation returned an invalid value.", status_code=503)
        with transaction.atomic():
            integration = Integration(
                tenant_id=tenant_id,
                connector=connector,
                name=_configured_text(tenant_id, data.get("name"), "name"),
                description=str(data.get("description") or ""),
                integration_type=connector.connector_type,
                config=dict(normalized),
                created_by=actor_id,
            )
            _model_validation(integration)
            integration.save()
            _publish(tenant_id, "integration", integration.id, "integration.created", {"actor_id": str(actor_id), "adapter_key": connector.adapter_key})
            return integration

    def update(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, data: Mapping[str, object]) -> Integration:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        forbidden = set(data) - {"name", "description", "config"}
        if forbidden:
            raise IntegrationPlatformError("immutable_field", f"Fields cannot be updated: {', '.join(sorted(forbidden))}.", status_code=400)
        with transaction.atomic():
            integration = Integration.objects.select_for_update().for_tenant(tenant_id).filter(pk=integration_id, is_deleted=False).first()
            if integration is None:
                raise NotFound()
            if "name" in data:
                integration.name = _configured_text(tenant_id, data["name"], "name")
            if "description" in data:
                integration.description = str(data["description"] or "")
            if "config" in data:
                config = _safe_mapping(tenant_id, data["config"], "config")
                _validate_schema(config, integration.connector.schema)
                normalized = _unwrap(self._adapter(integration.connector, ConnectorCapability.TEST).validate_config(config))
                if not isinstance(normalized, Mapping):
                    raise IntegrationPlatformError("invalid_adapter_result", "Adapter configuration validation returned an invalid value.", status_code=503)
                integration.config = dict(normalized)
            integration.updated_by = actor_id
            _model_validation(integration)
            integration.save()
            _publish(tenant_id, "integration", integration.id, "integration.updated", {"actor_id": str(actor_id), "adapter_key": integration.connector.adapter_key})
            return integration

    def soft_delete(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID) -> None:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            integration = Integration.objects.select_for_update().for_tenant(tenant_id).filter(pk=integration_id, is_deleted=False).first()
            if integration is None:
                raise NotFound()
            if integration.status != IntegrationStatus.INACTIVE:
                raise IntegrationPlatformError("invalid_state", "Only inactive integrations can be deleted.", status_code=409)
            for credential in IntegrationCredential.objects.select_for_update().for_tenant(tenant_id).filter(integration=integration, status=CredentialStatus.ACTIVE):
                self.credentials.revoke(tenant_id, actor_id, credential.id, f"integration-delete:{integration.id}:{credential.id}")
            integration.is_deleted, integration.deleted_at, integration.deleted_by = True, timezone.now(), actor_id
            integration.updated_by = actor_id
            integration.save(update_fields=("is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"))
            _publish(tenant_id, "integration", integration.id, "integration.deleted", {"actor_id": str(actor_id), "adapter_key": integration.connector.adapter_key})

    def activate(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, transition_key: str) -> Integration:
        del actor_id, transition_key
        integration = _active(Integration, _uuid(tenant_id, "tenant_id"), integration_id)
        # test_succeeded is deliberately the only activation edge.
        if integration.status != IntegrationStatus.ACTIVE or integration.last_tested_at is None:
            raise IntegrationPlatformError("successful_test_required", "A current successful test is required for activation.", status_code=409)
        return integration

    def deactivate(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, transition_key: str) -> Integration:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        with transaction.atomic():
            integration = _apply_transition(INTEGRATION_STATE_MACHINE, "integration_transitions", integration, "deactivate", tenant_id=tenant_id, transition_key=_configured_text(tenant_id, transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Integration deactivated"))
            _publish(tenant_id, "integration", integration.id, "integration.updated", {"actor_id": str(actor_id), "action": "deactivate", "adapter_key": integration.connector.adapter_key})
            return integration

    def request_test(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, idempotency_key: str) -> AsyncJob:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        self._adapter(integration.connector, ConnectorCapability.TEST)
        key = _configured_text(tenant_id, idempotency_key, "idempotency_key")
        with transaction.atomic():
            integration = _apply_transition(INTEGRATION_STATE_MACHINE, "integration_transitions", integration, "request_test", tenant_id=tenant_id, transition_key=key, metadata=_transition_metadata(actor_id, "Connection test requested"))
            try:
                job = enqueue(tenant_id, actor_id, self.TEST_COMMAND, {"integration_id": str(integration.id)}, f"{self.TEST_COMMAND}:{key}")
            except Exception as exc:
                raise CapabilityUnavailable(capability="durable_job_dispatch") from exc
            integration.last_test_job_id = job.id
            integration.save(update_fields=("last_test_job_id", "updated_at"))
            _publish(tenant_id, "integration", integration.id, "integration.test.requested", {"actor_id": str(actor_id), "job_id": str(job.id), "adapter_key": integration.connector.adapter_key})
            return job

    def execute_test(self, tenant_id: UUID, job: AsyncJob) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        if job.tenant_id != tenant_id or job.command != self.TEST_COMMAND:
            raise NotFound()
        integration = _active(Integration, tenant_id, _uuid(job.payload.get("integration_id"), "integration_id"))
        if integration.status != IntegrationStatus.TESTING or integration.last_test_job_id != job.id:
            raise IntegrationPlatformError("stale_job", "This connection-test job is no longer current.", status_code=409)
        adapter = self._adapter(integration.connector, ConnectorCapability.TEST)
        credential = self.credentials.resolve_any_active(tenant_id, integration.id)
        started = time.monotonic()
        try:
            result = adapter.test_connection(integration.config, credential)
            if not isinstance(result, OperationResult):
                raise IntegrationPlatformError("invalid_adapter_result", "The adapter returned invalid test evidence.", status_code=503)
        except Exception as exc:
            result = OperationResult.failed(code="dependency_failure", message="The connector test failed.", provider=integration.connector.adapter_key, http_status=422)
            logger.warning(
                "integration.test.failed",
                extra={
                    "correlation_id": job.correlation_id or _correlation_id(),
                    "tenant_id": str(tenant_id),
                    "aggregate_id": str(integration.id),
                    "job_id": str(job.id),
                    "error_code": type(exc).__name__,
                },
            )
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        with transaction.atomic():
            integration.last_tested_at = timezone.now()
            integration.last_error_code = result.error_code or ""
            integration.last_error_message = result.message or ""
            integration.save(update_fields=("last_tested_at", "last_error_code", "last_error_message", "updated_at"))
            command = "test_succeeded" if result.status == "succeeded" else "test_failed"
            integration = _apply_transition(INTEGRATION_STATE_MACHINE, "integration_transitions", integration, command, tenant_id=tenant_id, transition_key=f"job:{job.id}:{command}", metadata=_transition_metadata(None, "Connection test completed", job_id=str(job.id), duration_ms=duration_ms, outcome=result.status))
            event = "integration.test.succeeded" if result.status == "succeeded" else "integration.test.failed"
            _publish(tenant_id, "integration", integration.id, event, {"job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "duration_ms": duration_ms, "outcome": result.status, "error_code": result.error_code or ""})
        if result.status != "succeeded":
            return OperationResult.failed(code=result.error_code or "connection_test_failed", message=result.message or "The connector test failed.", evidence={"job_id": str(job.id), "duration_ms": duration_ms}, provider=integration.connector.adapter_key, http_status=result.http_status or 422)
        return OperationResult.succeeded({"integration_id": str(integration.id), "status": integration.status, "duration_ms": duration_ms}, evidence={**dict(result.evidence), "job_id": str(job.id), "duration_ms": duration_ms}, provider=integration.connector.adapter_key)

    def request_sync(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, direction: str, mapping_ids: Sequence[UUID], idempotency_key: str) -> AsyncJob:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        if integration.status != IntegrationStatus.ACTIVE:
            raise IntegrationPlatformError("invalid_state", "Only active integrations can synchronize.", status_code=409)
        allowed_directions = setting(runtime_configuration(tenant_id), "synchronization.directions")
        if not isinstance(allowed_directions, list) or direction not in allowed_directions:
            raise CapabilityUnavailable(capability=f"synchronization_{direction}")
        self._adapter(integration.connector, direction)
        ids = [_uuid(value, "mapping_id") for value in mapping_ids]
        if len(ids) != len(set(ids)):
            raise IntegrationPlatformError("validation_error", "mapping_ids must be unique.", status_code=400)
        found = set(DataMapping.objects.for_tenant(tenant_id).filter(integration=integration, is_deleted=False, id__in=ids).values_list("id", flat=True))
        if found != set(ids):
            raise NotFound()
        try:
            quota_cost = int(setting(runtime_configuration(tenant_id), "synchronization.quota_cost"))
            quota = self.quotas.consume(tenant_id, "integration_platform.integration:sync", cost=quota_cost)
        except Exception as exc:
            raise CapabilityUnavailable(capability="sync_quota") from exc
        if not quota.allowed:
            raise IntegrationPlatformError("quota_exceeded", "The synchronization quota is exhausted.", status_code=429)
        key = _configured_text(tenant_id, idempotency_key, "idempotency_key")
        try:
            job = enqueue(tenant_id, actor_id, self.SYNC_COMMAND, {"integration_id": str(integration.id), "direction": direction, "mapping_ids": [str(value) for value in ids]}, f"{self.SYNC_COMMAND}:{key}")
        except Exception as exc:
            raise CapabilityUnavailable(capability="durable_job_dispatch") from exc
        integration.last_sync_job_id = job.id
        integration.save(update_fields=("last_sync_job_id", "updated_at"))
        _publish(tenant_id, "integration", integration.id, "integration.sync.requested", {"actor_id": str(actor_id), "job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "direction": direction})
        return job

    def request_sync_governed(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        integration_id: UUID,
        direction: str,
        mapping_ids: Sequence[UUID],
        idempotency_key: str,
    ) -> AsyncJob:
        """Public preflight that rejects unavailable capabilities before enqueue."""

        policy = runtime_configuration(_uuid(tenant_id, "tenant_id"))
        if direction == "push":
            flags = setting(policy, "feature_flags.push_synchronization")
            if not isinstance(flags, Mapping) or flags.get("enabled") is not True:
                raise CapabilityUnavailable(capability="governed_push_source")
        return self.request_sync(
            tenant_id, actor_id, integration_id, direction, mapping_ids, idempotency_key
        )

    def execute_sync(self, tenant_id: UUID, job: AsyncJob) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        if job.tenant_id != tenant_id or job.command != self.SYNC_COMMAND:
            raise NotFound()
        integration = _active(Integration, tenant_id, _uuid(job.payload.get("integration_id"), "integration_id"))
        direction = job.payload.get("direction")
        if direction not in {"pull", "push"}:
            raise IntegrationPlatformError("invalid_job_payload", "Synchronization direction is invalid.", status_code=422)
        adapter = self._adapter(integration.connector, str(direction))
        credential = self.credentials.resolve_any_active(tenant_id, integration.id)
        mapping_ids = [_uuid(value, "mapping_id") for value in job.payload.get("mapping_ids", [])]
        mappings = list(DataMapping.objects.for_tenant(tenant_id).filter(integration=integration, is_deleted=False, id__in=mapping_ids))
        if len(mappings) != len(mapping_ids):
            raise NotFound()
        if direction == "push":
            failure = OperationResult.failed(
                code="sync_source_unavailable",
                message="No governed source contract supplied records for this push job.",
                evidence={"job_id": str(job.id)},
                provider=integration.connector.adapter_key,
                http_status=503,
            )
            _publish(tenant_id, "integration", integration.id, "integration.sync.failed", {"job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "error_code": failure.error_code or ""})
            return failure
        batch_limit = int(setting(runtime_configuration(tenant_id), "synchronization.pull_batch_limit"))
        result = adapter.pull(integration.config, credential, RecordCursor(), batch_limit)
        if not isinstance(result, OperationResult) or result.status != "succeeded" or not isinstance(result.value, RecordBatch):
            if isinstance(result, OperationResult):
                return OperationResult.failed(code=result.error_code or "sync_pull_failed", message=result.message or "The connector pull failed.", evidence={"job_id": str(job.id)}, provider=integration.connector.adapter_key, http_status=result.http_status or 422)
            raise IntegrationPlatformError("invalid_adapter_result", "The adapter returned an invalid record batch.", status_code=503)
        batch = result.value
        transformed = DataMappingService().transform(tenant_id, integration.id, mapping_ids, batch.records)
        if batch.source_count == 0 and batch.source_exhausted:
            evidence = {
                "job_id": str(job.id),
                "records_read": 0,
                "records_written": 0,
                "records_failed": 0,
                "source_exhausted": True,
            }
            _publish(
                tenant_id,
                "integration",
                integration.id,
                "integration.sync.succeeded",
                {"adapter_key": integration.connector.adapter_key, **evidence},
            )
            return OperationResult.succeeded(evidence, evidence=evidence, provider=integration.connector.adapter_key)
        persisted = result.evidence.get("persisted_count")
        if not isinstance(persisted, int) or persisted != len(transformed.records):
            failure = OperationResult.failed(code="sync_sink_unavailable", message="No governed sink contract proved persistence of transformed records.", evidence={"job_id": str(job.id), "records_read": batch.source_count, "records_failed": len(transformed.failures)}, provider=integration.connector.adapter_key, http_status=422)
            _publish(tenant_id, "integration", integration.id, "integration.sync.failed", {"job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "error_code": failure.error_code or "", "records_read": batch.source_count, "records_failed": len(transformed.failures)})
            return failure
        evidence = {"job_id": str(job.id), "records_read": batch.source_count, "records_written": persisted, "records_failed": len(transformed.failures), "source_exhausted": batch.source_exhausted}
        _publish(tenant_id, "integration", integration.id, "integration.sync.succeeded", {"adapter_key": integration.connector.adapter_key, **evidence})
        return OperationResult.succeeded(evidence, evidence=evidence, provider=integration.connector.adapter_key)

    def get_job(self, tenant_id: UUID, integration_id: UUID, job_id: UUID) -> AsyncJob:
        tenant_id = _uuid(tenant_id, "tenant_id")
        integration = _active(Integration, tenant_id, integration_id)
        job = AsyncJob.objects.for_tenant(tenant_id).filter(pk=job_id, payload__integration_id=str(integration.id)).first()
        if job is None:
            raise NotFound()
        return job


class WebhookService:
    DELIVERY_COMMAND = "integration_platform.webhook.deliver"
    RECEIVE_COMMAND = "integration_platform.webhook.receive"

    @staticmethod
    def _new_secret(tenant_id: UUID) -> str:
        return secrets.token_urlsafe(int(setting(runtime_configuration(tenant_id), "security.signing_secret_bytes")))

    def create(self, tenant_id: UUID, actor_id: UUID, data: Mapping[str, object]) -> SecretOnce:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        policy = runtime_configuration(tenant_id)
        secret = self._new_secret(tenant_id)
        with transaction.atomic():
            webhook = Webhook(
                tenant_id=tenant_id,
                created_by=actor_id,
                name=_configured_text(tenant_id, data.get("name"), "name"),
                direction=str(data.get("direction") or ""),
                url=str(data.get("url") or ""),
                events=list(data.get("events") or []),
                encrypted_signing_secret=_encrypt_secret(secret, "webhook_secret_encryption"),
                config=_safe_mapping(tenant_id, data.get("config", {}), "config"),
                timeout_seconds=int(data.get("timeout_seconds", setting(policy, "webhooks.timeout_seconds_default"))),
                max_attempts=int(data.get("max_attempts", setting(policy, "webhooks.max_attempts_default"))),
            )
            _model_validation(webhook)
            webhook.save()
            _publish(tenant_id, "webhook", webhook.id, "webhook.created", {"actor_id": str(actor_id), "direction": webhook.direction})
            return SecretOnce(webhook, secret)

    def update(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, data: Mapping[str, object]) -> Webhook:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        forbidden = set(data) - {"name", "url", "events", "config", "timeout_seconds", "max_attempts"}
        if forbidden:
            raise IntegrationPlatformError("immutable_field", f"Fields cannot be updated: {', '.join(sorted(forbidden))}.", status_code=400)
        with transaction.atomic():
            webhook = Webhook.objects.select_for_update().for_tenant(tenant_id).filter(pk=webhook_id, is_deleted=False).first()
            if webhook is None:
                raise NotFound()
            for field in ("name", "url", "events", "timeout_seconds", "max_attempts"):
                if field in data:
                    setattr(webhook, field, data[field])
            if "config" in data:
                webhook.config = _safe_mapping(tenant_id, data["config"], "config")
            webhook.updated_by = actor_id
            _model_validation(webhook)
            webhook.save()
            _publish(tenant_id, "webhook", webhook.id, "webhook.updated", {"actor_id": str(actor_id), "direction": webhook.direction})
            return webhook

    def soft_delete(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID) -> None:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        webhook = _active(Webhook, tenant_id, webhook_id)
        if webhook.status != WebhookStatus.INACTIVE:
            raise IntegrationPlatformError("invalid_state", "Only inactive webhooks can be deleted.", status_code=409)
        with transaction.atomic():
            webhook.is_deleted, webhook.deleted_at, webhook.deleted_by = True, timezone.now(), actor_id
            webhook.updated_by = actor_id
            webhook.save(update_fields=("is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"))
            _publish(tenant_id, "webhook", webhook.id, "webhook.deleted", {"actor_id": str(actor_id), "direction": webhook.direction})

    def activate(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, transition_key: str) -> Webhook:
        return self._transition(tenant_id, actor_id, webhook_id, "activate", transition_key)

    def deactivate(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, transition_key: str) -> Webhook:
        return self._transition(tenant_id, actor_id, webhook_id, "deactivate", transition_key)

    def _transition(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, command: str, transition_key: str) -> Webhook:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        webhook = _active(Webhook, tenant_id, webhook_id)
        with transaction.atomic():
            webhook = _apply_transition(WEBHOOK_STATE_MACHINE, "webhook_transitions", webhook, command, tenant_id=tenant_id, transition_key=_configured_text(tenant_id, transition_key, "transition_key"), metadata=_transition_metadata(actor_id, f"Webhook {command}d"))
            _publish(tenant_id, "webhook", webhook.id, "webhook.updated", {"actor_id": str(actor_id), "action": command, "direction": webhook.direction})
            return webhook

    def rotate_secret(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, transition_key: str) -> SecretOnce:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        key = _configured_text(tenant_id, transition_key, "transition_key")
        secret = self._new_secret(tenant_id)
        with transaction.atomic():
            webhook = Webhook.objects.select_for_update().for_tenant(tenant_id).filter(pk=webhook_id, is_deleted=False).first()
            if webhook is None:
                raise NotFound()
            if any(item.get("transition_key") == key for item in webhook.transition_history):
                raise IntegrationPlatformError("secret_already_rotated", "The rotated secret cannot be returned again.", status_code=409)
            webhook.encrypted_signing_secret = _encrypt_secret(secret, "webhook_secret_encryption")
            webhook.updated_by = actor_id
            webhook.transition_history = [*webhook.transition_history, {"transition_key": key, "command": "rotate_secret", "from_state": webhook.status, "to_state": webhook.status, "occurred_at": timezone.now().isoformat(), "metadata": _transition_metadata(actor_id, "Webhook signing secret rotated")}]
            webhook.save(update_fields=("encrypted_signing_secret", "updated_by", "transition_history", "updated_at"))
            _publish(tenant_id, "webhook", webhook.id, "webhook.updated", {"actor_id": str(actor_id), "action": "rotate_secret", "direction": webhook.direction})
            return SecretOnce(webhook, secret)

    def verify_inbound(self, public_id: UUID, timestamp: str, nonce: str, signature: str, raw_body: bytes) -> Webhook:
        public_id = _uuid(public_id, "public_id")
        webhook = Webhook.objects.filter(public_id=public_id, direction=WebhookDirection.INBOUND, status=WebhookStatus.ACTIVE, is_deleted=False).first()
        if webhook is None:
            raise NotFound()
        policy = runtime_configuration(webhook.tenant_id)
        payload_max = int(setting(policy, "security.payload_max_bytes"))
        if not isinstance(raw_body, bytes) or len(raw_body) > payload_max:
            raise IntegrationPlatformError("invalid_payload", "Webhook body is invalid or too large.", status_code=400)
        try:
            issued_at = datetime.fromtimestamp(int(timestamp), tz=datetime_timezone.utc)
        except (TypeError, ValueError, OSError) as exc:
            raise IntegrationPlatformError("invalid_timestamp", "Webhook timestamp is invalid.", status_code=401) from exc
        if abs((timezone.now() - issued_at).total_seconds()) > int(setting(policy, "security.signature_window_seconds")):
            raise IntegrationPlatformError("stale_signature", "Webhook signature timestamp is outside the allowed window.", status_code=401)
        nonce = _text(nonce, "nonce", int(setting(policy, "validation.nonce_max_length")))
        signature = _text(signature, "signature", int(setting(policy, "validation.signature_max_length")))
        try:
            secret = EncryptionService.decrypt(webhook.encrypted_signing_secret)
        except Exception as exc:
            raise CapabilityUnavailable(capability="webhook_signature_verification") from exc
        canonical = f"{INBOUND_SIGNATURE_VERSION}.{timestamp}.{nonce}.".encode("ascii") + raw_body
        expected = f"sha256={hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).hexdigest()}"
        if not hmac.compare_digest(expected, signature):
            raise IntegrationPlatformError("invalid_signature", "Webhook signature verification failed.", status_code=401)
        nonce_key = f"integration-platform:webhook-nonce:{webhook.public_id}:{hashlib.sha256(nonce.encode()).hexdigest()}"
        try:
            accepted = cache.add(nonce_key, "used", timeout=int(setting(policy, "security.signature_window_seconds")))
        except Exception as exc:
            raise CapabilityUnavailable(capability="webhook_replay_protection") from exc
        if not accepted:
            raise IntegrationPlatformError("nonce_replayed", "Webhook nonce has already been used.", status_code=409)
        return webhook

    def receive(self, public_id: UUID, headers: Mapping[str, str], raw_body: bytes) -> AsyncJob:
        # This method owns verification and nonce consumption.  API callers must
        # not invoke verify_inbound separately.
        normalized_headers = {str(key).lower(): value for key, value in headers.items()}
        timestamp = normalized_headers.get(INBOUND_TIMESTAMP_HEADER.lower(), normalized_headers.get("x-saraise-timestamp", ""))
        nonce = normalized_headers.get(INBOUND_NONCE_HEADER.lower(), normalized_headers.get("x-saraise-nonce", ""))
        signature = normalized_headers.get(INBOUND_SIGNATURE_HEADER.lower(), normalized_headers.get("x-saraise-signature", ""))
        webhook = self.verify_inbound(public_id, timestamp, nonce, signature, raw_body)
        try:
            parsed: object = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrationPlatformError("invalid_json", "Webhook body must be valid UTF-8 JSON.", status_code=400) from exc
        secret_keys = frozenset(str(value) for value in setting(runtime_configuration(webhook.tenant_id), "security.secret_field_names"))
        payload = _redact(parsed, secret_keys)
        body_hash = hashlib.sha256(raw_body).hexdigest()
        with transaction.atomic():
            try:
                job = enqueue(webhook.tenant_id, webhook.created_by, self.RECEIVE_COMMAND, {"webhook_id": str(webhook.id), "payload": payload, "payload_hash": body_hash}, f"{self.RECEIVE_COMMAND}:{webhook.public_id}:{body_hash}:{nonce}")
            except Exception as exc:
                raise CapabilityUnavailable(capability="durable_job_dispatch") from exc
            webhook.last_received_at = timezone.now()
            webhook.save(update_fields=("last_received_at", "updated_at"))
            _publish(webhook.tenant_id, "webhook", webhook.id, "webhook.received", {"job_id": str(job.id), "event": "inbound", "payload_hash": body_hash})
            return job

    def enqueue_delivery(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, event: str, payload: Mapping[str, object], idempotency_key: str) -> WebhookDelivery:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        webhook = _active(Webhook, tenant_id, webhook_id)
        if webhook.direction != WebhookDirection.OUTBOUND or webhook.status != WebhookStatus.ACTIVE:
            raise IntegrationPlatformError("invalid_state", "An active outbound webhook is required.", status_code=409)
        event = _configured_text(tenant_id, event, "event", "validation.event_name_max_length")
        if event not in webhook.events:
            raise IntegrationPlatformError("event_not_subscribed", "The webhook does not subscribe to this event.", status_code=400)
        secret_keys = frozenset(str(value) for value in setting(runtime_configuration(tenant_id), "security.secret_field_names"))
        safe_payload = _redact(dict(payload), secret_keys)
        canonical = json.dumps(safe_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        key = _configured_text(tenant_id, idempotency_key, "idempotency_key")
        with transaction.atomic():
            existing = WebhookDelivery.objects.for_tenant(tenant_id).filter(webhook=webhook, idempotency_key=key).first()
            if existing is not None:
                return existing
            delivery_id = uuid.uuid4()
            try:
                job = enqueue(tenant_id, actor_id, self.DELIVERY_COMMAND, {"delivery_id": str(delivery_id)}, f"{self.DELIVERY_COMMAND}:{key}")
            except Exception as exc:
                raise CapabilityUnavailable(capability="durable_job_dispatch") from exc
            delivery = WebhookDelivery(
                id=delivery_id,
                tenant_id=tenant_id,
                webhook=webhook,
                event=event,
                payload=safe_payload,
                payload_hash=hashlib.sha256(canonical).hexdigest(),
                idempotency_key=key,
                max_attempts=webhook.max_attempts,
                job_id=job.id,
                correlation_id=job.correlation_id,
            )
            _model_validation(delivery)
            delivery.save()
            _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.queued", {"actor_id": str(actor_id), "job_id": str(job.id), "webhook_id": str(webhook.id), "attempt_count": 0})
            return delivery

    def redrive_delivery(self, tenant_id: UUID, actor_id: UUID, delivery_id: UUID, transition_key: str) -> WebhookDelivery:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        delivery = WebhookDelivery.objects.for_tenant(tenant_id).filter(pk=delivery_id).first()
        if delivery is None:
            raise NotFound()
        with transaction.atomic():
            delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "redrive", tenant_id=tenant_id, transition_key=_configured_text(tenant_id, transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Delivery redriven"))
            job = enqueue(tenant_id, actor_id, self.DELIVERY_COMMAND, {"delivery_id": str(delivery.id)}, f"{self.DELIVERY_COMMAND}:redrive:{transition_key}")
            delivery.job_id, delivery.next_attempt_at = job.id, None
            delivery.save(update_fields=("job_id", "next_attempt_at", "updated_at"))
            _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.redriven", {"actor_id": str(actor_id), "job_id": str(job.id), "webhook_id": str(delivery.webhook_id), "attempt_count": delivery.attempt_count})
            return delivery


class WebhookDeliveryWorker:
    def __init__(self, *, http_client: ResilientHttpClient | None = None) -> None:
        self.http_client = http_client

    def _client(self, webhook: Webhook) -> ResilientHttpClient:
        if self.http_client is not None:
            return self.http_client
        policy = runtime_configuration(webhook.tenant_id)
        return ResilientHttpClient(
            connect_timeout=min(int(setting(policy, "webhooks.connect_timeout_max_seconds")), webhook.timeout_seconds),
            read_timeout=webhook.timeout_seconds,
            max_retries=int(setting(policy, "webhooks.http_client_retries")),
        )

    def execute(self, tenant_id: UUID, job: AsyncJob) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        if job.tenant_id != tenant_id or job.command != WebhookService.DELIVERY_COMMAND:
            raise NotFound()
        delivery = WebhookDelivery.objects.for_tenant(tenant_id).select_related("webhook").filter(pk=job.payload.get("delivery_id"), job_id=job.id).first()
        if delivery is None:
            raise NotFound()
        webhook = delivery.webhook
        if delivery.status == DeliveryStatus.RETRYING:
            if delivery.next_attempt_at is None or delivery.next_attempt_at > timezone.now():
                raise IntegrationPlatformError(
                    "retry_not_due",
                    "The delivery retry is not due yet.",
                    status_code=409,
                )
            delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "requeue", tenant_id=tenant_id, transition_key=f"job:{job.id}:requeue", metadata=_transition_metadata(None, "Retry became due"))
        delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "start", tenant_id=tenant_id, transition_key=f"job:{job.id}:start", metadata=_transition_metadata(None, "Delivery attempt started"))
        delivery.attempt_count += 1
        delivery.save(update_fields=("attempt_count", "updated_at"))
        canonical = json.dumps(delivery.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        timestamp = str(int(timezone.now().timestamp()))
        nonce = secrets.token_urlsafe(int(setting(runtime_configuration(tenant_id), "security.outbound_nonce_bytes")))
        try:
            secret = EncryptionService.decrypt(webhook.encrypted_signing_secret)
        except Exception as exc:
            return self.move_to_dead_letter(tenant_id, delivery.id, exc)
        signature = hmac.new(
            secret.encode(),
            f"{INBOUND_SIGNATURE_VERSION}.{timestamp}.{nonce}.".encode("ascii") + canonical,
            hashlib.sha256,
        ).hexdigest()
        started = time.monotonic()
        try:
            response = self._client(webhook).post(
                webhook.url,
                dependency=str(webhook.config.get("dependency") or "integration_webhook"),
                content=canonical,
                headers={
                    "Content-Type": "application/json",
                    INBOUND_TIMESTAMP_HEADER: timestamp,
                    INBOUND_NONCE_HEADER: nonce,
                    INBOUND_SIGNATURE_HEADER: f"sha256={signature}",
                    "Idempotency-Key": delivery.idempotency_key,
                },
                correlation_id=delivery.correlation_id,
            )
            code = response.status_code
        except Exception as exc:
            if delivery.attempt_count < delivery.max_attempts:
                return self.schedule_retry(tenant_id, delivery.id, exc)
            return self.move_to_dead_letter(tenant_id, delivery.id, exc)
        duration = max(0, round((time.monotonic() - started) * 1000))
        delivery.response_code, delivery.duration_ms = code, duration
        delivery.save(update_fields=("response_code", "duration_ms", "updated_at"))
        policy = runtime_configuration(tenant_id)
        if int(setting(policy, "webhooks.success_status_min")) <= code <= int(setting(policy, "webhooks.success_status_max")):
            self._record_attempt(delivery, "delivered")
            delivery.delivered_at = timezone.now()
            delivery.save(update_fields=("delivered_at", "updated_at"))
            delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "succeed", tenant_id=tenant_id, transition_key=f"job:{job.id}:succeed", metadata=_transition_metadata(None, "Provider acknowledged delivery", response_code=code, duration_ms=duration))
            webhook.last_delivered_at = delivery.delivered_at
            webhook.save(update_fields=("last_delivered_at", "updated_at"))
            evidence = {"delivery_id": str(delivery.id), "attempt_count": delivery.attempt_count, "response_code": code, "duration_ms": duration}
            _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.succeeded", {"job_id": str(job.id), "webhook_id": str(webhook.id), **evidence})
            return OperationResult.succeeded(evidence, evidence=evidence, provider=webhook.url.split("/", 3)[2])
        error = RuntimeError(f"HTTP {code}")
        if code in set(setting(policy, "webhooks.retry_statuses")) or code >= int(setting(policy, "webhooks.retry_server_error_min")):
            return self.schedule_retry(tenant_id, delivery.id, error) if delivery.attempt_count < delivery.max_attempts else self.move_to_dead_letter(tenant_id, delivery.id, error)
        return self.move_to_dead_letter(tenant_id, delivery.id, error)

    def schedule_retry(self, tenant_id: UUID, delivery_id: UUID, error: Exception) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        delivery = WebhookDelivery.objects.for_tenant(tenant_id).filter(pk=delivery_id).first()
        if delivery is None:
            raise NotFound()
        if delivery.attempt_count >= delivery.max_attempts:
            return self.move_to_dead_letter(tenant_id, delivery.id, error)
        retry_max = int(setting(runtime_configuration(tenant_id), "webhooks.retry_delay_max_seconds"))
        base = min(retry_max, 2 ** max(0, delivery.attempt_count - 1))
        jitter = int.from_bytes(hashlib.sha256(f"{delivery.id}:{delivery.attempt_count}".encode()).digest()[:2], "big") % max(1, base)
        delay = min(retry_max, base + jitter)
        with transaction.atomic():
            delivery.error_code, delivery.error_message = _error_code(tenant_id, error), "The delivery dependency failed transiently."
            self._record_attempt(delivery, "retrying", error_code=delivery.error_code)
            delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay)
            delivery.save(update_fields=("error_code", "error_message", "next_attempt_at", "updated_at"))
            delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "retry", tenant_id=tenant_id, transition_key=f"attempt:{delivery.attempt_count}:retry", metadata=_transition_metadata(None, "Transient delivery failure", delay_seconds=delay, error_code=delivery.error_code))
            retry_job = enqueue(
                tenant_id,
                delivery.webhook.created_by,
                WebhookService.DELIVERY_COMMAND,
                {"delivery_id": str(delivery.id)},
                f"{WebhookService.DELIVERY_COMMAND}:retry:{delivery.id}:{delivery.attempt_count}",
            )
            delivery.job_id = retry_job.id
            delivery.save(update_fields=("job_id", "updated_at"))
            OutboxEvent.objects.filter(
                tenant_id=tenant_id,
                aggregate_id=retry_job.id,
                event_type="async_job.enqueued",
            ).update(available_at=delivery.next_attempt_at)
            _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.retrying", {"job_id": str(retry_job.id), "webhook_id": str(delivery.webhook_id), "attempt_count": delivery.attempt_count, "error_code": delivery.error_code})
        return OperationResult.failed(code="delivery_retrying", message="Delivery will be retried.", evidence={"delivery_id": str(delivery.id), "next_attempt_at": delivery.next_attempt_at.isoformat(), "attempt_count": delivery.attempt_count}, provider="webhook", http_status=503)

    def move_to_dead_letter(self, tenant_id: UUID, delivery_id: UUID, error: Exception) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        delivery = WebhookDelivery.objects.for_tenant(tenant_id).filter(pk=delivery_id).first()
        if delivery is None:
            raise NotFound()
        delivery.error_code, delivery.error_message = _error_code(tenant_id, error), "The delivery could not be completed."
        self._record_attempt(delivery, "dead_letter", error_code=delivery.error_code)
        delivery.next_attempt_at = None
        delivery.save(update_fields=("error_code", "error_message", "next_attempt_at", "updated_at"))
        delivery = _apply_transition(DELIVERY_STATE_MACHINE, "delivery_transitions", delivery, "exhaust", tenant_id=tenant_id, transition_key=f"attempt:{delivery.attempt_count}:exhaust", metadata=_transition_metadata(None, "Delivery moved to dead letter", error_code=delivery.error_code))
        if delivery.webhook.status == WebhookStatus.ACTIVE:
            _apply_transition(WEBHOOK_STATE_MACHINE, "webhook_transitions", delivery.webhook, "delivery_failed", tenant_id=tenant_id, transition_key=f"delivery:{delivery.id}:failed", metadata=_transition_metadata(None, "Delivery exhausted retry policy"))
        _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.dead_lettered", {"job_id": str(delivery.job_id), "webhook_id": str(delivery.webhook_id), "attempt_count": delivery.attempt_count, "error_code": delivery.error_code})
        return OperationResult.failed(code="delivery_dead_lettered", message="Delivery moved to the dead-letter queue.", evidence={"delivery_id": str(delivery.id), "attempt_count": delivery.attempt_count}, provider="webhook", http_status=422)

    @staticmethod
    def _record_attempt(
        delivery: WebhookDelivery,
        outcome: str,
        *,
        error_code: str = "",
    ) -> WebhookDeliveryAttempt:
        """Idempotently append the immutable evidence behind the projection."""

        attempt_number = max(1, delivery.attempt_count)
        values = {
            "outcome": outcome,
            "response_code": delivery.response_code,
            "error_code": error_code,
            "duration_ms": delivery.duration_ms,
            "job_id": delivery.job_id,
            "correlation_id": delivery.correlation_id,
        }
        existing = WebhookDeliveryAttempt.objects.for_tenant(delivery.tenant_id).filter(
            delivery=delivery,
            attempt_number=attempt_number,
        ).first()
        if existing is not None:
            if any(getattr(existing, field) != value for field, value in values.items()):
                raise IntegrationPlatformError(
                    "delivery_attempt_conflict",
                    "Immutable delivery attempt evidence conflicts with the requested outcome.",
                    status_code=409,
                )
            return existing
        attempt = WebhookDeliveryAttempt(
            tenant_id=delivery.tenant_id,
            delivery=delivery,
            attempt_number=attempt_number,
            **values,
        )
        _model_validation(attempt)
        attempt.save()
        return attempt

    def recover_stale(self, tenant_id: UUID, stale_before: datetime) -> list[AsyncJob]:
        return recover_stale_jobs(_uuid(tenant_id, "tenant_id"), stale_before=stale_before)


def _error_code(tenant_id: UUID, error: Exception) -> str:
    name = type(error).__name__.lower()
    maximum = int(setting(runtime_configuration(tenant_id), "validation.error_code_max_length"))
    return name[:maximum] if name else "dependency_failure"


class DataMappingService:
    MUTABLE_FIELDS = frozenset({"name", "source_field", "target_field", "transform", "position", "is_required", "default_value"})

    def create(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, data: Mapping[str, object]) -> DataMapping:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        with transaction.atomic():
            mapping = DataMapping(
                tenant_id=tenant_id,
                integration=integration,
                created_by=actor_id,
                name=_configured_text(tenant_id, data.get("name"), "name"),
                source_field=_configured_text(tenant_id, data.get("source_field"), "source_field"),
                target_field=_configured_text(tenant_id, data.get("target_field"), "target_field"),
                transform=dict(data.get("transform") or {}),
                position=int(data.get("position", setting(runtime_configuration(tenant_id), "mapping.default_position"))),
                is_required=bool(data.get("is_required", setting(runtime_configuration(tenant_id), "mapping.default_required"))),
                default_value=data.get("default_value"),
            )
            _model_validation(mapping)
            mapping.save()
            _publish(tenant_id, "data_mapping", mapping.id, "mapping.created", {"actor_id": str(actor_id), "integration_id": str(integration.id)})
            return mapping

    def update(self, tenant_id: UUID, actor_id: UUID, mapping_id: UUID, data: Mapping[str, object]) -> DataMapping:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        unknown = set(data) - self.MUTABLE_FIELDS
        if unknown:
            raise IntegrationPlatformError("immutable_field", f"Fields cannot be updated: {', '.join(sorted(unknown))}.", status_code=400)
        with transaction.atomic():
            mapping = DataMapping.objects.select_for_update().for_tenant(tenant_id).filter(pk=mapping_id, is_deleted=False).first()
            if mapping is None:
                raise NotFound()
            for field, value in data.items():
                setattr(mapping, field, value)
            mapping.updated_by = actor_id
            _model_validation(mapping)
            mapping.save()
            _publish(tenant_id, "data_mapping", mapping.id, "mapping.updated", {"actor_id": str(actor_id), "integration_id": str(mapping.integration_id)})
            return mapping

    def soft_delete(self, tenant_id: UUID, actor_id: UUID, mapping_id: UUID) -> None:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        mapping = _active(DataMapping, tenant_id, mapping_id)
        with transaction.atomic():
            mapping.is_deleted, mapping.deleted_at, mapping.deleted_by = True, timezone.now(), actor_id
            mapping.updated_by = actor_id
            mapping.save(update_fields=("is_deleted", "deleted_at", "deleted_by", "updated_by", "updated_at"))
            _publish(tenant_id, "data_mapping", mapping.id, "mapping.deleted", {"actor_id": str(actor_id), "integration_id": str(mapping.integration_id)})

    def validate(self, tenant_id: UUID, integration_id: UUID, mappings: Sequence[Mapping[str, object] | DataMapping], source_schema: Mapping[str, object], target_schema: Mapping[str, object]) -> dict[str, object]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        integration = _active(Integration, tenant_id, integration_id)
        source_fields = set((source_schema.get("properties") or {}).keys()) if isinstance(source_schema.get("properties"), Mapping) else set()
        target_fields = set((target_schema.get("properties") or {}).keys()) if isinstance(target_schema.get("properties"), Mapping) else set()
        errors: list[dict[str, object]] = []
        for index, item in enumerate(mappings):
            if isinstance(item, DataMapping):
                if item.tenant_id != tenant_id or item.integration_id != integration.id or item.is_deleted:
                    raise NotFound()
                source, target, transform = item.source_field, item.target_field, item.transform
            else:
                source, target, transform = item.get("source_field"), item.get("target_field"), item.get("transform", {})
            try:
                transformation_registry.validate(transform)
                if source_fields and source not in source_fields:
                    raise DjangoValidationError("Unknown source field")
                if target_fields and target not in target_fields:
                    raise DjangoValidationError("Unknown target field")
            except (DjangoValidationError, IntegrationPlatformError) as exc:
                errors.append({"index": index, "message": str(exc)})
        result = {"valid": not errors, "errors": errors, "mapping_count": len(mappings)}
        _publish(tenant_id, "integration", integration.id, "mapping.validated", {"valid": not errors, "mapping_count": len(mappings), "error_count": len(errors)})
        return result

    def preview(
        self,
        tenant_id: UUID,
        integration_id: UUID,
        mapping_ids: Sequence[UUID],
        sample: Mapping[str, object] | Sequence[Mapping[str, object]],
    ) -> TransformResult:
        records = (sample,) if isinstance(sample, Mapping) else tuple(sample)
        limit = int(setting(runtime_configuration(_uuid(tenant_id, "tenant_id")), "mapping.preview_record_limit"))
        if not records or len(records) > limit or any(not isinstance(record, Mapping) for record in records):
            raise IntegrationPlatformError(
                "validation_error",
                f"sample must contain between 1 and {limit} JSON objects.",
                status_code=400,
            )
        return self.transform(tenant_id, integration_id, mapping_ids, records)

    def transform(self, tenant_id: UUID, integration_id: UUID, mapping_ids: Sequence[UUID], records: Sequence[Mapping[str, object]]) -> TransformResult:
        tenant_id = _uuid(tenant_id, "tenant_id")
        integration = _active(Integration, tenant_id, integration_id)
        ids = [_uuid(value, "mapping_id") for value in mapping_ids]
        mappings = list(DataMapping.objects.for_tenant(tenant_id).filter(integration=integration, id__in=ids, is_deleted=False).order_by("position", "id"))
        if len(mappings) != len(set(ids)):
            raise NotFound()
        output: list[dict[str, object]] = []
        failures: list[MappingFailure] = []
        for index, record in enumerate(records):
            transformed: dict[str, object] = {}
            record_failed = False
            for mapping in mappings:
                value = record.get(mapping.source_field, mapping.default_value)
                if mapping.is_required and value is None:
                    failures.append(MappingFailure(index, mapping.id, mapping.source_field, mapping.target_field, "required_value_missing", "A required source value is missing."))
                    record_failed = True
                    continue
                try:
                    transformed[mapping.target_field] = transformation_registry.apply(value, mapping.transform)
                except DjangoValidationError:
                    failures.append(MappingFailure(index, mapping.id, mapping.source_field, mapping.target_field, "transformation_failed", "The registered transformation rejected this value."))
                    record_failed = True
            if not record_failed:
                output.append(transformed)
        return TransformResult(tuple(output), tuple(failures))


# Stable instances are convenient for controllers while constructors remain
# public for dependency-injected tests and paid extensions.
connector_service = ConnectorService()
configuration_service = ConfigurationService()
credential_service = CredentialService()
integration_service = IntegrationService(credentials=credential_service)
webhook_service = WebhookService()
delivery_worker = WebhookDeliveryWorker()
mapping_service = DataMappingService()


__all__ = [
    "ConfigurationService", "ConnectorService", "CredentialService", "DataMappingService", "IntegrationPlatformError",
    "IntegrationService", "MappingFailure", "SecretOnce", "TransformResult", "WebhookDeliveryWorker",
    "WebhookService", "configuration_service", "connector_service", "credential_service", "delivery_worker",
    "durable_job_receipt", "durable_job_state", "integration_service", "mapping_service",
    "runtime_configuration", "webhook_service", "EncryptionService",
]

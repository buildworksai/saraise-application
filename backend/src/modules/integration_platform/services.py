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
from .models import (
    Connector,
    ConnectorCapability,
    CredentialStatus,
    CredentialType,
    DataMapping,
    DeliveryStatus,
    Integration,
    IntegrationCredential,
    IntegrationStatus,
    Webhook,
    WebhookDelivery,
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
SECRET_KEYS = frozenset({"password", "secret", "token", "authorization", "api_key", "apikey", "credential", "private_key"})
INBOUND_TIMESTAMP_HEADER = "X-SARAISE-Webhook-Timestamp"
INBOUND_NONCE_HEADER = "X-SARAISE-Webhook-Nonce"
INBOUND_SIGNATURE_HEADER = "X-SARAISE-Webhook-Signature"
INBOUND_SIGNATURE_VERSION = "v1"
INBOUND_WINDOW_SECONDS = 300
MAX_BODY_BYTES = 1024 * 1024


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


def _text(value: object, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IntegrationPlatformError("validation_error", f"{field} is required.", status_code=400)
    normalized = value.strip()
    if len(normalized) > maximum:
        raise IntegrationPlatformError("validation_error", f"{field} exceeds {maximum} characters.", status_code=400)
    return normalized


def _encrypt_secret(value: str, capability: str) -> str:
    try:
        return EncryptionService.encrypt(value)
    except EncryptionConfigurationError as exc:
        raise CapabilityUnavailable(capability=capability) from exc


def _safe_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise IntegrationPlatformError("validation_error", f"{field} must be an object.", status_code=400)
    result = dict(value)
    _reject_secrets(result, field)
    try:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise IntegrationPlatformError("validation_error", f"{field} must contain JSON values.", status_code=400) from exc
    if len(encoded.encode("utf-8")) > MAX_BODY_BYTES:
        raise IntegrationPlatformError("payload_too_large", f"{field} exceeds 1 MiB.", status_code=413)
    return result


def _reject_secrets(value: object, field: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SECRET_KEYS or any(part in normalized for part in ("password", "secret", "authorization")):
                raise IntegrationPlatformError("secret_in_config", f"{field} cannot contain credential-like keys.", status_code=400)
            _reject_secrets(child, field)
    elif isinstance(value, list):
        for child in value:
            _reject_secrets(child, field)


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower().replace("-", "_") in SECRET_KEYS else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child) for child in value]
    return value


def _correlation_id() -> str:
    # Correlation is generated by core middleware/job orchestration, never here.
    return get_correlation_id() or "correlation-unavailable"


def _transition_metadata(actor_id: UUID | None, reason: str, **evidence: object) -> dict[str, object]:
    return {"actor_id": str(actor_id) if actor_id else "system", "reason": reason, "correlation_id": _correlation_id(), **evidence}


def _publish(tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, payload: Mapping[str, object]) -> OutboxEvent:
    safe = _redact(dict(payload))
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


class ConnectorService:
    def __init__(self, *, entitlements: EntitlementService | None = None) -> None:
        self.entitlements = entitlements or EntitlementService()

    def _entitled(self, tenant_id: UUID, connector: Connector) -> bool:
        if not connector.required_entitlement:
            return True
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
    def _plaintext(value: object) -> str:
        if isinstance(value, str):
            if not value:
                raise IntegrationPlatformError("validation_error", "Credential plaintext is required.", status_code=400)
            return value
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise IntegrationPlatformError("validation_error", "Credential plaintext must be text or JSON.", status_code=400) from exc

    @staticmethod
    def _hint(plaintext: str) -> str:
        return f"••••{plaintext[-4:]}" if len(plaintext) >= 4 else "••••"

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
        raw = self._plaintext(plaintext)
        with transaction.atomic():
            if IntegrationCredential.objects.for_tenant(tenant_id).filter(integration=integration, credential_type=credential_type, status=CredentialStatus.ACTIVE).exists():
                raise IntegrationPlatformError("active_credential_exists", "Rotate the active credential instead.", status_code=409)
            credential = IntegrationCredential(
                tenant_id=tenant_id,
                integration=integration,
                credential_type=credential_type,
                encrypted_value=_encrypt_secret(raw, "credential_encryption"),
                display_hint=self._hint(raw),
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
        raw = self._plaintext(plaintext)
        key = _text(idempotency_key, "idempotency_key")
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
            CREDENTIAL_STATE_MACHINE.apply(old, "rotate", tenant_id=tenant_id, transition_key=key, metadata=_transition_metadata(actor_id, "Credential rotated"))
            new = IntegrationCredential(
                tenant_id=tenant_id,
                integration=old.integration,
                credential_type=old.credential_type,
                encrypted_value=_encrypt_secret(raw, "credential_encryption"),
                display_hint=self._hint(raw),
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
            credential = CREDENTIAL_STATE_MACHINE.apply(credential, "revoke", tenant_id=tenant_id, transition_key=_text(transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Credential revoked"))
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
            CREDENTIAL_STATE_MACHINE.apply(credential, "expire", tenant_id=tenant_id, transition_key=f"expire:{credential.id}:{credential.expires_at.isoformat()}", metadata=_transition_metadata(None, "Credential expired"))
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
        if connector.required_entitlement:
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
        config = _safe_mapping(data.get("config", {}), "config")
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
                name=_text(data.get("name"), "name"),
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
                integration.name = _text(data["name"], "name")
            if "description" in data:
                integration.description = str(data["description"] or "")
            if "config" in data:
                config = _safe_mapping(data["config"], "config")
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
            integration = INTEGRATION_STATE_MACHINE.apply(integration, "deactivate", tenant_id=tenant_id, transition_key=_text(transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Integration deactivated"))
            _publish(tenant_id, "integration", integration.id, "integration.updated", {"actor_id": str(actor_id), "action": "deactivate", "adapter_key": integration.connector.adapter_key})
            return integration

    def request_test(self, tenant_id: UUID, actor_id: UUID, integration_id: UUID, idempotency_key: str) -> AsyncJob:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        integration = _active(Integration, tenant_id, integration_id)
        self._adapter(integration.connector, ConnectorCapability.TEST)
        key = _text(idempotency_key, "idempotency_key")
        with transaction.atomic():
            integration = INTEGRATION_STATE_MACHINE.apply(integration, "request_test", tenant_id=tenant_id, transition_key=key, metadata=_transition_metadata(actor_id, "Connection test requested"))
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
            logger.warning("integration.test.failed", extra={"tenant_id": str(tenant_id), "aggregate_id": str(integration.id), "job_id": str(job.id), "error_code": type(exc).__name__})
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        with transaction.atomic():
            integration.last_tested_at = timezone.now()
            integration.last_error_code = result.error_code or ""
            integration.last_error_message = result.message or ""
            integration.save(update_fields=("last_tested_at", "last_error_code", "last_error_message", "updated_at"))
            command = "test_succeeded" if result.status == "succeeded" else "test_failed"
            integration = INTEGRATION_STATE_MACHINE.apply(integration, command, tenant_id=tenant_id, transition_key=f"job:{job.id}:{command}", metadata=_transition_metadata(None, "Connection test completed", job_id=str(job.id), duration_ms=duration_ms, outcome=result.status))
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
        if direction not in {"pull", "push"}:
            raise IntegrationPlatformError("validation_error", "direction must be pull or push.", status_code=400)
        self._adapter(integration.connector, direction)
        ids = [_uuid(value, "mapping_id") for value in mapping_ids]
        if len(ids) != len(set(ids)):
            raise IntegrationPlatformError("validation_error", "mapping_ids must be unique.", status_code=400)
        found = set(DataMapping.objects.for_tenant(tenant_id).filter(integration=integration, is_deleted=False, id__in=ids).values_list("id", flat=True))
        if found != set(ids):
            raise NotFound()
        try:
            quota = self.quotas.consume(tenant_id, "integration_platform.integration:sync", cost=1)
        except Exception as exc:
            raise CapabilityUnavailable(capability="sync_quota") from exc
        if not quota.allowed:
            raise IntegrationPlatformError("quota_exceeded", "The synchronization quota is exhausted.", status_code=429)
        key = _text(idempotency_key, "idempotency_key")
        try:
            job = enqueue(tenant_id, actor_id, self.SYNC_COMMAND, {"integration_id": str(integration.id), "direction": direction, "mapping_ids": [str(value) for value in ids]}, f"{self.SYNC_COMMAND}:{key}")
        except Exception as exc:
            raise CapabilityUnavailable(capability="durable_job_dispatch") from exc
        integration.last_sync_job_id = job.id
        integration.save(update_fields=("last_sync_job_id", "updated_at"))
        _publish(tenant_id, "integration", integration.id, "integration.sync.requested", {"actor_id": str(actor_id), "job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "direction": direction})
        return job

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
            failure = OperationResult.failed(code="sync_source_unavailable", message="No governed source contract supplied records for this push job.", evidence={"job_id": str(job.id)}, provider=integration.connector.adapter_key, http_status=422)
            _publish(tenant_id, "integration", integration.id, "integration.sync.failed", {"job_id": str(job.id), "adapter_key": integration.connector.adapter_key, "error_code": failure.error_code or ""})
            return failure
        result = adapter.pull(integration.config, credential, RecordCursor(), 1000)
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
    def _new_secret() -> str:
        return secrets.token_urlsafe(48)

    def create(self, tenant_id: UUID, actor_id: UUID, data: Mapping[str, object]) -> SecretOnce:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        secret = self._new_secret()
        with transaction.atomic():
            webhook = Webhook(
                tenant_id=tenant_id,
                created_by=actor_id,
                name=_text(data.get("name"), "name"),
                direction=str(data.get("direction") or ""),
                url=str(data.get("url") or ""),
                events=list(data.get("events") or []),
                encrypted_signing_secret=_encrypt_secret(secret, "webhook_secret_encryption"),
                config=_safe_mapping(data.get("config", {}), "config"),
                timeout_seconds=int(data.get("timeout_seconds", 10)),
                max_attempts=int(data.get("max_attempts", 5)),
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
                webhook.config = _safe_mapping(data["config"], "config")
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
            webhook = WEBHOOK_STATE_MACHINE.apply(webhook, command, tenant_id=tenant_id, transition_key=_text(transition_key, "transition_key"), metadata=_transition_metadata(actor_id, f"Webhook {command}d"))
            _publish(tenant_id, "webhook", webhook.id, "webhook.updated", {"actor_id": str(actor_id), "action": command, "direction": webhook.direction})
            return webhook

    def rotate_secret(self, tenant_id: UUID, actor_id: UUID, webhook_id: UUID, transition_key: str) -> SecretOnce:
        tenant_id, actor_id = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        key = _text(transition_key, "transition_key")
        secret = self._new_secret()
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
        if not isinstance(raw_body, bytes) or len(raw_body) > MAX_BODY_BYTES:
            raise IntegrationPlatformError("invalid_payload", "Webhook body is invalid or too large.", status_code=400)
        try:
            issued_at = datetime.fromtimestamp(int(timestamp), tz=datetime_timezone.utc)
        except (TypeError, ValueError, OSError) as exc:
            raise IntegrationPlatformError("invalid_timestamp", "Webhook timestamp is invalid.", status_code=401) from exc
        if abs((timezone.now() - issued_at).total_seconds()) > INBOUND_WINDOW_SECONDS:
            raise IntegrationPlatformError("stale_signature", "Webhook signature timestamp is outside the allowed window.", status_code=401)
        nonce = _text(nonce, "nonce", 128)
        signature = _text(signature, "signature", 128)
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
            accepted = cache.add(nonce_key, "used", timeout=INBOUND_WINDOW_SECONDS)
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
        payload = _redact(parsed)
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
        event = _text(event, "event")
        if event not in webhook.events:
            raise IntegrationPlatformError("event_not_subscribed", "The webhook does not subscribe to this event.", status_code=400)
        safe_payload = _redact(dict(payload))
        canonical = json.dumps(safe_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        key = _text(idempotency_key, "idempotency_key")
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
            delivery = DELIVERY_STATE_MACHINE.apply(delivery, "redrive", tenant_id=tenant_id, transition_key=_text(transition_key, "transition_key"), metadata=_transition_metadata(actor_id, "Delivery redriven"))
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
        return ResilientHttpClient(connect_timeout=min(5, webhook.timeout_seconds), read_timeout=webhook.timeout_seconds, max_retries=0)

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
            delivery = DELIVERY_STATE_MACHINE.apply(delivery, "requeue", tenant_id=tenant_id, transition_key=f"job:{job.id}:requeue", metadata=_transition_metadata(None, "Retry became due"))
        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "start", tenant_id=tenant_id, transition_key=f"job:{job.id}:start", metadata=_transition_metadata(None, "Delivery attempt started"))
        delivery.attempt_count += 1
        delivery.save(update_fields=("attempt_count", "updated_at"))
        canonical = json.dumps(delivery.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        timestamp = str(int(timezone.now().timestamp()))
        nonce = secrets.token_urlsafe(24)
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
            code, excerpt = response.status_code, _safe_excerpt(response.text)
        except Exception as exc:
            if delivery.attempt_count < delivery.max_attempts:
                return self.schedule_retry(tenant_id, delivery.id, exc)
            return self.move_to_dead_letter(tenant_id, delivery.id, exc)
        duration = max(0, round((time.monotonic() - started) * 1000))
        delivery.response_code, delivery.response_body_excerpt, delivery.duration_ms = code, excerpt, duration
        delivery.save(update_fields=("response_code", "response_body_excerpt", "duration_ms", "updated_at"))
        if 200 <= code < 300:
            delivery.delivered_at = timezone.now()
            delivery.save(update_fields=("delivered_at", "updated_at"))
            delivery = DELIVERY_STATE_MACHINE.apply(delivery, "succeed", tenant_id=tenant_id, transition_key=f"job:{job.id}:succeed", metadata=_transition_metadata(None, "Provider acknowledged delivery", response_code=code, duration_ms=duration))
            webhook.last_delivered_at = delivery.delivered_at
            webhook.save(update_fields=("last_delivered_at", "updated_at"))
            evidence = {"delivery_id": str(delivery.id), "attempt_count": delivery.attempt_count, "response_code": code, "duration_ms": duration}
            _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.succeeded", {"job_id": str(job.id), "webhook_id": str(webhook.id), **evidence})
            return OperationResult.succeeded(evidence, evidence=evidence, provider=webhook.url.split("/", 3)[2])
        error = RuntimeError(f"HTTP {code}")
        if code in {408, 429} or code >= 500:
            return self.schedule_retry(tenant_id, delivery.id, error) if delivery.attempt_count < delivery.max_attempts else self.move_to_dead_letter(tenant_id, delivery.id, error)
        return self.move_to_dead_letter(tenant_id, delivery.id, error)

    def schedule_retry(self, tenant_id: UUID, delivery_id: UUID, error: Exception) -> OperationResult[dict[str, object]]:
        tenant_id = _uuid(tenant_id, "tenant_id")
        delivery = WebhookDelivery.objects.for_tenant(tenant_id).filter(pk=delivery_id).first()
        if delivery is None:
            raise NotFound()
        if delivery.attempt_count >= delivery.max_attempts:
            return self.move_to_dead_letter(tenant_id, delivery.id, error)
        base = min(3600, 2 ** max(0, delivery.attempt_count - 1))
        jitter = int.from_bytes(hashlib.sha256(f"{delivery.id}:{delivery.attempt_count}".encode()).digest()[:2], "big") % max(1, base)
        delay = min(3600, base + jitter)
        with transaction.atomic():
            delivery.error_code, delivery.error_message = _error_code(error), "The delivery dependency failed transiently."
            delivery.next_attempt_at = timezone.now() + timedelta(seconds=delay)
            delivery.save(update_fields=("error_code", "error_message", "next_attempt_at", "updated_at"))
            delivery = DELIVERY_STATE_MACHINE.apply(delivery, "retry", tenant_id=tenant_id, transition_key=f"attempt:{delivery.attempt_count}:retry", metadata=_transition_metadata(None, "Transient delivery failure", delay_seconds=delay, error_code=delivery.error_code))
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
        delivery.error_code, delivery.error_message = _error_code(error), "The delivery could not be completed."
        delivery.next_attempt_at = None
        delivery.save(update_fields=("error_code", "error_message", "next_attempt_at", "updated_at"))
        delivery = DELIVERY_STATE_MACHINE.apply(delivery, "exhaust", tenant_id=tenant_id, transition_key=f"attempt:{delivery.attempt_count}:exhaust", metadata=_transition_metadata(None, "Delivery moved to dead letter", error_code=delivery.error_code))
        if delivery.webhook.status == WebhookStatus.ACTIVE:
            WEBHOOK_STATE_MACHINE.apply(delivery.webhook, "delivery_failed", tenant_id=tenant_id, transition_key=f"delivery:{delivery.id}:failed", metadata=_transition_metadata(None, "Delivery exhausted retry policy"))
        _publish(tenant_id, "webhook_delivery", delivery.id, "webhook.delivery.dead_lettered", {"job_id": str(delivery.job_id), "webhook_id": str(delivery.webhook_id), "attempt_count": delivery.attempt_count, "error_code": delivery.error_code})
        return OperationResult.failed(code="delivery_dead_lettered", message="Delivery moved to the dead-letter queue.", evidence={"delivery_id": str(delivery.id), "attempt_count": delivery.attempt_count}, provider="webhook", http_status=422)

    def recover_stale(self, tenant_id: UUID, stale_before: datetime) -> list[AsyncJob]:
        return recover_stale_jobs(_uuid(tenant_id, "tenant_id"), stale_before=stale_before)


def _error_code(error: Exception) -> str:
    name = type(error).__name__.lower()
    return name[:100] if name else "dependency_failure"


def _safe_excerpt(value: object) -> str:
    text = str(value)[:2048]
    for marker in ("authorization", "password", "secret", "token", "api_key"):
        if marker in text.lower():
            return "[REDACTED]"
    return text


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
                name=_text(data.get("name"), "name"),
                source_field=_text(data.get("source_field"), "source_field"),
                target_field=_text(data.get("target_field"), "target_field"),
                transform=dict(data.get("transform") or {}),
                position=int(data.get("position", 0)),
                is_required=bool(data.get("is_required", False)),
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
        if not records or len(records) > 100 or any(not isinstance(record, Mapping) for record in records):
            raise IntegrationPlatformError(
                "validation_error",
                "sample must contain between 1 and 100 JSON objects.",
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
credential_service = CredentialService()
integration_service = IntegrationService(credentials=credential_service)
webhook_service = WebhookService()
delivery_worker = WebhookDeliveryWorker()
mapping_service = DataMappingService()


__all__ = [
    "ConnectorService", "CredentialService", "DataMappingService", "IntegrationPlatformError",
    "IntegrationService", "MappingFailure", "SecretOnce", "TransformResult", "WebhookDeliveryWorker",
    "WebhookService", "connector_service", "credential_service", "delivery_worker", "integration_service",
    "mapping_service", "webhook_service", "EncryptionService",
]

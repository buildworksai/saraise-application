"""Transactional business services for tenant-safe product traceability."""

from __future__ import annotations

import hmac
import logging
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from src.core.api import OperationFailed, OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent, OutboxStatus
from src.core.async_jobs.services import enqueue
from src.core.observability import get_correlation_id
from src.core.state_machine import StateMachine, StateMachineError, Transition

from .hashing import canonical_json, compute_event_hash, compute_merkle_root, normalize_utc_timestamp, sha256_hex
from . import metrics
from .models import (
    AuthenticityCredential,
    AuthenticityCredentialStatus,
    ComplianceEvidence,
    ComplianceEvidenceStatus,
    LedgerAnchor,
    LedgerAnchorStatus,
    LedgerNetwork,
    LedgerNetworkStatus,
    TraceabilityAsset,
    TraceabilityAssetStatus,
    TraceabilityEvent,
    VerificationAttempt,
    VerificationOutcome,
    VerificationType,
)
from .providers import (
    AdapterNotRegisteredError,
    AnchorReceipt,
    CredentialIssuerAdapter,
    DocumentReferenceResolver,
    InvalidProviderResponseError,
    InventoryReferenceResolver,
    LedgerProviderAdapter,
    ProofResult,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderHealth,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SubmissionReceipt,
    credential_issuer_registry,
    get_credential_issuer,
    get_document_resolver,
    get_inventory_resolver,
    get_ledger_provider,
)

logger = logging.getLogger("saraise.blockchain_traceability")

SUBMIT_ANCHOR_COMMAND = "blockchain_traceability.submit_anchor"


class BlockchainTraceabilityError(OperationFailed):
    """Stable domain error consumed by the governed API error renderer."""

    def __init__(self, code: str, message: str, *, status_code: int = 422, detail: object | None = None) -> None:
        super().__init__(error_code=code, message=message, detail=detail, http_status=status_code)


class DomainConflictError(BlockchainTraceabilityError):
    def __init__(self, code: str, message: str, *, detail: object | None = None) -> None:
        super().__init__(code, message, status_code=409, detail=detail)


class IdempotencyConflictError(DomainConflictError):
    def __init__(self, message: str = "The idempotency key was already used for different input.") -> None:
        super().__init__("idempotency_conflict", message)


class DomainNotFoundError(BlockchainTraceabilityError):
    def __init__(self, resource: str) -> None:
        super().__init__("resource_not_found", f"The requested {resource} was not found.", status_code=404)


class DependencyUnavailableError(BlockchainTraceabilityError):
    def __init__(self, capability: str, message: str | None = None) -> None:
        super().__init__(
            "dependency_unavailable",
            message or "The configured dependency is currently unavailable.",
            status_code=503,
            detail={"capability": capability},
        )


@dataclass(frozen=True, slots=True)
class IssuedCredential:
    credential: AuthenticityCredential
    token: str


@dataclass(frozen=True, slots=True)
class AssetHistoryItem:
    kind: str
    occurred_at: str
    identifier: UUID
    sequence: int | None = None
    event: Mapping[str, Any] | None = None
    anchor: Mapping[str, Any] | None = None
    credential: Mapping[str, Any] | None = None
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AssetHistory:
    asset: Mapping[str, Any]
    items: tuple[AssetHistoryItem, ...]
    proof_status: str
    failing_sequence: int | None
    pagination: Mapping[str, Any]


NETWORK_MACHINE = StateMachine(
    name="blockchain_traceability.network",
    model=LedgerNetwork,
    states=LedgerNetworkStatus.values,
    transitions=(
        Transition("activate", LedgerNetworkStatus.DRAFT, LedgerNetworkStatus.ACTIVE),
        Transition("activate", LedgerNetworkStatus.DISABLED, LedgerNetworkStatus.ACTIVE),
        Transition("mark_degraded", LedgerNetworkStatus.ACTIVE, LedgerNetworkStatus.DEGRADED),
        Transition("restore", LedgerNetworkStatus.DEGRADED, LedgerNetworkStatus.ACTIVE),
        Transition("disable", LedgerNetworkStatus.DRAFT, LedgerNetworkStatus.DISABLED),
        Transition("disable", LedgerNetworkStatus.ACTIVE, LedgerNetworkStatus.DISABLED),
        Transition("disable", LedgerNetworkStatus.DEGRADED, LedgerNetworkStatus.DISABLED),
    ),
)

ASSET_MACHINE = StateMachine(
    name="blockchain_traceability.asset",
    model=TraceabilityAsset,
    states=TraceabilityAssetStatus.values,
    terminal_states=(TraceabilityAssetStatus.RETIRED,),
    transitions=(
        Transition("activate", TraceabilityAssetStatus.DRAFT, TraceabilityAssetStatus.ACTIVE),
        Transition("recall", TraceabilityAssetStatus.ACTIVE, TraceabilityAssetStatus.RECALLED),
        Transition("release_recall", TraceabilityAssetStatus.RECALLED, TraceabilityAssetStatus.ACTIVE),
        Transition("retire", TraceabilityAssetStatus.DRAFT, TraceabilityAssetStatus.RETIRED),
        Transition("retire", TraceabilityAssetStatus.ACTIVE, TraceabilityAssetStatus.RETIRED),
        Transition("retire", TraceabilityAssetStatus.RECALLED, TraceabilityAssetStatus.RETIRED),
    ),
)

ANCHOR_MACHINE = StateMachine(
    name="blockchain_traceability.anchor",
    model=LedgerAnchor,
    states=LedgerAnchorStatus.values,
    terminal_states=(LedgerAnchorStatus.CONFIRMED,),
    transitions=(
        Transition("start_submission", LedgerAnchorStatus.QUEUED, LedgerAnchorStatus.SUBMITTING),
        Transition("accept_submission", LedgerAnchorStatus.SUBMITTING, LedgerAnchorStatus.SUBMITTED),
        Transition("confirm", LedgerAnchorStatus.SUBMITTED, LedgerAnchorStatus.CONFIRMED),
        Transition("fail", LedgerAnchorStatus.SUBMITTING, LedgerAnchorStatus.FAILED),
        Transition("fail", LedgerAnchorStatus.SUBMITTED, LedgerAnchorStatus.FAILED),
        Transition("retry", LedgerAnchorStatus.FAILED, LedgerAnchorStatus.QUEUED),
    ),
)

CREDENTIAL_MACHINE = StateMachine(
    name="blockchain_traceability.credential",
    model=AuthenticityCredential,
    states=AuthenticityCredentialStatus.values,
    terminal_states=(AuthenticityCredentialStatus.REVOKED, AuthenticityCredentialStatus.EXPIRED),
    transitions=(
        Transition("revoke", AuthenticityCredentialStatus.ACTIVE, AuthenticityCredentialStatus.REVOKED),
        Transition("expire", AuthenticityCredentialStatus.ACTIVE, AuthenticityCredentialStatus.EXPIRED),
    ),
)

EVIDENCE_MACHINE = StateMachine(
    name="blockchain_traceability.compliance_evidence",
    model=ComplianceEvidence,
    states=ComplianceEvidenceStatus.values,
    terminal_states=(ComplianceEvidenceStatus.SUPERSEDED,),
    transitions=(
        Transition("finalize", ComplianceEvidenceStatus.DRAFT, ComplianceEvidenceStatus.FINALIZED),
        Transition("supersede", ComplianceEvidenceStatus.FINALIZED, ComplianceEvidenceStatus.SUPERSEDED),
    ),
)


def _uuid(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BlockchainTraceabilityError("validation_error", f"{field_name} must be a valid UUID.", status_code=400) from exc


def _actor(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlockchainTraceabilityError("validation_error", "actor_id is required.", status_code=400)
    normalized = value.strip()
    if len(normalized) > 255:
        raise BlockchainTraceabilityError("validation_error", "actor_id exceeds 255 characters.", status_code=400)
    return normalized


def _correlation() -> str:
    return get_correlation_id() or str(uuid.uuid4())


def _data(value: Mapping[str, Any] | dict[str, Any], *, allowed: set[str], required: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BlockchainTraceabilityError("validation_error", "data must be an object.", status_code=400)
    unknown = set(value) - allowed
    if unknown:
        raise BlockchainTraceabilityError(
            "validation_error", f"Unknown fields: {', '.join(sorted(unknown))}.", status_code=400
        )
    missing = {name for name in required if name not in value}
    if missing:
        raise BlockchainTraceabilityError(
            "validation_error", f"Missing fields: {', '.join(sorted(missing))}.", status_code=400
        )
    return dict(value)


def _model_error(exc: ValidationError) -> BlockchainTraceabilityError:
    detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None)
    return BlockchainTraceabilityError("validation_error", "The traceability data is invalid.", status_code=400, detail=detail)


def _transition(machine: StateMachine[Any], aggregate: Any, command: str, transition_key: str, actor_id: str, **metadata: Any) -> Any:
    try:
        return machine.apply(
            aggregate,
            command,
            transition_key=transition_key,
            metadata={"actor_id": actor_id, "correlation_id": _correlation(), **metadata},
        )
    except StateMachineError as exc:
        raise DomainConflictError("illegal_state", "The requested state transition is not allowed.") from exc


def _provider_failure(exc: Exception, capability: str) -> DependencyUnavailableError:
    if isinstance(exc, ProviderTimeoutError):
        return DependencyUnavailableError(capability, "The provider call timed out.")
    if isinstance(exc, ProviderCircuitOpenError):
        return DependencyUnavailableError(capability, "The provider circuit is open.")
    return DependencyUnavailableError(capability)


def _safe_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    forbidden = {"authorization", "credential", "credentials", "password", "private_key", "secret", "token"}

    def redact(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): redact(nested)
                for key, nested in value.items()
                if not any(part in str(key).lower() for part in forbidden)
            }
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    result = redact(receipt)
    if not isinstance(result, dict):
        raise InvalidProviderResponseError("provider receipt must be an object")
    return result


def _emit_domain_event(
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    payload: Mapping[str, Any],
) -> OutboxEvent:
    """Persist a secret-free domain event inside the caller's transaction."""

    event = OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={**dict(payload), "correlation_id": _correlation()},
    )
    oldest = (
        OutboxEvent.objects.filter(tenant_id=tenant_id, status=OutboxStatus.PENDING)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    metrics.OUTBOX_AGE.set(max(0.0, (timezone.now() - (oldest or event.created_at)).total_seconds()))
    return event


def _matches(instance: Any, values: Mapping[str, Any]) -> bool:
    for key, value in values.items():
        current = getattr(instance, key)
        if isinstance(current, UUID):
            value = _uuid(value, key)
        if current != value:
            return False
    return True


class LedgerNetworkService:
    CREATE_FIELDS = {
        "network_key",
        "name",
        "description",
        "provider_type",
        "dependency_key",
        "network_namespace",
        "chain_id",
        "secret_ref",
        "confirmation_depth",
        "supports_batch_anchors",
        "supports_finality",
        "provider_options",
    }
    UPDATE_FIELDS = CREATE_FIELDS - {"network_key"}

    def create_network(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> LedgerNetwork:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"network_key", "name", "provider_type", "dependency_key", "network_namespace"},
        )
        try:
            adapter = get_ledger_provider(str(values["provider_type"]))
            options = values.get("provider_options", {})
            if not isinstance(options, Mapping):
                raise BlockchainTraceabilityError("validation_error", "provider_options must be an object.", status_code=400)
            adapter.validate_options(options)
            network = LedgerNetwork(tenant_id=tenant, created_by=actor, **values)
            network.save()
            return network
        except AdapterNotRegisteredError as exc:
            raise DependencyUnavailableError("ledger_provider") from exc
        except BlockchainTraceabilityError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise _model_error(exc) if isinstance(exc, ValidationError) else BlockchainTraceabilityError(
                "invalid_provider_options", "Provider options are invalid.", status_code=400
            ) from exc

    def get_network(self, tenant_id: UUID, network_id: UUID | str) -> LedgerNetwork:
        try:
            return LedgerNetwork.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(network_id, "network_id"), is_deleted=False)
        except LedgerNetwork.DoesNotExist as exc:
            raise DomainNotFoundError("ledger network") from exc

    def list_networks(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[LedgerNetwork]:
        queryset = LedgerNetwork.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False)
        for key in ("status", "provider_type"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        return queryset.order_by("name", "id")

    def update_network(self, tenant_id: UUID, network_id: UUID | str, actor_id: str, data: Mapping[str, Any]) -> LedgerNetwork:
        actor = _actor(actor_id)
        values = _data(data, allowed=self.UPDATE_FIELDS)
        with transaction.atomic():
            network = LedgerNetwork.objects.select_for_update().get(pk=self.get_network(tenant_id, network_id).pk)
            operational = self.UPDATE_FIELDS - {"name", "description"}
            if network.status in {LedgerNetworkStatus.ACTIVE, LedgerNetworkStatus.DEGRADED} and operational & set(values):
                raise DomainConflictError("network_active", "Disable the network before changing provider configuration.")
            if "provider_type" in values or "provider_options" in values:
                try:
                    provider_type = str(values.get("provider_type", network.provider_type))
                    adapter = get_ledger_provider(provider_type)
                    options = values.get("provider_options", network.provider_options)
                    if not isinstance(options, Mapping):
                        raise ValueError
                    adapter.validate_options(options)
                except AdapterNotRegisteredError as exc:
                    raise DependencyUnavailableError("ledger_provider") from exc
                except (ValueError, TypeError) as exc:
                    raise BlockchainTraceabilityError(
                        "invalid_provider_options", "Provider options are invalid.", status_code=400
                    ) from exc
            for field, value in values.items():
                setattr(network, field, value)
            network.updated_by = actor
            try:
                network.save()
            except ValidationError as exc:
                raise _model_error(exc) from exc
            return network

    def delete_network(self, tenant_id: UUID, network_id: UUID | str, actor_id: str) -> None:
        actor = _actor(actor_id)
        with transaction.atomic():
            network = LedgerNetwork.objects.select_for_update().get(pk=self.get_network(tenant_id, network_id).pk)
            if network.status not in {LedgerNetworkStatus.DRAFT, LedgerNetworkStatus.DISABLED} or network.anchors.exists():
                raise DomainConflictError("network_in_use", "Only unused draft or disabled networks can be deleted.")
            network.is_deleted = True
            network.deleted_at = timezone.now()
            network.deleted_by = actor
            network.updated_by = actor
            network.save()

    def probe_network(
        self, tenant_id: UUID, network_id: UUID | str, actor_id: str
    ) -> OperationResult[ProviderHealth]:
        _actor(actor_id)
        network = self.get_network(tenant_id, network_id)
        now = timezone.now()
        try:
            adapter = get_ledger_provider(network.provider_type)
            health = adapter.health(network)
            if not isinstance(health, ProviderHealth):
                raise InvalidProviderResponseError("provider returned invalid health evidence")
        except (AdapterNotRegisteredError, ProviderUnavailableError) as exc:
            metrics.PROVIDER_UNAVAILABLE.labels(capability="network_probe").inc()
            network.last_health_status = "unavailable"
            network.last_health_code = "PROVIDER_UNAVAILABLE"
            network.last_health_checked_at = now
            network.save(update_fields=["last_health_status", "last_health_code", "last_health_checked_at", "updated_at"])
            return OperationResult.unavailable(
                capability="ledger_provider", provider=network.provider_type, evidence={"network_id": str(network.id)}
            )
        except ProviderError:
            network.last_health_status = "failed"
            network.last_health_code = "INVALID_PROVIDER_RESPONSE"
            network.last_health_checked_at = now
            network.save(update_fields=["last_health_status", "last_health_code", "last_health_checked_at", "updated_at"])
            return OperationResult.failed(
                code="INVALID_PROVIDER_RESPONSE",
                message="The provider returned invalid health evidence.",
                provider=network.provider_type,
                http_status=502,
            )
        network.last_health_status = "available" if health.available else "unavailable"
        network.last_health_code = health.code[:64]
        network.last_health_checked_at = now
        network.save(update_fields=["last_health_status", "last_health_code", "last_health_checked_at", "updated_at"])
        if not health.available:
            return OperationResult.unavailable(
                capability="ledger_provider",
                message="The configured ledger provider is unavailable.",
                provider=network.provider_type,
                evidence={"health_code": health.code},
            )
        return OperationResult.succeeded(
            health,
            provider=network.provider_type,
            evidence={"health_code": health.code, "checked_at": now.isoformat()},
        )

    def activate_network(
        self, tenant_id: UUID, network_id: UUID | str, actor_id: str, transition_key: str
    ) -> LedgerNetwork:
        actor = _actor(actor_id)
        network = self.get_network(tenant_id, network_id)
        result = self.probe_network(tenant_id, network_id, actor)
        if result.status != "succeeded" or result.value is None or not result.value.available:
            raise result.to_exception()
        return _transition(NETWORK_MACHINE, network, "activate", transition_key, actor)

    def disable_network(
        self, tenant_id: UUID, network_id: UUID | str, actor_id: str, transition_key: str
    ) -> LedgerNetwork:
        return _transition(NETWORK_MACHINE, self.get_network(tenant_id, network_id), "disable", transition_key, _actor(actor_id))


class TraceabilityAssetService:
    CREATE_FIELDS = {
        "asset_key",
        "name",
        "description",
        "product_ref",
        "batch_ref",
        "serial_number",
        "gtin",
        "asset_type",
        "attributes",
    }
    UPDATE_FIELDS = CREATE_FIELDS - {"asset_key"}

    def __init__(self, *, inventory_resolver: InventoryReferenceResolver | None = None) -> None:
        self.inventory_resolver = inventory_resolver

    def _validate_inventory(self, tenant_id: UUID, product_ref: str, batch_ref: str) -> None:
        resolver = self.inventory_resolver
        if resolver is None:
            try:
                resolver = get_inventory_resolver()
            except AdapterNotRegisteredError:
                return  # Optional integration: opaque references remain explicitly unverified.
        try:
            result = resolver.validate_reference(tenant_id, product_ref, batch_ref)
        except ProviderUnavailableError as exc:
            raise DependencyUnavailableError("inventory_reference") from exc
        if not result.valid:
            raise BlockchainTraceabilityError(
                "invalid_inventory_reference", "The inventory reference is not valid for this tenant.", status_code=400
            )

    def register_asset(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> TraceabilityAsset:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        values = _data(data, allowed=self.CREATE_FIELDS, required={"asset_key", "name", "asset_type"})
        self._validate_inventory(tenant, str(values.get("product_ref", "")), str(values.get("batch_ref", "")))
        try:
            with transaction.atomic():
                asset = TraceabilityAsset(tenant_id=tenant, created_by=actor, **values)
                asset.save()
                _emit_domain_event(
                    tenant,
                    "traceability_asset",
                    asset.id,
                    "blockchain_traceability.asset.registered",
                    {"asset_id": str(asset.id), "asset_key": asset.asset_key, "actor_id": actor},
                )
            logger.info(
                "Traceability asset registered",
                extra={"tenant_id": str(tenant), "actor_id": actor, "asset_id": str(asset.id), "correlation_id": _correlation()},
            )
            return asset
        except ValidationError as exc:
            raise _model_error(exc) from exc

    def get_asset(self, tenant_id: UUID, asset_id: UUID | str) -> TraceabilityAsset:
        try:
            return TraceabilityAsset.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(asset_id, "asset_id"), is_deleted=False)
        except TraceabilityAsset.DoesNotExist as exc:
            raise DomainNotFoundError("traceability asset") from exc

    def list_assets(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[TraceabilityAsset]:
        queryset = TraceabilityAsset.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False)
        for key in ("status", "product_ref", "batch_ref", "serial_number", "gtin", "asset_type"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        return queryset.order_by("-created_at", "id")

    def update_asset(self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, data: Mapping[str, Any]) -> TraceabilityAsset:
        actor = _actor(actor_id)
        values = _data(data, allowed=self.UPDATE_FIELDS)
        with transaction.atomic():
            asset = TraceabilityAsset.objects.select_for_update().get(pk=self.get_asset(tenant_id, asset_id).pk)
            if asset.status == TraceabilityAssetStatus.RETIRED:
                raise DomainConflictError("asset_retired", "Retired assets are immutable.")
            product_ref = str(values.get("product_ref", asset.product_ref))
            batch_ref = str(values.get("batch_ref", asset.batch_ref))
            if {"product_ref", "batch_ref"} & set(values):
                self._validate_inventory(asset.tenant_id, product_ref, batch_ref)
            for field, value in values.items():
                setattr(asset, field, value)
            asset.updated_by = actor
            try:
                asset.save()
            except ValidationError as exc:
                raise _model_error(exc) from exc
            return asset

    def delete_asset(self, tenant_id: UUID, asset_id: UUID | str, actor_id: str) -> None:
        actor = _actor(actor_id)
        with transaction.atomic():
            asset = TraceabilityAsset.objects.select_for_update().get(pk=self.get_asset(tenant_id, asset_id).pk)
            has_evidence = (
                asset.events.exists()
                or asset.anchors.exists()
                or asset.credentials.exists()
                or asset.compliance_evidence.filter(status=ComplianceEvidenceStatus.FINALIZED).exists()
            )
            if asset.status != TraceabilityAssetStatus.DRAFT or has_evidence:
                raise DomainConflictError("asset_has_evidence", "Only an unused draft asset can be deleted.")
            asset.is_deleted = True
            asset.deleted_at = timezone.now()
            asset.deleted_by = actor
            asset.updated_by = actor
            asset.save()

    def _asset_transition(
        self,
        tenant_id: UUID,
        asset_id: UUID | str,
        actor_id: str,
        command: str,
        transition_key: str,
        **metadata: Any,
    ) -> TraceabilityAsset:
        actor = _actor(actor_id)
        with transaction.atomic():
            asset = self.get_asset(tenant_id, asset_id)
            now = timezone.now()
            timestamp_field = {"activate": "activated_at", "recall": "recalled_at", "retire": "retired_at"}.get(command)
            if timestamp_field:
                setattr(asset, timestamp_field, now)
                asset.updated_by = actor
                asset.save(update_fields=[timestamp_field, "updated_by", "updated_at"])
            if command == "release_recall":
                asset.recalled_at = None
                asset.updated_by = actor
                asset.save(update_fields=["recalled_at", "updated_by", "updated_at"])
            asset = _transition(ASSET_MACHINE, asset, command, transition_key, actor, **metadata)
            _emit_domain_event(
                asset.tenant_id,
                "traceability_asset",
                asset.id,
                "blockchain_traceability.asset.transitioned",
                {"asset_id": str(asset.id), "command": command, "status": asset.status, "actor_id": actor},
            )
            return asset

    def activate_asset(self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, transition_key: str) -> TraceabilityAsset:
        return self._asset_transition(tenant_id, asset_id, actor_id, "activate", transition_key)

    def recall_asset(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, reason: str, transition_key: str
    ) -> TraceabilityAsset:
        if not isinstance(reason, str) or not reason.strip():
            raise BlockchainTraceabilityError("validation_error", "A recall reason is required.", status_code=400)
        return self._asset_transition(tenant_id, asset_id, actor_id, "recall", transition_key, reason=reason.strip())

    def release_recall(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, transition_key: str
    ) -> TraceabilityAsset:
        return self._asset_transition(tenant_id, asset_id, actor_id, "release_recall", transition_key)

    def retire_asset(self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, transition_key: str) -> TraceabilityAsset:
        return self._asset_transition(tenant_id, asset_id, actor_id, "retire", transition_key)

    def product_history(self, tenant_id: UUID, asset_id: UUID | str, page: int, page_size: int) -> AssetHistory:
        asset = self.get_asset(tenant_id, asset_id)
        if page < 1 or page_size < 1 or page_size > 100:
            raise BlockchainTraceabilityError("validation_error", "Invalid history pagination.", status_code=400)
        items: list[AssetHistoryItem] = []
        for event in asset.events.all().iterator(chunk_size=100):
            items.append(
                AssetHistoryItem(
                    kind="event",
                    occurred_at=normalize_utc_timestamp(event.occurred_at),
                    identifier=event.id,
                    sequence=event.sequence,
                    event={
                        "id": str(event.id),
                        "event_type": event.event_type,
                        "previous_hash": event.previous_hash,
                        "event_hash": event.event_hash,
                        "actor_ref": event.actor_ref,
                        "location": event.location,
                    },
                )
            )
        for anchor in asset.anchors.all().iterator(chunk_size=100):
            items.append(
                AssetHistoryItem(
                    kind="anchor",
                    occurred_at=normalize_utc_timestamp(anchor.created_at),
                    identifier=anchor.id,
                    anchor={
                        "id": str(anchor.id),
                        "status": anchor.status,
                        "start_sequence": anchor.start_sequence,
                        "end_sequence": anchor.end_sequence,
                        "root_hash": anchor.root_hash,
                    },
                )
            )
        for credential in asset.credentials.all().iterator(chunk_size=100):
            items.append(
                AssetHistoryItem(
                    kind="credential",
                    occurred_at=normalize_utc_timestamp(credential.issued_at),
                    identifier=credential.id,
                    credential={"id": str(credential.id), "public_id": credential.public_id, "status": credential.status},
                )
            )
        for evidence in asset.compliance_evidence.filter(is_deleted=False).iterator(chunk_size=100):
            items.append(
                AssetHistoryItem(
                    kind="compliance",
                    occurred_at=normalize_utc_timestamp(evidence.observed_at),
                    identifier=evidence.id,
                    evidence={
                        "id": str(evidence.id),
                        "evidence_key": evidence.evidence_key,
                        "status": evidence.status,
                        "result": evidence.result,
                    },
                )
            )
        items.sort(key=lambda item: (item.occurred_at, str(item.identifier), item.kind), reverse=True)
        start = (page - 1) * page_size
        end = start + page_size
        chain_outcome, _reason, chain_evidence = TraceabilityEventService._chain_evidence(asset)
        if chain_outcome == VerificationOutcome.INVALID:
            proof_status = "Invalid proof"
        elif asset.anchors.filter(status=LedgerAnchorStatus.CONFIRMED).exists():
            proof_status = "Externally verified"
        else:
            proof_status = "Locally consistent — not externally anchored"
        failing = chain_evidence.get("failing_sequence")
        return AssetHistory(
            asset={
                "id": str(asset.id),
                "asset_key": asset.asset_key,
                "name": asset.name,
                "status": asset.status,
                "head_sequence": asset.head_sequence,
                "head_hash": asset.head_hash,
            },
            items=tuple(items[start:end]),
            proof_status=proof_status,
            failing_sequence=failing if isinstance(failing, int) else None,
            pagination={
                "page": page,
                "page_size": page_size,
                "total": len(items),
                "has_next": end < len(items),
            },
        )


class VerificationService:
    CREATE_FIELDS = {
        "verification_type",
        "asset",
        "anchor",
        "credential",
        "compliance_evidence",
        "idempotency_key",
        "presented_token_digest",
        "outcome",
        "reason_code",
        "chain_head_hash",
        "proof_evidence",
        "actor_id",
        "source_fingerprint",
        "correlation_id",
        "latency_ms",
    }

    def get_attempt(self, tenant_id: UUID, attempt_id: UUID | str) -> VerificationAttempt:
        try:
            return VerificationAttempt.objects.get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(attempt_id, "attempt_id")
            )
        except VerificationAttempt.DoesNotExist as exc:
            raise DomainNotFoundError("verification attempt") from exc

    def list_attempts(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[VerificationAttempt]:
        queryset = VerificationAttempt.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        for key in ("verification_type", "outcome", "asset_id", "reason_code"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        return queryset.order_by("-created_at", "id")

    def record_attempt(self, tenant_id: UUID, data: Mapping[str, Any]) -> VerificationAttempt:
        tenant = _uuid(tenant_id, "tenant_id")
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"verification_type", "idempotency_key", "outcome", "reason_code", "actor_id", "latency_ms"},
        )
        existing = VerificationAttempt.objects.filter(
            tenant_id=tenant,
            verification_type=values["verification_type"],
            idempotency_key=values["idempotency_key"],
        ).first()
        if existing is not None:
            comparison = {
                key: values.get(key, "" if key in {"presented_token_digest", "chain_head_hash", "source_fingerprint"} else None)
                for key in (
                    "outcome",
                    "reason_code",
                    "presented_token_digest",
                    "chain_head_hash",
                    "source_fingerprint",
                )
            }
            if not _matches(existing, comparison):
                raise IdempotencyConflictError()
            return existing
        try:
            with transaction.atomic():
                attempt = VerificationAttempt(
                    tenant_id=tenant, correlation_id=values.pop("correlation_id", _correlation()), **values
                )
                attempt.save()
                _emit_domain_event(
                    tenant,
                    "verification_attempt",
                    attempt.id,
                    "blockchain_traceability.verification.completed",
                    {
                        "verification_attempt_id": str(attempt.id),
                        "verification_type": attempt.verification_type,
                        "outcome": attempt.outcome,
                        "reason_code": attempt.reason_code,
                    },
                )
            logger.info(
                "Traceability verification completed",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": attempt.actor_id,
                    "correlation_id": attempt.correlation_id,
                    "verification_attempt_id": str(attempt.id),
                    "outcome": attempt.outcome,
                    "latency_ms": attempt.latency_ms,
                },
            )
            if attempt.verification_type == VerificationType.CHAIN:
                metrics.CHAIN_VERIFICATIONS.labels(outcome=attempt.outcome).inc()
            if attempt.verification_type == VerificationType.AUTHENTICITY:
                metrics.AUTHENTICITY_CHECKS.labels(outcome=attempt.outcome).inc()
            if attempt.outcome == VerificationOutcome.INVALID:
                metrics.INVALID_PROOFS.labels(verification_type=attempt.verification_type).inc()
            return attempt
        except ValidationError as exc:
            raise _model_error(exc) from exc


class TraceabilityEventService:
    CREATE_FIELDS = {
        "asset_id",
        "idempotency_key",
        "event_type",
        "schema_version",
        "occurred_at",
        "actor_ref",
        "location",
        "payload",
    }

    def append_event(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> TraceabilityEvent:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"asset_id", "idempotency_key", "event_type", "occurred_at", "actor_ref"},
        )
        asset_id = _uuid(values.pop("asset_id"), "asset_id")
        values.setdefault("schema_version", 1)
        values.setdefault("location", {})
        values.setdefault("payload", {})
        with transaction.atomic():
            try:
                asset = TraceabilityAsset.objects.select_for_update().get(tenant_id=tenant, id=asset_id, is_deleted=False)
            except TraceabilityAsset.DoesNotExist as exc:
                raise DomainNotFoundError("traceability asset") from exc
            if asset.status == TraceabilityAssetStatus.RETIRED:
                raise DomainConflictError("asset_retired", "Events cannot be appended to a retired asset.")
            existing = TraceabilityEvent.objects.filter(
                tenant_id=tenant, asset=asset, idempotency_key=values["idempotency_key"]
            ).first()
            if existing is not None:
                comparable = {key: values[key] for key in ("event_type", "schema_version", "occurred_at", "actor_ref", "location", "payload")}
                if not _matches(existing, comparable):
                    raise IdempotencyConflictError()
                return existing
            sequence = asset.head_sequence + 1
            event_hash = compute_event_hash(
                tenant_id=tenant,
                asset_id=asset.id,
                sequence=sequence,
                event_type=values["event_type"],
                schema_version=values["schema_version"],
                occurred_at=values["occurred_at"],
                actor_ref=values["actor_ref"],
                location=values["location"],
                payload=values["payload"],
                previous_hash=asset.head_hash,
            )
            try:
                event = TraceabilityEvent.objects.create(
                    tenant_id=tenant,
                    asset=asset,
                    sequence=sequence,
                    previous_hash=asset.head_hash,
                    event_hash=event_hash,
                    created_by=actor,
                    correlation_id=_correlation(),
                    **values,
                )
                asset.head_sequence = sequence
                asset.head_hash = event_hash
                asset.updated_by = actor
                asset.save(update_fields=["head_sequence", "head_hash", "updated_by", "updated_at"])
                _emit_domain_event(
                    tenant,
                    "traceability_event",
                    event.id,
                    "blockchain_traceability.event.appended",
                    {
                        "event_id": str(event.id),
                        "asset_id": str(asset.id),
                        "sequence": sequence,
                        "event_hash": event_hash,
                        "correlation_id": event.correlation_id,
                    },
                )
            except ValidationError as exc:
                raise _model_error(exc) from exc
            logger.info(
                "Traceability event appended",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": actor,
                    "correlation_id": event.correlation_id,
                    "asset_id": str(asset.id),
                    "event_id": str(event.id),
                },
            )
            metrics.EVENTS_APPENDED.labels(outcome="succeeded").inc()
            metrics.HASH_CHAIN_LENGTH.set(asset.head_sequence)
            return event

    def get_event(self, tenant_id: UUID, event_id: UUID | str) -> TraceabilityEvent:
        try:
            return TraceabilityEvent.objects.select_related("asset").get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(event_id, "event_id")
            )
        except TraceabilityEvent.DoesNotExist as exc:
            raise DomainNotFoundError("traceability event") from exc

    def list_events(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[TraceabilityEvent]:
        queryset = TraceabilityEvent.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("asset")
        for key in ("asset_id", "event_type", "actor_ref"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        if filters and filters.get("occurred_after"):
            queryset = queryset.filter(occurred_at__gte=filters["occurred_after"])
        if filters and filters.get("occurred_before"):
            queryset = queryset.filter(occurred_at__lte=filters["occurred_before"])
        return queryset.order_by("sequence", "id")

    @staticmethod
    def _chain_evidence(asset: TraceabilityAsset) -> tuple[str, str, dict[str, Any]]:
        previous_hash = ""
        expected_sequence = 1
        for event in TraceabilityEvent.objects.filter(tenant_id=asset.tenant_id, asset=asset).order_by("sequence").iterator(
            chunk_size=500
        ):
            if event.sequence != expected_sequence:
                return (
                    VerificationOutcome.INVALID,
                    "CHAIN_SEQUENCE_GAP",
                    {"failing_sequence": expected_sequence, "observed_sequence": event.sequence},
                )
            expected_hash = compute_event_hash(
                tenant_id=event.tenant_id,
                asset_id=event.asset_id,
                sequence=event.sequence,
                event_type=event.event_type,
                schema_version=event.schema_version,
                occurred_at=event.occurred_at,
                actor_ref=event.actor_ref,
                location=event.location,
                payload=event.payload,
                previous_hash=previous_hash,
            )
            if event.previous_hash != previous_hash or event.event_hash != expected_hash:
                return (
                    VerificationOutcome.INVALID,
                    "CHAIN_HASH_MISMATCH",
                    {
                        "failing_sequence": event.sequence,
                        "expected_previous_hash": previous_hash,
                        "observed_previous_hash": event.previous_hash,
                        "expected_event_hash": expected_hash,
                        "observed_event_hash": event.event_hash,
                    },
                )
            previous_hash = event.event_hash
            expected_sequence += 1
        event_count = expected_sequence - 1
        if asset.head_sequence != event_count or asset.head_hash != previous_hash:
            return (
                VerificationOutcome.INVALID,
                "ASSET_HEAD_MISMATCH",
                {
                    "event_count": event_count,
                    "computed_head_hash": previous_hash,
                    "stored_head_sequence": asset.head_sequence,
                    "stored_head_hash": asset.head_hash,
                },
            )
        if event_count == 0:
            return VerificationOutcome.INCONCLUSIVE, "EMPTY_CHAIN", {"event_count": 0, "locally_consistent": True}
        return (
            VerificationOutcome.VERIFIED,
            "CHAIN_VALID",
            {"event_count": event_count, "head_hash": previous_hash, "locally_consistent": True},
        )

    def verify_chain(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, idempotency_key: str
    ) -> VerificationAttempt:
        started = time.perf_counter()
        asset = TraceabilityAssetService().get_asset(tenant_id, asset_id)
        outcome, reason, evidence = self._chain_evidence(asset)
        return VerificationService().record_attempt(
            asset.tenant_id,
            {
                "verification_type": VerificationType.CHAIN,
                "asset": asset,
                "idempotency_key": idempotency_key,
                "outcome": outcome,
                "reason_code": reason,
                "chain_head_hash": asset.head_hash,
                "proof_evidence": evidence,
                "actor_id": _actor(actor_id),
                "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
            },
        )


class LedgerAnchorService:
    CREATE_FIELDS = {"asset_id", "network_id", "start_sequence", "end_sequence", "idempotency_key"}

    def __init__(self, *, provider: LedgerProviderAdapter | None = None) -> None:
        self.provider = provider

    def _provider(self, network: LedgerNetwork) -> LedgerProviderAdapter:
        return self.provider or get_ledger_provider(network.provider_type)

    def get_anchor(self, tenant_id: UUID, anchor_id: UUID | str) -> LedgerAnchor:
        try:
            return LedgerAnchor.objects.select_related("asset", "network").get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(anchor_id, "anchor_id")
            )
        except LedgerAnchor.DoesNotExist as exc:
            raise DomainNotFoundError("ledger anchor") from exc

    def list_anchors(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[LedgerAnchor]:
        queryset = LedgerAnchor.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("asset", "network")
        for key in ("asset_id", "network_id", "status"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        if filters and filters.get("created_after"):
            queryset = queryset.filter(created_at__gte=filters["created_after"])
        if filters and filters.get("created_before"):
            queryset = queryset.filter(created_at__lte=filters["created_before"])
        return queryset.order_by("-created_at", "id")

    def request_anchor(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> tuple[LedgerAnchor, AsyncJob]:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        values = _data(data, allowed=self.CREATE_FIELDS, required={"asset_id", "network_id", "idempotency_key"})
        asset = TraceabilityAssetService().get_asset(tenant, values.pop("asset_id"))
        network = LedgerNetworkService().get_network(tenant, values.pop("network_id"))
        if network.status != LedgerNetworkStatus.ACTIVE:
            raise DomainConflictError("network_not_active", "Anchors require an active ledger network.")
        start_sequence = int(values.pop("start_sequence", 1))
        end_sequence = int(values.pop("end_sequence", asset.head_sequence))
        if start_sequence < 1 or end_sequence < start_sequence or end_sequence > asset.head_sequence:
            raise BlockchainTraceabilityError("invalid_anchor_range", "The requested event range is invalid.", status_code=400)
        hashes = list(
            TraceabilityEvent.objects.filter(
                tenant_id=tenant, asset=asset, sequence__gte=start_sequence, sequence__lte=end_sequence
            )
            .order_by("sequence")
            .values_list("event_hash", flat=True)
        )
        if len(hashes) != end_sequence - start_sequence + 1:
            raise DomainConflictError("chain_gap", "The event range is not contiguous and cannot be anchored.")
        root_hash = compute_merkle_root(hashes)
        idempotency_key = str(values["idempotency_key"])
        with transaction.atomic():
            existing = LedgerAnchor.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
            if existing is not None:
                if not (
                    existing.asset_id == asset.id
                    and existing.network_id == network.id
                    and existing.start_sequence == start_sequence
                    and existing.end_sequence == end_sequence
                    and existing.root_hash == root_hash
                ):
                    raise IdempotencyConflictError()
                if existing.async_job_id is None:
                    raise DomainConflictError("anchor_job_missing", "The anchor has no durable job evidence.")
                return existing, AsyncJob.objects.get(tenant_id=tenant, id=existing.async_job_id)
            anchor = LedgerAnchor.objects.create(
                tenant_id=tenant,
                asset=asset,
                network=network,
                start_sequence=start_sequence,
                end_sequence=end_sequence,
                root_hash=root_hash,
                idempotency_key=idempotency_key,
                created_by=actor,
            )
            job = enqueue(
                tenant,
                actor,
                SUBMIT_ANCHOR_COMMAND,
                {"anchor_id": str(anchor.id), "tenant_id": str(tenant), "correlation_id": _correlation()},
                f"{SUBMIT_ANCHOR_COMMAND}:{idempotency_key}",
            )
            anchor.async_job_id = job.id
            anchor.save(update_fields=["async_job_id", "updated_at"])
            _emit_domain_event(
                tenant,
                "ledger_anchor",
                anchor.id,
                "blockchain_traceability.anchor.queued",
                {
                    "anchor_id": str(anchor.id),
                    "asset_id": str(asset.id),
                    "network_id": str(network.id),
                    "job_id": str(job.id),
                },
            )
            metrics.ANCHOR_REQUESTS.labels(outcome="queued").inc()
            return anchor, job

    def _fail_anchor(self, anchor: LedgerAnchor, code: str, message: str, transition_key: str) -> None:
        if anchor.status in {LedgerAnchorStatus.SUBMITTING, LedgerAnchorStatus.SUBMITTED}:
            anchor = _transition(ANCHOR_MACHINE, anchor, "fail", transition_key, "system", failure_code=code)
        anchor.failure_code = code[:64]
        anchor.failure_message = message
        anchor.last_checked_at = timezone.now()
        anchor.save(update_fields=["failure_code", "failure_message", "last_checked_at", "updated_at"])
        _emit_domain_event(
            anchor.tenant_id,
            "ledger_anchor",
            anchor.id,
            "blockchain_traceability.anchor.failed",
            {"anchor_id": str(anchor.id), "failure_code": code},
        )
        metrics.ANCHOR_FAILURES.labels(reason=code[:64]).inc()

    def submit_anchor_job(self, job: AsyncJob) -> dict[str, Any]:
        provider_started = time.perf_counter()
        if job.command != SUBMIT_ANCHOR_COMMAND:
            raise BlockchainTraceabilityError("invalid_job", "The job command is not an anchor submission.", status_code=400)
        tenant = _uuid(job.tenant_id, "tenant_id")
        anchor_id = job.payload.get("anchor_id") if isinstance(job.payload, dict) else None
        if not anchor_id:
            raise BlockchainTraceabilityError("invalid_job", "The durable job is missing anchor identity.", status_code=400)
        with transaction.atomic():
            anchor = LedgerAnchor.objects.select_for_update().select_related("network", "asset").get(
                tenant_id=tenant, id=_uuid(anchor_id, "anchor_id")
            )
            if anchor.async_job_id != job.id:
                raise IdempotencyConflictError("The job does not own this anchor submission.")
            if anchor.status in {LedgerAnchorStatus.SUBMITTED, LedgerAnchorStatus.CONFIRMED}:
                return {
                    "anchor_id": str(anchor.id),
                    "status": anchor.status,
                    "provider_transaction_id": anchor.provider_transaction_id,
                }
            if anchor.status != LedgerAnchorStatus.QUEUED:
                raise DomainConflictError("illegal_state", "The anchor is not queued for submission.")
            anchor = _transition(ANCHOR_MACHINE, anchor, "start_submission", f"job:{job.id}:start", "system")
        try:
            receipt = self._provider(anchor.network).submit_anchor(anchor.network, anchor, str(job.id))
            if not isinstance(receipt, SubmissionReceipt):
                raise InvalidProviderResponseError("provider returned invalid submission evidence")
        except (AdapterNotRegisteredError, ProviderUnavailableError) as exc:
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
                self._fail_anchor(locked, "PROVIDER_UNAVAILABLE", "The ledger provider could not submit the anchor.", f"job:{job.id}:fail")
            metrics.PROVIDER_UNAVAILABLE.labels(capability="anchor_submission").inc()
            metrics.ANCHOR_LATENCY.labels(outcome="unavailable").observe(time.perf_counter() - provider_started)
            raise _provider_failure(exc, "ledger_anchor_submission") from exc
        except ProviderError as exc:
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
                self._fail_anchor(
                    locked,
                    "INVALID_PROVIDER_RESPONSE",
                    "The ledger provider returned invalid submission evidence.",
                    f"job:{job.id}:invalid",
                )
            metrics.ANCHOR_LATENCY.labels(outcome="failed").observe(time.perf_counter() - provider_started)
            raise BlockchainTraceabilityError(
                "invalid_provider_response", "The ledger provider returned invalid submission evidence.", status_code=502
            ) from exc
        if receipt.simulated or not receipt.accepted:
            code = "SIMULATED_PROVIDER" if receipt.simulated else (receipt.failure_code or "PROVIDER_REJECTED")
            message = "Simulated provider evidence cannot anchor a traceability proof." if receipt.simulated else (
                receipt.failure_message or "The provider rejected the anchor."
            )
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
                self._fail_anchor(locked, code, message, f"job:{job.id}:rejected")
            raise BlockchainTraceabilityError(code.lower(), message, status_code=422)
        with transaction.atomic():
            locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
            locked = _transition(ANCHOR_MACHINE, locked, "accept_submission", f"job:{job.id}:accepted", "system")
            locked.provider_transaction_id = receipt.provider_transaction_id
            locked.transaction_hash = receipt.transaction_hash
            locked.provider_receipt = _safe_receipt(receipt.receipt)
            locked.submitted_at = receipt.submitted_at or timezone.now()
            locked.failure_code = ""
            locked.failure_message = ""
            locked.save(
                update_fields=[
                    "provider_transaction_id",
                    "transaction_hash",
                    "provider_receipt",
                    "submitted_at",
                    "failure_code",
                    "failure_message",
                    "updated_at",
                ]
            )
            metrics.ANCHOR_LATENCY.labels(outcome="submitted").observe(time.perf_counter() - provider_started)
            return {
                "anchor_id": str(locked.id),
                "status": locked.status,
                "provider_transaction_id": locked.provider_transaction_id,
            }

    def _apply_receipt(self, anchor: LedgerAnchor, receipt: AnchorReceipt, actor_id: str) -> LedgerAnchor:
        if receipt.provider_transaction_id != anchor.provider_transaction_id:
            raise InvalidProviderResponseError("receipt transaction identity does not match the anchor")
        anchor.transaction_hash = receipt.transaction_hash or anchor.transaction_hash
        anchor.block_number = receipt.block_number
        anchor.block_hash = receipt.block_hash
        anchor.confirmations = receipt.confirmations
        anchor.provider_receipt = _safe_receipt(receipt.receipt)
        anchor.last_checked_at = receipt.observed_at or timezone.now()
        if receipt.final and receipt.confirmations >= anchor.network.confirmation_depth:
            if receipt.simulated:
                raise InvalidProviderResponseError("simulated receipts cannot confirm anchors")
            anchor.confirmed_at = receipt.observed_at or timezone.now()
        anchor.save(
            update_fields=[
                "transaction_hash",
                "block_number",
                "block_hash",
                "confirmations",
                "provider_receipt",
                "last_checked_at",
                "confirmed_at",
                "updated_at",
            ]
        )
        if anchor.confirmed_at is not None:
            anchor = _transition(
                ANCHOR_MACHINE,
                anchor,
                "confirm",
                f"receipt:{anchor.provider_transaction_id}:{anchor.confirmations}",
                actor_id,
            )
            network = anchor.network
            network.last_successful_anchor_at = anchor.confirmed_at
            network.save(update_fields=["last_successful_anchor_at", "updated_at"])
            _emit_domain_event(
                anchor.tenant_id,
                "ledger_anchor",
                anchor.id,
                "blockchain_traceability.anchor.confirmed",
                {
                    "anchor_id": str(anchor.id),
                    "network_id": str(network.id),
                    "confirmations": anchor.confirmations,
                },
            )
        return anchor

    def refresh_receipt(
        self, tenant_id: UUID, anchor_id: UUID | str, actor_id: str
    ) -> OperationResult[LedgerAnchor]:
        actor = _actor(actor_id)
        anchor = self.get_anchor(tenant_id, anchor_id)
        if anchor.status == LedgerAnchorStatus.CONFIRMED:
            return OperationResult.succeeded(
                anchor,
                provider=anchor.network.provider_type,
                evidence={"anchor_id": str(anchor.id), "confirmations": anchor.confirmations},
            )
        if anchor.status != LedgerAnchorStatus.SUBMITTED or not anchor.provider_transaction_id:
            return OperationResult.failed(
                code="ANCHOR_NOT_SUBMITTED", message="The anchor has no provider receipt to refresh.", http_status=409
            )
        try:
            receipt = self._provider(anchor.network).get_receipt(anchor.network, anchor.provider_transaction_id)
            if not isinstance(receipt, AnchorReceipt):
                raise InvalidProviderResponseError("provider returned invalid receipt evidence")
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().select_related("network").get(
                    tenant_id=anchor.tenant_id, id=anchor.id
                )
                locked = self._apply_receipt(locked, receipt, actor)
            return OperationResult.succeeded(
                locked,
                provider=locked.network.provider_type,
                evidence={"anchor_id": str(locked.id), "confirmations": locked.confirmations},
            )
        except (AdapterNotRegisteredError, ProviderUnavailableError):
            metrics.PROVIDER_UNAVAILABLE.labels(capability="receipt_refresh").inc()
            return OperationResult.unavailable(
                capability="ledger_receipt", provider=anchor.network.provider_type, evidence={"anchor_id": str(anchor.id)}
            )
        except ProviderError:
            return OperationResult.failed(
                code="INVALID_PROVIDER_RECEIPT",
                message="The provider receipt could not be validated.",
                provider=anchor.network.provider_type,
                http_status=502,
            )

    def verify_anchor(
        self, tenant_id: UUID, anchor_id: UUID | str, actor_id: str, idempotency_key: str
    ) -> VerificationAttempt:
        started = time.perf_counter()
        actor = _actor(actor_id)
        anchor = self.get_anchor(tenant_id, anchor_id)
        outcome = VerificationOutcome.INCONCLUSIVE
        reason = "ANCHOR_NOT_CONFIRMED"
        evidence: dict[str, Any] = {"anchor_status": anchor.status, "root_hash": anchor.root_hash}
        try:
            proof = self._provider(anchor.network).verify_anchor(anchor.network, anchor)
            if not isinstance(proof, ProofResult):
                raise InvalidProviderResponseError("provider returned invalid proof")
            if proof.simulated:
                outcome, reason = VerificationOutcome.INCONCLUSIVE, "SIMULATED_PROVIDER"
            elif proof.verified and anchor.status == LedgerAnchorStatus.CONFIRMED:
                outcome, reason = VerificationOutcome.VERIFIED, proof.reason_code or "ANCHOR_VERIFIED"
            elif proof.verified:
                outcome, reason = VerificationOutcome.INCONCLUSIVE, "ANCHOR_NOT_CONFIRMED"
            else:
                outcome, reason = VerificationOutcome.INVALID, proof.reason_code or "INVALID_PROOF"
            evidence.update(_safe_receipt(proof.evidence))
        except (AdapterNotRegisteredError, ProviderUnavailableError):
            metrics.PROVIDER_UNAVAILABLE.labels(capability="anchor_verification").inc()
            outcome, reason = VerificationOutcome.DEPENDENCY_UNAVAILABLE, "PROVIDER_UNAVAILABLE"
        except ProviderError:
            outcome, reason = VerificationOutcome.INVALID, "INVALID_PROVIDER_PROOF"
        return VerificationService().record_attempt(
            anchor.tenant_id,
            {
                "verification_type": VerificationType.ANCHOR,
                "asset": anchor.asset,
                "anchor": anchor,
                "idempotency_key": idempotency_key,
                "outcome": outcome,
                "reason_code": reason,
                "chain_head_hash": anchor.asset.head_hash,
                "proof_evidence": evidence,
                "actor_id": actor,
                "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
            },
        )

    def retry_anchor(
        self, tenant_id: UUID, anchor_id: UUID | str, actor_id: str, transition_key: str
    ) -> tuple[LedgerAnchor, AsyncJob]:
        actor = _actor(actor_id)
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            anchor = LedgerAnchor.objects.select_for_update().get(pk=self.get_anchor(tenant, anchor_id).pk)
            anchor = _transition(ANCHOR_MACHINE, anchor, "retry", transition_key, actor)
            job = enqueue(
                tenant,
                actor,
                SUBMIT_ANCHOR_COMMAND,
                {"anchor_id": str(anchor.id), "tenant_id": str(tenant), "correlation_id": _correlation()},
                f"{SUBMIT_ANCHOR_COMMAND}:retry:{anchor.id}:{transition_key}",
            )
            anchor.async_job_id = job.id
            anchor.failure_code = ""
            anchor.failure_message = ""
            anchor.save(update_fields=["async_job_id", "failure_code", "failure_message", "updated_at"])
            return anchor, job


class AuthenticityService:
    def __init__(
        self,
        *,
        issuer_adapter: CredentialIssuerAdapter | None = None,
        issuer_key_ref: str | None = None,
    ) -> None:
        self.issuer_adapter = issuer_adapter
        self.issuer_key_ref = issuer_key_ref

    def _issuer_for_issue(self) -> tuple[CredentialIssuerAdapter, str]:
        adapter = self.issuer_adapter
        if adapter is None:
            issuer_type = getattr(settings, "BLOCKCHAIN_TRACEABILITY_ISSUER_TYPE", "django_signing_v1")
            try:
                adapter = get_credential_issuer(str(issuer_type))
            except AdapterNotRegisteredError as exc:
                raise DependencyUnavailableError(
                    "credential_issuer", "The configured credential issuer is not registered."
                ) from exc
        key_ref = self.issuer_key_ref or getattr(adapter, "issuer_key_ref", "") or getattr(
            settings, "BLOCKCHAIN_TRACEABILITY_ISSUER_KEY_REF", ""
        )
        if not isinstance(key_ref, str) or not key_ref.strip():
            raise DependencyUnavailableError("credential_issuer_key", "A credential issuer key reference is required.")
        return adapter, key_ref.strip()

    def issue_credential(
        self,
        tenant_id: UUID,
        asset_id: UUID | str,
        actor_id: str,
        claims: Mapping[str, Any],
        expires_at: datetime | None,
    ) -> IssuedCredential:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        asset = TraceabilityAssetService().get_asset(tenant, asset_id)
        if asset.status == TraceabilityAssetStatus.RETIRED:
            raise DomainConflictError("asset_retired", "Credentials cannot be issued for a retired asset.")
        if not isinstance(claims, Mapping):
            raise BlockchainTraceabilityError("validation_error", "claims must be an object.", status_code=400)
        if {"asset_id", "public_id"} & set(claims):
            raise BlockchainTraceabilityError("reserved_claim", "asset_id and public_id are issuer-managed claims.", status_code=400)
        issued_at = timezone.now()
        if expires_at is not None and expires_at <= issued_at:
            raise BlockchainTraceabilityError("validation_error", "expires_at must be in the future.", status_code=400)
        public_id = str(uuid.uuid4())
        bound_claims = {**dict(claims), "asset_id": str(asset.id), "public_id": public_id}
        canonical_claims = canonical_json(bound_claims)
        claims_hash = sha256_hex(canonical_claims)
        token = secrets.token_urlsafe(32)
        token_digest = sha256_hex(token)
        adapter, issuer_key_ref = self._issuer_for_issue()
        try:
            signature_result = adapter.sign_claims(tenant, issuer_key_ref, canonical_claims)
        except ProviderUnavailableError as exc:
            metrics.PROVIDER_UNAVAILABLE.labels(capability="credential_signing").inc()
            raise DependencyUnavailableError("credential_issuer") from exc
        except ProviderError as exc:
            raise BlockchainTraceabilityError(
                "credential_signing_failed", "The credential could not be signed.", status_code=502
            ) from exc
        credential_type = str(getattr(adapter, "issuer_type", "signed_claims"))[:64]
        try:
            with transaction.atomic():
                credential = AuthenticityCredential.objects.create(
                    tenant_id=tenant,
                    asset=asset,
                    public_id=public_id,
                    credential_type=credential_type,
                    token_digest=token_digest,
                    claims=bound_claims,
                    claims_hash=claims_hash,
                    signature_algorithm=signature_result.signature_algorithm,
                    issuer_key_ref=issuer_key_ref,
                    signature=signature_result.signature,
                    issued_at=issued_at,
                    expires_at=expires_at,
                    created_by=actor,
                )
                _emit_domain_event(
                    tenant,
                    "authenticity_credential",
                    credential.id,
                    "blockchain_traceability.credential.issued",
                    {"credential_id": str(credential.id), "asset_id": str(asset.id), "public_id": credential.public_id},
                )
        except ValidationError as exc:
            raise _model_error(exc) from exc
        return IssuedCredential(credential=credential, token=token)

    def get_credential(self, tenant_id: UUID, credential_id: UUID | str) -> AuthenticityCredential:
        try:
            return AuthenticityCredential.objects.select_related("asset").get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(credential_id, "credential_id")
            )
        except AuthenticityCredential.DoesNotExist as exc:
            raise DomainNotFoundError("authenticity credential") from exc

    def list_credentials(
        self, tenant_id: UUID, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[AuthenticityCredential]:
        queryset = AuthenticityCredential.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("asset")
        for key in ("asset_id", "status", "credential_type"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        if filters and filters.get("expires_after"):
            queryset = queryset.filter(expires_at__gte=filters["expires_after"])
        if filters and filters.get("expires_before"):
            queryset = queryset.filter(expires_at__lte=filters["expires_before"])
        return queryset.order_by("-created_at", "id")

    def revoke_credential(
        self, tenant_id: UUID, credential_id: UUID | str, actor_id: str, reason: str, transition_key: str
    ) -> AuthenticityCredential:
        actor = _actor(actor_id)
        if not isinstance(reason, str) or not reason.strip():
            raise BlockchainTraceabilityError("validation_error", "A revocation reason is required.", status_code=400)
        with transaction.atomic():
            credential = AuthenticityCredential.objects.select_for_update().get(
                pk=self.get_credential(tenant_id, credential_id).pk
            )
            credential.revoked_at = timezone.now()
            credential.revocation_reason = reason.strip()
            credential.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
            credential = _transition(CREDENTIAL_MACHINE, credential, "revoke", transition_key, actor, reason=reason.strip())
            _emit_domain_event(
                credential.tenant_id,
                "authenticity_credential",
                credential.id,
                "blockchain_traceability.credential.revoked",
                {"credential_id": str(credential.id), "asset_id": str(credential.asset_id), "actor_id": actor},
            )
            return credential

    def _record_authenticity(
        self,
        tenant_id: UUID,
        actor_id: str,
        idempotency_key: str,
        started: float,
        token_digest: str,
        outcome: str,
        reason: str,
        evidence: Mapping[str, Any],
        credential: AuthenticityCredential | None = None,
    ) -> VerificationAttempt:
        return VerificationService().record_attempt(
            tenant_id,
            {
                "verification_type": VerificationType.AUTHENTICITY,
                "asset": credential.asset if credential else None,
                "credential": credential,
                "idempotency_key": idempotency_key,
                "presented_token_digest": token_digest,
                "outcome": outcome,
                "reason_code": reason,
                "chain_head_hash": credential.asset.head_hash if credential else "",
                "proof_evidence": dict(evidence),
                "actor_id": _actor(actor_id),
                "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
            },
        )

    def verify_authenticity(
        self, tenant_id: UUID, actor_id: str, public_id: str, token: str, idempotency_key: str
    ) -> VerificationAttempt:
        tenant = _uuid(tenant_id, "tenant_id")
        started = time.perf_counter()
        if not isinstance(token, str) or not token:
            raise BlockchainTraceabilityError("validation_error", "token is required.", status_code=400)
        token_digest = sha256_hex(token)
        credential = AuthenticityCredential.objects.select_related("asset").filter(tenant_id=tenant, public_id=public_id).first()
        if credential is None:
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_NOT_FOUND", {"credential_found": False}
            )
        if not hmac.compare_digest(token_digest, credential.token_digest):
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.NOT_AUTHENTIC,
                "TOKEN_MISMATCH", {"credential_found": True, "token_match": False}, credential
            )
        if credential.status == AuthenticityCredentialStatus.REVOKED:
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_REVOKED", {"token_match": True, "credential_status": credential.status}, credential
            )
        if credential.expires_at is not None and credential.expires_at <= timezone.now():
            with transaction.atomic():
                locked = AuthenticityCredential.objects.select_for_update().get(tenant_id=tenant, id=credential.id)
                if locked.status == AuthenticityCredentialStatus.ACTIVE:
                    credential = _transition(
                        CREDENTIAL_MACHINE, locked, "expire", f"expiry:{credential.expires_at.isoformat()}", "system"
                    )
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_EXPIRED", {"token_match": True, "credential_status": credential.status}, credential
            )
        if credential.claims.get("asset_id") != str(credential.asset_id) or credential.claims.get("public_id") != public_id:
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.INVALID,
                "CLAIM_BINDING_INVALID", {"token_match": True, "claim_binding": False}, credential
            )
        try:
            adapter = self.issuer_adapter or get_credential_issuer(credential.credential_type)
            proof = adapter.verify_signature(tenant, credential)
            if not isinstance(proof, ProofResult):
                raise InvalidProviderResponseError("issuer returned invalid proof")
        except (AdapterNotRegisteredError, ProviderUnavailableError):
            metrics.PROVIDER_UNAVAILABLE.labels(capability="credential_verification").inc()
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.DEPENDENCY_UNAVAILABLE,
                "ISSUER_UNAVAILABLE", {"token_match": True, "claim_binding": True}, credential
            )
        except ProviderError:
            return self._record_authenticity(
                tenant, actor_id, idempotency_key, started, token_digest, VerificationOutcome.INVALID,
                "INVALID_SIGNATURE_EVIDENCE", {"token_match": True, "claim_binding": True}, credential
            )
        if proof.simulated:
            outcome, reason = VerificationOutcome.INCONCLUSIVE, "SIMULATED_PROVIDER"
        elif not proof.verified:
            outcome, reason = VerificationOutcome.NOT_AUTHENTIC, proof.reason_code or "SIGNATURE_INVALID"
        else:
            chain_outcome, chain_reason, chain_evidence = TraceabilityEventService._chain_evidence(credential.asset)
            if chain_outcome == VerificationOutcome.INVALID:
                outcome, reason = VerificationOutcome.INVALID, chain_reason
            elif chain_outcome == VerificationOutcome.INCONCLUSIVE:
                outcome, reason = VerificationOutcome.INCONCLUSIVE, chain_reason
            else:
                outcome, reason = VerificationOutcome.VERIFIED, "AUTHENTIC"
            proof = ProofResult(
                verified=proof.verified,
                reason_code=proof.reason_code,
                evidence={**dict(proof.evidence), "chain": chain_evidence},
                simulated=False,
            )
        return self._record_authenticity(
            tenant,
            actor_id,
            idempotency_key,
            started,
            token_digest,
            outcome,
            reason,
            {"token_match": True, "claim_binding": True, **dict(proof.evidence)},
            credential,
        )


class ComplianceEvidenceService:
    CREATE_FIELDS = {
        "asset_id",
        "event_id",
        "evidence_key",
        "evidence_type",
        "standard",
        "jurisdiction",
        "result",
        "details",
        "document_ref",
        "observed_at",
        "valid_until",
        "supersedes_id",
    }
    UPDATE_FIELDS = CREATE_FIELDS - {"asset_id", "supersedes_id"}

    def __init__(self, *, document_resolver: DocumentReferenceResolver | None = None) -> None:
        self.document_resolver = document_resolver

    def _validate_document(self, tenant: UUID, values: Mapping[str, Any]) -> None:
        document_ref = values.get("document_ref")
        if document_ref is None:
            return
        document_id = _uuid(document_ref, "document_ref")
        resolver = self.document_resolver
        if resolver is None:
            try:
                resolver = get_document_resolver()
            except AdapterNotRegisteredError as exc:
                raise DependencyUnavailableError("document_reference") from exc
        try:
            result = resolver.validate_reference(tenant, document_id)
        except ProviderUnavailableError as exc:
            raise DependencyUnavailableError("document_reference") from exc
        if not result.valid:
            raise DomainNotFoundError("document")

    def _references(self, tenant: UUID, values: dict[str, Any]) -> dict[str, Any]:
        asset_id = values.pop("asset_id", None)
        if asset_id is not None:
            values["asset"] = TraceabilityAssetService().get_asset(tenant, asset_id)
        event_id = values.pop("event_id", None)
        if event_id is not None:
            values["event"] = TraceabilityEventService().get_event(tenant, event_id)
        supersedes_id = values.pop("supersedes_id", None)
        if supersedes_id is not None:
            values["supersedes"] = self.get_evidence(tenant, supersedes_id)
        return values

    def create_draft(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> ComplianceEvidence:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"asset_id", "evidence_key", "evidence_type", "standard", "result", "observed_at"},
        )
        self._validate_document(tenant, values)
        values = self._references(tenant, values)
        try:
            evidence = ComplianceEvidence(tenant_id=tenant, created_by=actor, **values)
            evidence.save()
            return evidence
        except ValidationError as exc:
            raise _model_error(exc) from exc

    def get_evidence(self, tenant_id: UUID, evidence_id: UUID | str) -> ComplianceEvidence:
        try:
            return ComplianceEvidence.objects.select_related("asset", "event", "supersedes").get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(evidence_id, "evidence_id"), is_deleted=False
            )
        except ComplianceEvidence.DoesNotExist as exc:
            raise DomainNotFoundError("compliance evidence") from exc

    def list_evidence(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[ComplianceEvidence]:
        queryset = ComplianceEvidence.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False).select_related(
            "asset", "event", "supersedes"
        )
        for key in ("asset_id", "evidence_type", "standard", "jurisdiction", "result", "status"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        if filters and filters.get("observed_after"):
            queryset = queryset.filter(observed_at__gte=filters["observed_after"])
        if filters and filters.get("observed_before"):
            queryset = queryset.filter(observed_at__lte=filters["observed_before"])
        return queryset.order_by("-observed_at", "id")

    def update_draft(
        self, tenant_id: UUID, evidence_id: UUID | str, actor_id: str, data: Mapping[str, Any]
    ) -> ComplianceEvidence:
        actor = _actor(actor_id)
        values = _data(data, allowed=self.UPDATE_FIELDS)
        tenant = _uuid(tenant_id, "tenant_id")
        self._validate_document(tenant, values)
        values = self._references(tenant, values)
        with transaction.atomic():
            evidence = ComplianceEvidence.objects.select_for_update().get(pk=self.get_evidence(tenant, evidence_id).pk)
            if evidence.status != ComplianceEvidenceStatus.DRAFT:
                raise DomainConflictError("evidence_finalized", "Finalized evidence cannot be edited.")
            for field, value in values.items():
                setattr(evidence, field, value)
            evidence.updated_by = actor
            try:
                evidence.save()
            except ValidationError as exc:
                raise _model_error(exc) from exc
            return evidence

    def delete_draft(self, tenant_id: UUID, evidence_id: UUID | str, actor_id: str) -> None:
        actor = _actor(actor_id)
        with transaction.atomic():
            evidence = ComplianceEvidence.objects.select_for_update().get(pk=self.get_evidence(tenant_id, evidence_id).pk)
            if evidence.status != ComplianceEvidenceStatus.DRAFT:
                raise DomainConflictError("evidence_finalized", "Finalized evidence cannot be deleted.")
            evidence.is_deleted = True
            evidence.deleted_at = timezone.now()
            evidence.deleted_by = actor
            evidence.updated_by = actor
            evidence.save()

    @staticmethod
    def _content_document(evidence: ComplianceEvidence) -> dict[str, Any]:
        def stamp(value: datetime | None) -> str | None:
            return normalize_utc_timestamp(value) if value is not None else None

        return {
            "tenant_id": str(evidence.tenant_id),
            "asset_id": str(evidence.asset_id),
            "event_id": str(evidence.event_id) if evidence.event_id else None,
            "evidence_key": evidence.evidence_key,
            "evidence_type": evidence.evidence_type,
            "standard": evidence.standard,
            "jurisdiction": evidence.jurisdiction,
            "result": evidence.result,
            "details": evidence.details,
            "document_ref": str(evidence.document_ref) if evidence.document_ref else None,
            "observed_at": stamp(evidence.observed_at),
            "valid_until": stamp(evidence.valid_until),
            "supersedes_id": str(evidence.supersedes_id) if evidence.supersedes_id else None,
        }

    def finalize(
        self, tenant_id: UUID, evidence_id: UUID | str, actor_id: str, transition_key: str
    ) -> ComplianceEvidence:
        actor = _actor(actor_id)
        with transaction.atomic():
            evidence = ComplianceEvidence.objects.select_for_update().get(pk=self.get_evidence(tenant_id, evidence_id).pk)
            if evidence.status != ComplianceEvidenceStatus.DRAFT:
                raise DomainConflictError("evidence_not_draft", "Only draft evidence can be finalized.")
            evidence.content_hash = sha256_hex(canonical_json(self._content_document(evidence)))
            evidence.finalized_at = timezone.now()
            evidence.updated_by = actor
            evidence.save(update_fields=["content_hash", "finalized_at", "updated_by", "updated_at"])
            evidence = _transition(EVIDENCE_MACHINE, evidence, "finalize", transition_key, actor)
            _emit_domain_event(
                evidence.tenant_id,
                "compliance_evidence",
                evidence.id,
                "blockchain_traceability.compliance.finalized",
                {"evidence_id": str(evidence.id), "asset_id": str(evidence.asset_id), "result": evidence.result},
            )
            return evidence

    def supersede(
        self,
        tenant_id: UUID,
        evidence_id: UUID | str,
        actor_id: str,
        replacement_data: Mapping[str, Any],
        transition_key: str,
    ) -> ComplianceEvidence:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        with transaction.atomic():
            original = ComplianceEvidence.objects.select_for_update().get(pk=self.get_evidence(tenant, evidence_id).pk)
            if original.status != ComplianceEvidenceStatus.FINALIZED:
                raise DomainConflictError("evidence_not_finalized", "Only finalized evidence can be superseded.")
            values = dict(replacement_data)
            values["asset_id"] = original.asset_id
            values["supersedes_id"] = original.id
            replacement = self.create_draft(tenant, actor, values)
            replacement = self.finalize(tenant, replacement.id, actor, f"{transition_key}:replacement")
            _transition(EVIDENCE_MACHINE, original, "supersede", transition_key, actor, replacement_id=str(replacement.id))
            return replacement

    def verify_evidence(
        self, tenant_id: UUID, evidence_id: UUID | str, actor_id: str, idempotency_key: str
    ) -> VerificationAttempt:
        started = time.perf_counter()
        evidence = self.get_evidence(tenant_id, evidence_id)
        computed = sha256_hex(canonical_json(self._content_document(evidence)))
        proof = {
            "computed_content_hash": computed,
            "stored_content_hash": evidence.content_hash,
            "status": evidence.status,
            "valid_until": evidence.valid_until.isoformat() if evidence.valid_until else None,
        }
        if evidence.status == ComplianceEvidenceStatus.DRAFT:
            outcome, reason = VerificationOutcome.INCONCLUSIVE, "EVIDENCE_NOT_FINALIZED"
        elif computed != evidence.content_hash:
            outcome, reason = VerificationOutcome.INVALID, "CONTENT_HASH_MISMATCH"
        elif evidence.valid_until is not None and evidence.valid_until <= timezone.now():
            outcome, reason = VerificationOutcome.INVALID, "EVIDENCE_EXPIRED"
        elif evidence.status == ComplianceEvidenceStatus.SUPERSEDED:
            outcome, reason = VerificationOutcome.INVALID, "EVIDENCE_SUPERSEDED"
        else:
            outcome, reason = VerificationOutcome.VERIFIED, "EVIDENCE_VALID"
        return VerificationService().record_attempt(
            evidence.tenant_id,
            {
                "verification_type": VerificationType.COMPLIANCE,
                "asset": evidence.asset,
                "compliance_evidence": evidence,
                "idempotency_key": idempotency_key,
                "outcome": outcome,
                "reason_code": reason,
                "chain_head_hash": evidence.asset.head_hash,
                "proof_evidence": proof,
                "actor_id": _actor(actor_id),
                "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
            },
        )

"""Transactional business services for tenant-safe product traceability."""

from __future__ import annotations

import hmac
import json
import logging
import random
import secrets
import threading
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
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
from src.core.state_machine import StateMachine, StateMachineError, Transition, TransitionRecord

from . import metrics
from .hashing import canonical_json, compute_event_hash, compute_merkle_root, normalize_utc_timestamp, sha256_hex
from .models import (
    AuthenticityCredential,
    AuthenticityCredentialStatus,
    BlockchainTraceabilityConfiguration,
    BlockchainTraceabilityConfigurationAudit,
    BlockchainTraceabilityConfigurationVersion,
    ComplianceEvidence,
    ComplianceEvidenceStatus,
    CredentialIssuanceSagaEvent,
    LedgerAnchor,
    LedgerAnchorStatus,
    LedgerNetwork,
    LedgerNetworkStatus,
    LifecycleTransition,
    MutationIdempotencyRecord,
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


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "validation": {
        "max_json_bytes": 262144,
        "max_json_depth": 20,
        "max_json_keys": 1000,
        "gtin_lengths": [8, 12, 13, 14],
        "max_revocation_reason_chars": 2000,
        "max_authenticity_token_chars": 4096,
        "max_actor_id_chars": 255,
        "credential_type_max_chars": 64,
    },
    "network_policy": {"default_confirmation_depth": 1, "max_confirmation_depth": 65535},
    "schema_policy": {"default_version": 1, "allowed_versions": [1]},
    "list_policy": {
        "default_page_size": 25,
        "max_page_size": 100,
        "history_chunk_size": 100,
        "verification_chunk_size": 500,
    },
    "health_policy": {
        "provider_probe_cache_ttl_seconds": 30,
        "outbox_freshness_seconds": 300,
        "cache_marker_ttl_seconds": 10,
    },
    "inventory_policy": {"validation_required": True},
    "anchor_policy": {"default_start_sequence": 1, "use_current_head_default": True},
    "credential_policy": {"issuer_type": "django_signing_v1", "token_entropy_bytes": 32},
    "resilience": {
        "timeout_seconds": 10.0,
        "max_attempts": 3,
        "base_backoff_seconds": 0.05,
        "max_backoff_seconds": 1.0,
        "circuit_failure_threshold": 5,
        "circuit_recovery_seconds": 30,
    },
    "workflow": {
        "machines": {
            "network": {
                "states": ["draft", "active", "degraded", "disabled"],
                "terminal_states": [],
                "transitions": [
                    ["activate", "draft", "active"],
                    ["activate", "disabled", "active"],
                    ["mark_degraded", "active", "degraded"],
                    ["restore", "degraded", "active"],
                    ["disable", "draft", "disabled"],
                    ["disable", "active", "disabled"],
                    ["disable", "degraded", "disabled"],
                ],
            },
            "asset": {
                "states": ["draft", "active", "recalled", "retired"],
                "terminal_states": ["retired"],
                "transitions": [
                    ["activate", "draft", "active"],
                    ["recall", "active", "recalled"],
                    ["release_recall", "recalled", "active"],
                    ["retire", "draft", "retired"],
                    ["retire", "active", "retired"],
                    ["retire", "recalled", "retired"],
                ],
            },
            "anchor": {
                "states": ["queued", "submitting", "submitted", "confirmed", "failed"],
                "terminal_states": ["confirmed"],
                "transitions": [
                    ["start_submission", "queued", "submitting"],
                    ["accept_submission", "submitting", "submitted"],
                    ["confirm", "submitted", "confirmed"],
                    ["fail", "submitting", "failed"],
                    ["fail", "submitted", "failed"],
                    ["retry", "failed", "queued"],
                ],
            },
            "credential": {
                "states": ["active", "revoked", "expired"],
                "terminal_states": ["revoked", "expired"],
                "transitions": [["revoke", "active", "revoked"], ["expire", "active", "expired"]],
            },
            "compliance_evidence": {
                "states": ["draft", "finalized", "superseded"],
                "terminal_states": ["superseded"],
                "transitions": [["finalize", "draft", "finalized"], ["supersede", "finalized", "superseded"]],
            },
        },
        "network_deletable_statuses": ["draft", "disabled"],
        "asset_deletable_statuses": ["draft"],
    },
    "ui": {
        "sidebar_order": 400,
        "positive_statuses": ["active", "confirmed", "verified", "finalized", "healthy"],
        "warning_statuses": ["queued", "submitting", "submitted", "degraded", "warning", "inconclusive"],
        "default_recall_reason": "Recall confirmed in traceability workspace",
        "default_revocation_reason": "Revoked from traceability workspace",
    },
    "features": {
        "enabled": True,
        "roles": ["tenant_admin"],
        "cohorts": [],
        "enable_supersede": True,
        "enable_health": True,
    },
}


def _configuration_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


class BlockchainTraceabilityConfigurationService:
    """Validate, version and audit tenant configuration as one atomic document."""

    SECTIONS = frozenset(DEFAULT_CONFIGURATION)

    @staticmethod
    def _integer(section: Mapping[str, Any], key: str, minimum: int, maximum: int) -> int:
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise BlockchainTraceabilityError(
                "invalid_configuration", f"{key} must be between {minimum} and {maximum}.", status_code=400
            )
        return value

    @classmethod
    def validate_document(cls, document: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(document, Mapping) or set(document) != cls.SECTIONS:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "Configuration must contain exactly the declared sections.", status_code=400
            )
        result = _configuration_copy(document)
        if any(not isinstance(result[section], Mapping) for section in cls.SECTIONS):
            raise BlockchainTraceabilityError(
                "invalid_configuration", "Every configuration section must be an object.", status_code=400
            )
        validation = result["validation"]
        if not isinstance(validation, Mapping):
            raise BlockchainTraceabilityError("invalid_configuration", "validation must be an object.", status_code=400)
        cls._integer(validation, "max_json_bytes", 1024, 1048576)
        cls._integer(validation, "max_json_depth", 1, 50)
        cls._integer(validation, "max_json_keys", 1, 10000)
        cls._integer(validation, "max_revocation_reason_chars", 1, 10000)
        cls._integer(validation, "max_authenticity_token_chars", 256, 16384)
        cls._integer(validation, "max_actor_id_chars", 32, 1024)
        cls._integer(validation, "credential_type_max_chars", 16, 255)
        gtin_lengths = validation.get("gtin_lengths")
        if not isinstance(gtin_lengths, list) or not gtin_lengths or not set(gtin_lengths) <= {8, 12, 13, 14}:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "gtin_lengths is not a safe allow-list.", status_code=400
            )

        network = result["network_policy"]
        maximum_depth = cls._integer(network, "max_confirmation_depth", 1, 65535)
        default_depth = cls._integer(network, "default_confirmation_depth", 1, maximum_depth)
        if default_depth > maximum_depth:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "Default confirmation depth exceeds its limit.", status_code=400
            )

        schema = result["schema_policy"]
        versions = schema.get("allowed_versions") if isinstance(schema, Mapping) else None
        if (
            not isinstance(versions, list)
            or not versions
            or any(isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 65535 for item in versions)
        ):
            raise BlockchainTraceabilityError("invalid_configuration", "allowed_versions is invalid.", status_code=400)
        if schema.get("default_version") not in versions:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "default_version must be allowed.", status_code=400
            )

        listing = result["list_policy"]
        maximum_page = cls._integer(listing, "max_page_size", 1, 500)
        if cls._integer(listing, "default_page_size", 1, maximum_page) > maximum_page:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "Default page size exceeds its limit.", status_code=400
            )
        cls._integer(listing, "history_chunk_size", 1, 5000)
        cls._integer(listing, "verification_chunk_size", 1, 5000)

        health = result["health_policy"]
        for key in ("provider_probe_cache_ttl_seconds", "outbox_freshness_seconds", "cache_marker_ttl_seconds"):
            cls._integer(health, key, 1, 86400)
        inventory = result["inventory_policy"]
        if not isinstance(inventory, Mapping) or not isinstance(inventory.get("validation_required"), bool):
            raise BlockchainTraceabilityError("invalid_configuration", "Inventory policy is invalid.", status_code=400)
        anchor = result["anchor_policy"]
        cls._integer(anchor, "default_start_sequence", 1, 18446744073709551615)
        if not isinstance(anchor.get("use_current_head_default"), bool):
            raise BlockchainTraceabilityError("invalid_configuration", "Anchor policy is invalid.", status_code=400)
        credential = result["credential_policy"]
        if not isinstance(credential.get("issuer_type"), str) or not credential["issuer_type"].strip():
            raise BlockchainTraceabilityError("invalid_configuration", "issuer_type is required.", status_code=400)
        cls._integer(credential, "token_entropy_bytes", 32, 128)

        resilience = result["resilience"]
        cls._integer(resilience, "max_attempts", 1, 10)
        cls._integer(resilience, "circuit_failure_threshold", 1, 100)
        cls._integer(resilience, "circuit_recovery_seconds", 1, 3600)
        for key, minimum, maximum in (
            ("timeout_seconds", 0.1, 120.0),
            ("base_backoff_seconds", 0.0, 10.0),
            ("max_backoff_seconds", 0.0, 60.0),
        ):
            value = resilience.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= float(value) <= maximum:
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"{key} is outside safe limits.", status_code=400
                )
        if float(resilience["base_backoff_seconds"]) > float(resilience["max_backoff_seconds"]):
            raise BlockchainTraceabilityError(
                "invalid_configuration", "Backoff limits are inconsistent.", status_code=400
            )

        workflow = result["workflow"]
        machines = workflow.get("machines") if isinstance(workflow, Mapping) else None
        if not isinstance(machines, Mapping) or set(machines) != {
            "network",
            "asset",
            "anchor",
            "credential",
            "compliance_evidence",
        }:
            raise BlockchainTraceabilityError(
                "invalid_configuration", "All workflow machines are required.", status_code=400
            )
        machine_states = {
            "network": set(LedgerNetworkStatus.values),
            "asset": set(TraceabilityAssetStatus.values),
            "anchor": set(LedgerAnchorStatus.values),
            "credential": set(AuthenticityCredentialStatus.values),
            "compliance_evidence": set(ComplianceEvidenceStatus.values),
        }
        for name, definition in machines.items():
            if not isinstance(definition, Mapping) or not isinstance(definition.get("states"), list):
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"Workflow {name} is invalid.", status_code=400
                )
            states = set(definition["states"])
            if states != machine_states[name]:
                raise BlockchainTraceabilityError(
                    "invalid_configuration",
                    f"Workflow {name} states must match the domain allow-list.",
                    status_code=400,
                )
            terminal_states = definition.get("terminal_states")
            if not isinstance(terminal_states, list) or not set(terminal_states) <= states:
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"Workflow {name} terminal states are invalid.", status_code=400
                )
            transitions = definition.get("transitions")
            if not states or not isinstance(transitions, list) or not transitions:
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"Workflow {name} is incomplete.", status_code=400
                )
            for edge in transitions:
                if not isinstance(edge, list) or len(edge) != 3 or edge[1] not in states or edge[2] not in states:
                    raise BlockchainTraceabilityError(
                        "invalid_configuration", f"Workflow {name} has an invalid edge.", status_code=400
                    )
        for key, allowed in (
            ("network_deletable_statuses", set(LedgerNetworkStatus.values)),
            ("asset_deletable_statuses", set(TraceabilityAssetStatus.values)),
        ):
            values = workflow.get(key)
            if not isinstance(values, list) or not values or not set(values) <= allowed:
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"{key} is not a safe allow-list.", status_code=400
                )

        ui = result["ui"]
        cls._integer(ui, "sidebar_order", 0, 10000)
        presentation_statuses = set().union(*machine_states.values()) | {
            "verified",
            "healthy",
            "warning",
            "inconclusive",
            "invalid",
            "unavailable",
        }
        for key in ("positive_statuses", "warning_statuses"):
            if not isinstance(ui.get(key), list) or not ui[key] or not set(ui[key]) <= presentation_statuses:
                raise BlockchainTraceabilityError("invalid_configuration", f"{key} is invalid.", status_code=400)
        for key in ("default_recall_reason", "default_revocation_reason"):
            if not isinstance(ui.get(key), str):
                raise BlockchainTraceabilityError("invalid_configuration", f"{key} is invalid.", status_code=400)
        features = result["features"]
        for key in ("enabled", "enable_supersede", "enable_health"):
            if not isinstance(features.get(key), bool):
                raise BlockchainTraceabilityError("invalid_configuration", f"{key} must be boolean.", status_code=400)
        for key in ("roles", "cohorts"):
            if not isinstance(features.get(key), list) or not all(
                isinstance(item, str) and 0 < len(item) <= 128 and item.replace("-", "").replace("_", "").isalnum()
                for item in features[key]
            ):
                raise BlockchainTraceabilityError(
                    "invalid_configuration", f"{key} must be a string list.", status_code=400
                )
        return result

    @staticmethod
    def _environment(value: object) -> str:
        environment = str(value or "default").strip().lower()
        if (
            not environment
            or len(environment) > 64
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in environment)
        ):
            raise BlockchainTraceabilityError("invalid_environment", "Environment name is invalid.", status_code=400)
        return environment

    def current(self, tenant_id: UUID, environment: str = "default") -> BlockchainTraceabilityConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        env = self._environment(environment)
        try:
            return BlockchainTraceabilityConfiguration.objects.get(tenant_id=tenant, environment=env)
        except BlockchainTraceabilityConfiguration.DoesNotExist:
            return self._create_default(tenant, env)

    def _create_default(self, tenant: UUID, environment: str) -> BlockchainTraceabilityConfiguration:
        document = self.validate_document(DEFAULT_CONFIGURATION)
        correlation_id = _correlation()
        try:
            with transaction.atomic():
                existing = (
                    BlockchainTraceabilityConfiguration.objects.select_for_update()
                    .filter(tenant_id=tenant, environment=environment)
                    .first()
                )
                if existing is not None:
                    return existing
                current = BlockchainTraceabilityConfiguration.objects.create(
                    tenant_id=tenant,
                    environment=environment,
                    version=1,
                    document=document,
                    created_by="system:configuration-default",
                    updated_by="system:configuration-default",
                )
                self._record_revision(current, {}, "system:configuration-default", correlation_id, "initialize")
                return current
        except IntegrityError:
            # Concurrent first reads race on the tenant/environment unique key.
            # The losing transaction is fully rolled back, then reuses the one
            # complete revision created by the winner.
            return BlockchainTraceabilityConfiguration.objects.get(tenant_id=tenant, environment=environment)

    @staticmethod
    def _record_revision(
        current: BlockchainTraceabilityConfiguration,
        before: Mapping[str, Any],
        actor: str,
        correlation_id: str,
        action: str,
    ) -> None:
        BlockchainTraceabilityConfigurationVersion.objects.create(
            tenant_id=current.tenant_id,
            environment=current.environment,
            version=current.version,
            document=current.document,
            created_by=actor,
            correlation_id=correlation_id,
            change_type=action,
        )
        BlockchainTraceabilityConfigurationAudit.objects.create(
            tenant_id=current.tenant_id,
            environment=current.environment,
            from_version=current.version - 1 if current.version > 1 else None,
            to_version=current.version,
            before=dict(before),
            after=current.document,
            changed_by=actor,
            correlation_id=correlation_id,
            action=action,
        )

    def update(
        self,
        tenant_id: UUID,
        actor_id: str,
        document: Mapping[str, Any],
        environment: str = "default",
        *,
        action: str = "update",
    ) -> BlockchainTraceabilityConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id, tenant)
        validated = self.validate_document(document)
        with transaction.atomic():
            current = self.current(tenant, environment)
            current = BlockchainTraceabilityConfiguration.objects.select_for_update().get(pk=current.pk)
            before = _configuration_copy(current.document)
            if before == validated:
                return current
            current.version += 1
            current.document = validated
            current.updated_by = actor
            current.save(update_fields=["version", "document", "updated_by", "updated_at"])
            self._record_revision(current, before, actor, _correlation(), action)
            return current

    def history(
        self, tenant_id: UUID, environment: str = "default"
    ) -> QuerySet[BlockchainTraceabilityConfigurationVersion]:
        return BlockchainTraceabilityConfigurationVersion.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), environment=self._environment(environment)
        ).order_by("-version")

    def rollback(
        self, tenant_id: UUID, actor_id: str, version: int, environment: str = "default"
    ) -> BlockchainTraceabilityConfiguration:
        try:
            target = self.history(tenant_id, environment).get(version=version)
        except BlockchainTraceabilityConfigurationVersion.DoesNotExist as exc:
            raise DomainNotFoundError("configuration version") from exc
        return self.update(tenant_id, actor_id, target.document, environment, action="rollback")

    def preview(self, tenant_id: UUID, document: Mapping[str, Any], environment: str = "default") -> dict[str, Any]:
        validated = self.validate_document(document)
        current = self.current(tenant_id, environment)
        changes: list[dict[str, Any]] = []

        def compare(before: Any, after: Any, path: str) -> None:
            if isinstance(before, Mapping) and isinstance(after, Mapping):
                for key in sorted(set(before) | set(after)):
                    compare(before.get(key), after.get(key), f"{path}.{key}" if path else str(key))
            elif before != after:
                changes.append({"path": path, "before": before, "after": after})

        compare(current.document, validated, "")
        return {"valid": True, "changes": changes, "document": validated}

    def export_document(self, tenant_id: UUID, environment: str = "default") -> dict[str, Any]:
        current = self.current(tenant_id, environment)
        return {
            "schema": "saraise.blockchain_traceability.configuration/v1",
            "environment": current.environment,
            "version": current.version,
            "document": _configuration_copy(current.document),
        }

    def import_document(
        self, tenant_id: UUID, actor_id: str, payload: Mapping[str, Any], environment: str = "default"
    ) -> BlockchainTraceabilityConfiguration:
        if not isinstance(payload, Mapping) or set(payload) - {"schema", "environment", "version", "document"}:
            raise BlockchainTraceabilityError(
                "invalid_configuration_import", "Import document is invalid.", status_code=400
            )
        document = payload.get("document")
        if not isinstance(document, Mapping):
            raise BlockchainTraceabilityError(
                "invalid_configuration_import", "Import document is missing configuration.", status_code=400
            )
        return self.update(tenant_id, actor_id, document, environment, action="import")

    def document(self, tenant_id: UUID, environment: str = "default") -> dict[str, Any]:
        return _configuration_copy(self.current(tenant_id, environment).document)


_PROVIDER_CIRCUITS: dict[tuple[UUID, str], tuple[int, float | None]] = {}
_PROVIDER_CIRCUIT_LOCK = threading.Lock()


def execute_resilient_provider_call(tenant_id: UUID, capability: str, operation: Any) -> Any:
    """Execute one provider operation with tenant policy, timeout, jittered retry and circuit breaking."""

    tenant = _uuid(tenant_id, "tenant_id")
    policy = BlockchainTraceabilityConfigurationService().document(tenant)["resilience"]
    timeout_seconds = float(policy["timeout_seconds"])
    attempts = int(policy["max_attempts"])
    failure_threshold = int(policy["circuit_failure_threshold"])
    recovery_seconds = float(policy["circuit_recovery_seconds"])
    circuit_key = (tenant, capability)
    now = time.monotonic()
    with _PROVIDER_CIRCUIT_LOCK:
        failures, opened_at = _PROVIDER_CIRCUITS.get(circuit_key, (0, None))
        if opened_at is not None and now - opened_at < recovery_seconds:
            raise ProviderCircuitOpenError(f"Provider circuit for {capability} is open.")
        if opened_at is not None:
            _PROVIDER_CIRCUITS[circuit_key] = (0, None)

    last_error: ProviderUnavailableError | None = None
    for attempt in range(attempts):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bct-provider")
        future = executor.submit(operation)
        try:
            value = future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            last_error = ProviderTimeoutError(f"Provider call {capability} exceeded its configured deadline.")
        except ProviderUnavailableError as exc:
            last_error = exc
        else:
            with _PROVIDER_CIRCUIT_LOCK:
                _PROVIDER_CIRCUITS[circuit_key] = (0, None)
            executor.shutdown(wait=False, cancel_futures=True)
            return value
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        with _PROVIDER_CIRCUIT_LOCK:
            failures, _opened = _PROVIDER_CIRCUITS.get(circuit_key, (0, None))
            failures += 1
            opened_at = time.monotonic() if failures >= failure_threshold else None
            _PROVIDER_CIRCUITS[circuit_key] = (failures, opened_at)
        if opened_at is not None:
            raise ProviderCircuitOpenError(f"Provider circuit for {capability} opened.") from last_error
        if attempt + 1 < attempts:
            ceiling = min(
                float(policy["max_backoff_seconds"]),
                float(policy["base_backoff_seconds"]) * (2**attempt),
            )
            time.sleep(random.uniform(0.0, ceiling))
    if last_error is None:
        raise ProviderUnavailableError(f"Provider call {capability} failed without evidence.")
    raise last_error


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


class LifecycleTransitionRecorder:
    """State-machine recorder backed by an append-only tenant table."""

    def find(self, aggregate: Any, transition_key: str) -> TransitionRecord | None:
        row = LifecycleTransition.objects.filter(
            tenant_id=aggregate.tenant_id,
            aggregate_type=aggregate._meta.model_name,
            aggregate_id=aggregate.pk,
            transition_key=transition_key,
        ).first()
        if row is None:
            return None
        metadata = dict(row.metadata)
        metadata.update({"actor_id": row.actor_id, "correlation_id": row.correlation_id})
        if row.reason:
            metadata["reason"] = row.reason
        return TransitionRecord(
            transition_key=row.transition_key,
            command=row.command,
            from_state=row.from_state,
            to_state=row.to_state,
            occurred_at=row.occurred_at.isoformat(),
            metadata=metadata,
        )

    def record(self, aggregate: Any, record: TransitionRecord) -> None:
        metadata = dict(record.metadata)
        actor_id = str(metadata.pop("actor_id", ""))
        correlation_id = str(metadata.pop("correlation_id", ""))
        reason = str(metadata.pop("reason", ""))
        transition = LifecycleTransition.objects.create(
            tenant_id=aggregate.tenant_id,
            aggregate_type=aggregate._meta.model_name,
            aggregate_id=aggregate.pk,
            transition_key=record.transition_key,
            command=record.command,
            from_state=record.from_state,
            to_state=record.to_state,
            actor_id=actor_id,
            correlation_id=correlation_id,
            reason=reason,
            metadata=metadata,
            occurred_at=datetime.fromisoformat(record.occurred_at),
        )
        logger.info(
            "Lifecycle transition recorded",
            extra={
                "tenant_id": str(aggregate.tenant_id),
                "actor_id": actor_id,
                "correlation_id": correlation_id,
                "transition_id": str(transition.id),
                "aggregate_type": aggregate._meta.model_name,
                "aggregate_id": str(aggregate.pk),
                "command": record.command,
            },
        )

    def aggregate_update_fields(self) -> tuple[str, ...]:
        return ()


_MACHINE_MODELS: dict[str, type[Any]] = {
    "network": LedgerNetwork,
    "asset": TraceabilityAsset,
    "anchor": LedgerAnchor,
    "credential": AuthenticityCredential,
    "compliance_evidence": ComplianceEvidence,
}


def _configured_machine(tenant_id: UUID, machine_name: str) -> StateMachine[Any]:
    document = BlockchainTraceabilityConfigurationService().document(tenant_id)
    definition = document["workflow"]["machines"][machine_name]
    return StateMachine(
        name=f"blockchain_traceability.{machine_name}",
        model=_MACHINE_MODELS[machine_name],
        states=definition["states"],
        terminal_states=definition["terminal_states"],
        transitions=tuple(Transition(*edge) for edge in definition["transitions"]),
        recorder=LifecycleTransitionRecorder(),
    )


def _uuid(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BlockchainTraceabilityError(
            "validation_error", f"{field_name} must be a valid UUID.", status_code=400
        ) from exc


def _actor(value: object, tenant_id: UUID | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlockchainTraceabilityError("validation_error", "actor_id is required.", status_code=400)
    normalized = value.strip()
    maximum = 1024
    if tenant_id is not None:
        maximum = int(
            BlockchainTraceabilityConfigurationService().document(tenant_id)["validation"]["max_actor_id_chars"]
        )
    if len(normalized) > maximum:
        raise BlockchainTraceabilityError(
            "validation_error", f"actor_id exceeds the configured {maximum} character limit.", status_code=400
        )
    return normalized


def _correlation() -> str:
    return get_correlation_id() or str(uuid.uuid4())


def _data(
    value: Mapping[str, Any] | dict[str, Any], *, allowed: set[str], required: set[str] = frozenset()
) -> dict[str, Any]:
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
    return BlockchainTraceabilityError(
        "validation_error", "The traceability data is invalid.", status_code=400, detail=detail
    )


def _transition(
    machine_name: str, aggregate: Any, command: str, transition_key: str, actor_id: str, **metadata: Any
) -> Any:
    try:
        return _configured_machine(aggregate.tenant_id, machine_name).apply(
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


def _mutation_fingerprint(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256_hex(encoded)


def _mutation_replay(
    tenant_id: UUID,
    operation: str,
    idempotency_key: str,
    values: Mapping[str, Any],
    model: type[Any],
) -> Any | None:
    record = MutationIdempotencyRecord.objects.filter(
        tenant_id=tenant_id, operation=operation, idempotency_key=idempotency_key
    ).first()
    if record is None:
        return None
    if not hmac.compare_digest(record.request_fingerprint, _mutation_fingerprint(values)):
        raise IdempotencyConflictError()
    try:
        return model._base_manager.get(tenant_id=tenant_id, id=record.resource_id)
    except model.DoesNotExist as exc:
        raise DomainConflictError("idempotency_result_missing", "The prior idempotent result is unavailable.") from exc


def _record_mutation(
    tenant_id: UUID,
    operation: str,
    idempotency_key: str,
    values: Mapping[str, Any],
    resource: Any,
) -> None:
    MutationIdempotencyRecord.objects.create(
        tenant_id=tenant_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_fingerprint=_mutation_fingerprint(values),
        resource_type=resource._meta.model_name,
        resource_id=resource.pk,
        correlation_id=_correlation(),
    )


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
        actor = _actor(actor_id, tenant)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"network_key", "name", "provider_type", "dependency_key", "network_namespace"},
        )
        policy = BlockchainTraceabilityConfigurationService().document(tenant)["network_policy"]
        values.setdefault("confirmation_depth", policy["default_confirmation_depth"])
        if not 1 <= int(values["confirmation_depth"]) <= int(policy["max_confirmation_depth"]):
            raise BlockchainTraceabilityError(
                "validation_error", "Confirmation depth is outside the configured safe range.", status_code=400
            )
        idempotency_key = str(values["network_key"])
        replay = _mutation_replay(tenant, "network.create", idempotency_key, values, LedgerNetwork)
        if replay is not None:
            return replay
        try:
            adapter = get_ledger_provider(str(values["provider_type"]))
            options = values.get("provider_options", {})
            if not isinstance(options, Mapping):
                raise BlockchainTraceabilityError(
                    "validation_error", "provider_options must be an object.", status_code=400
                )
            adapter.validate_options(options)
            with transaction.atomic():
                network = LedgerNetwork(tenant_id=tenant, created_by=actor, **values)
                network.save()
                _record_mutation(tenant, "network.create", idempotency_key, values, network)
                _emit_domain_event(
                    tenant,
                    "ledger_network",
                    network.id,
                    "blockchain_traceability.network.created",
                    {"network_id": str(network.id), "network_key": network.network_key, "actor_id": actor},
                )
            logger.info(
                "Ledger network created",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": actor,
                    "network_id": str(network.id),
                    "correlation_id": _correlation(),
                },
            )
            return network
        except AdapterNotRegisteredError as exc:
            raise DependencyUnavailableError("ledger_provider") from exc
        except BlockchainTraceabilityError:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise (
                _model_error(exc)
                if isinstance(exc, ValidationError)
                else BlockchainTraceabilityError(
                    "invalid_provider_options", "Provider options are invalid.", status_code=400
                )
            ) from exc

    def get_network(self, tenant_id: UUID, network_id: UUID | str) -> LedgerNetwork:
        try:
            return LedgerNetwork.objects.get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(network_id, "network_id"), is_deleted=False
            )
        except LedgerNetwork.DoesNotExist as exc:
            raise DomainNotFoundError("ledger network") from exc

    def list_networks(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[LedgerNetwork]:
        queryset = LedgerNetwork.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False)
        for key in ("status", "provider_type"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        return queryset.order_by("name", "id")

    def update_network(
        self, tenant_id: UUID, network_id: UUID | str, actor_id: str, data: Mapping[str, Any]
    ) -> LedgerNetwork:
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        values = _data(data, allowed=self.UPDATE_FIELDS)
        with transaction.atomic():
            network = LedgerNetwork.objects.select_for_update().get(pk=self.get_network(tenant_id, network_id).pk)
            operational = self.UPDATE_FIELDS - {"name", "description"}
            if network.status in {LedgerNetworkStatus.ACTIVE, LedgerNetworkStatus.DEGRADED} and operational & set(
                values
            ):
                raise DomainConflictError(
                    "network_active", "Disable the network before changing provider configuration."
                )
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        with transaction.atomic():
            network = LedgerNetwork.objects.select_for_update().get(pk=self.get_network(tenant_id, network_id).pk)
            allowed = set(
                BlockchainTraceabilityConfigurationService().document(tenant_id)["workflow"][
                    "network_deletable_statuses"
                ]
            )
            if network.status not in allowed or network.anchors.exists():
                raise DomainConflictError("network_in_use", "The configured retention policy forbids deletion.")
            network.is_deleted = True
            network.deleted_at = timezone.now()
            network.deleted_by = actor
            network.updated_by = actor
            network.save()

    def probe_network(self, tenant_id: UUID, network_id: UUID | str, actor_id: str) -> OperationResult[ProviderHealth]:
        _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        network = self.get_network(tenant_id, network_id)
        now = timezone.now()
        try:
            adapter = get_ledger_provider(network.provider_type)
            health = execute_resilient_provider_call(
                network.tenant_id, "network_probe", lambda: adapter.health(network)
            )
            if not isinstance(health, ProviderHealth):
                raise InvalidProviderResponseError("provider returned invalid health evidence")
        except (AdapterNotRegisteredError, ProviderUnavailableError) as exc:
            metrics.PROVIDER_UNAVAILABLE.labels(capability="network_probe").inc()
            network.last_health_status = "unavailable"
            network.last_health_code = "PROVIDER_UNAVAILABLE"
            network.last_health_checked_at = now
            network.save(
                update_fields=["last_health_status", "last_health_code", "last_health_checked_at", "updated_at"]
            )
            return OperationResult.unavailable(
                capability="ledger_provider", provider=network.provider_type, evidence={"network_id": str(network.id)}
            )
        except ProviderError:
            network.last_health_status = "failed"
            network.last_health_code = "INVALID_PROVIDER_RESPONSE"
            network.last_health_checked_at = now
            network.save(
                update_fields=["last_health_status", "last_health_code", "last_health_checked_at", "updated_at"]
            )
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        network = self.get_network(tenant_id, network_id)
        result = self.probe_network(tenant_id, network_id, actor)
        if result.status != "succeeded" or result.value is None or not result.value.available:
            raise result.to_exception()
        return _transition("network", network, "activate", transition_key, actor)

    def disable_network(
        self, tenant_id: UUID, network_id: UUID | str, actor_id: str, transition_key: str
    ) -> LedgerNetwork:
        return _transition(
            "network",
            self.get_network(tenant_id, network_id),
            "disable",
            transition_key,
            _actor(actor_id, _uuid(tenant_id, "tenant_id")),
        )


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
        if not product_ref and not batch_ref:
            return
        policy = BlockchainTraceabilityConfigurationService().document(tenant_id)["inventory_policy"]
        resolver = self.inventory_resolver
        if resolver is None:
            try:
                resolver = get_inventory_resolver()
            except AdapterNotRegisteredError as exc:
                if bool(policy["validation_required"]):
                    raise DependencyUnavailableError(
                        "inventory_reference",
                        "Inventory reference validation is required but no resolver is registered.",
                    ) from exc
                return
        try:
            result = execute_resilient_provider_call(
                tenant_id,
                "inventory_reference",
                lambda: resolver.validate_reference(tenant_id, product_ref, batch_ref),
            )
        except ProviderUnavailableError as exc:
            raise DependencyUnavailableError("inventory_reference") from exc
        if not result.valid:
            raise BlockchainTraceabilityError(
                "invalid_inventory_reference", "The inventory reference is not valid for this tenant.", status_code=400
            )

    def register_asset(self, tenant_id: UUID, actor_id: str, data: Mapping[str, Any]) -> TraceabilityAsset:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id, tenant)
        values = _data(data, allowed=self.CREATE_FIELDS, required={"asset_key", "name", "asset_type"})
        validation = BlockchainTraceabilityConfigurationService().document(tenant)["validation"]
        gtin = str(values.get("gtin", ""))
        if gtin and (not gtin.isdigit() or len(gtin) not in set(validation["gtin_lengths"])):
            raise BlockchainTraceabilityError(
                "validation_error", "GTIN is not permitted by the tenant identifier policy.", status_code=400
            )
        idempotency_key = str(values["asset_key"])
        replay = _mutation_replay(tenant, "asset.register", idempotency_key, values, TraceabilityAsset)
        if replay is not None:
            return replay
        self._validate_inventory(tenant, str(values.get("product_ref", "")), str(values.get("batch_ref", "")))
        try:
            with transaction.atomic():
                asset = TraceabilityAsset(tenant_id=tenant, created_by=actor, **values)
                asset.save()
                _record_mutation(tenant, "asset.register", idempotency_key, values, asset)
                _emit_domain_event(
                    tenant,
                    "traceability_asset",
                    asset.id,
                    "blockchain_traceability.asset.registered",
                    {"asset_id": str(asset.id), "asset_key": asset.asset_key, "actor_id": actor},
                )
            logger.info(
                "Traceability asset registered",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": actor,
                    "asset_id": str(asset.id),
                    "correlation_id": _correlation(),
                },
            )
            return asset
        except ValidationError as exc:
            raise _model_error(exc) from exc

    def get_asset(self, tenant_id: UUID, asset_id: UUID | str) -> TraceabilityAsset:
        try:
            return TraceabilityAsset.objects.get(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(asset_id, "asset_id"), is_deleted=False
            )
        except TraceabilityAsset.DoesNotExist as exc:
            raise DomainNotFoundError("traceability asset") from exc

    def list_assets(self, tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[TraceabilityAsset]:
        queryset = TraceabilityAsset.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False)
        for key in ("status", "product_ref", "batch_ref", "serial_number", "gtin", "asset_type"):
            if filters and filters.get(key) not in (None, ""):
                queryset = queryset.filter(**{key: filters[key]})
        return queryset.order_by("-created_at", "id")

    def update_asset(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, data: Mapping[str, Any]
    ) -> TraceabilityAsset:
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        with transaction.atomic():
            asset = TraceabilityAsset.objects.select_for_update().get(pk=self.get_asset(tenant_id, asset_id).pk)
            has_evidence = (
                asset.events.exists()
                or asset.anchors.exists()
                or asset.credentials.exists()
                or asset.compliance_evidence.filter(status=ComplianceEvidenceStatus.FINALIZED).exists()
            )
            allowed = set(
                BlockchainTraceabilityConfigurationService().document(tenant_id)["workflow"]["asset_deletable_statuses"]
            )
            if asset.status not in allowed or has_evidence:
                raise DomainConflictError("asset_has_evidence", "The configured retention policy forbids deletion.")
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
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
            asset = _transition("asset", asset, command, transition_key, actor, **metadata)
            _emit_domain_event(
                asset.tenant_id,
                "traceability_asset",
                asset.id,
                "blockchain_traceability.asset.transitioned",
                {"asset_id": str(asset.id), "command": command, "status": asset.status, "actor_id": actor},
            )
            return asset

    def activate_asset(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, transition_key: str
    ) -> TraceabilityAsset:
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

    def retire_asset(
        self, tenant_id: UUID, asset_id: UUID | str, actor_id: str, transition_key: str
    ) -> TraceabilityAsset:
        return self._asset_transition(tenant_id, asset_id, actor_id, "retire", transition_key)

    def product_history(self, tenant_id: UUID, asset_id: UUID | str, page: int, page_size: int) -> AssetHistory:
        asset = self.get_asset(tenant_id, asset_id)
        policy = BlockchainTraceabilityConfigurationService().document(tenant_id)["list_policy"]
        if page < 1 or page_size < 1 or page_size > int(policy["max_page_size"]):
            raise BlockchainTraceabilityError("validation_error", "Invalid history pagination.", status_code=400)
        chunk_size = int(policy["history_chunk_size"])
        items: list[AssetHistoryItem] = []
        for event in asset.events.all().iterator(chunk_size=chunk_size):
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
        for anchor in asset.anchors.all().iterator(chunk_size=chunk_size):
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
        for credential in asset.credentials.all().iterator(chunk_size=chunk_size):
            items.append(
                AssetHistoryItem(
                    kind="credential",
                    occurred_at=normalize_utc_timestamp(credential.issued_at),
                    identifier=credential.id,
                    credential={
                        "id": str(credential.id),
                        "public_id": credential.public_id,
                        "status": credential.status,
                    },
                )
            )
        for evidence in asset.compliance_evidence.filter(is_deleted=False).iterator(chunk_size=chunk_size):
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

    def history_payload(self, asset: TraceabilityAsset, history: AssetHistory) -> dict[str, Any]:
        """Assemble the public timeline DTO inside the domain service boundary."""

        tenant = asset.tenant_id
        items = tuple(history.items)
        ids = {
            kind: {item.identifier for item in items if item.kind == kind}
            for kind in ("event", "anchor", "credential", "compliance")
        }
        records: dict[str, Mapping[UUID, Any]] = {
            "event": TraceabilityEvent.objects.filter(tenant_id=tenant, id__in=ids["event"]).in_bulk(),
            "anchor": LedgerAnchor.objects.filter(tenant_id=tenant, id__in=ids["anchor"]).in_bulk(),
            "credential": AuthenticityCredential.objects.filter(tenant_id=tenant, id__in=ids["credential"]).in_bulk(),
            "compliance": ComplianceEvidence.objects.filter(tenant_id=tenant, id__in=ids["compliance"]).in_bulk(),
        }

        def event_dto(row: TraceabilityEvent) -> dict[str, Any]:
            return {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "asset_id": str(row.asset_id),
                "sequence": row.sequence,
                "event_type": row.event_type,
                "schema_version": row.schema_version,
                "occurred_at": row.occurred_at.isoformat(),
                "recorded_at": row.recorded_at.isoformat(),
                "actor_ref": row.actor_ref,
                "location": row.location,
                "payload": row.payload,
                "previous_hash": row.previous_hash,
                "event_hash": row.event_hash,
                "hash_algorithm": row.hash_algorithm,
                "correlation_id": row.correlation_id,
            }

        def evidence_dto(row: Any, kind: str) -> dict[str, Any]:
            if kind == "anchor":
                return {
                    "id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "asset_id": str(row.asset_id),
                    "network_id": str(row.network_id),
                    "start_sequence": row.start_sequence,
                    "end_sequence": row.end_sequence,
                    "root_hash": row.root_hash,
                    "status": row.status,
                    "provider_transaction_id": row.provider_transaction_id,
                    "transaction_hash": row.transaction_hash,
                    "block_number": row.block_number,
                    "block_hash": row.block_hash,
                    "confirmations": row.confirmations,
                    "created_at": row.created_at.isoformat(),
                }
            if kind == "credential":
                return {
                    "id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "asset_id": str(row.asset_id),
                    "public_id": row.public_id,
                    "credential_type": row.credential_type,
                    "status": row.status,
                    "issued_at": row.issued_at.isoformat(),
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
            return {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "asset_id": str(row.asset_id),
                "event_id": str(row.event_id) if row.event_id else None,
                "evidence_key": row.evidence_key,
                "evidence_type": row.evidence_type,
                "standard": row.standard,
                "jurisdiction": row.jurisdiction,
                "result": row.result,
                "status": row.status,
                "observed_at": row.observed_at.isoformat(),
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            }

        timeline: list[dict[str, Any]] = []
        for item in items:
            if item.kind not in records or item.identifier not in records[item.kind]:
                raise DomainConflictError("history_evidence_missing", "Referenced history evidence is unavailable.")
            row = records[item.kind][item.identifier]
            key = "evidence" if item.kind == "compliance" else item.kind
            sequence = item.sequence
            if sequence is None and item.kind == "anchor":
                sequence = row.end_sequence
            timeline.append(
                {
                    "kind": item.kind,
                    "occurred_at": item.occurred_at,
                    "sequence": sequence if isinstance(sequence, int) else 0,
                    key: event_dto(row) if item.kind == "event" else evidence_dto(row, item.kind),
                }
            )
        pagination = history.pagination
        policy = BlockchainTraceabilityConfigurationService().document(tenant)["list_policy"]
        page = int(pagination.get("page", 1))
        page_size = int(pagination.get("page_size", policy["default_page_size"]))
        count = int(pagination.get("total", 0))
        proof_status = {
            "Locally consistent — not externally anchored": "locally_consistent",
            "Externally verified": "externally_verified",
            "Invalid proof": "invalid",
            "Verification unavailable": "unavailable",
        }.get(history.proof_status, "unavailable")
        return {
            "asset": {
                "id": str(asset.id),
                "tenant_id": str(asset.tenant_id),
                "asset_key": asset.asset_key,
                "name": asset.name,
                "description": asset.description,
                "product_ref": asset.product_ref,
                "batch_ref": asset.batch_ref,
                "serial_number": asset.serial_number,
                "gtin": asset.gtin,
                "asset_type": asset.asset_type,
                "status": asset.status,
                "attributes": asset.attributes,
                "head_sequence": asset.head_sequence,
                "head_hash": asset.head_hash,
                "activated_at": asset.activated_at.isoformat() if asset.activated_at else None,
                "recalled_at": asset.recalled_at.isoformat() if asset.recalled_at else None,
                "retired_at": asset.retired_at.isoformat() if asset.retired_at else None,
                "created_at": asset.created_at.isoformat(),
                "updated_at": asset.updated_at.isoformat(),
                "created_by": asset.created_by,
                "updated_by": asset.updated_by,
            },
            "items": timeline,
            "proof_status": proof_status,
            "failing_sequence": history.failing_sequence,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": (count + page_size - 1) // page_size if count else 0,
                "count": count,
                "has_next": bool(pagination.get("has_next", False)),
                "has_previous": page > 1,
            },
        }


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
                key: values.get(
                    key, "" if key in {"presented_token_digest", "chain_head_hash", "source_fingerprint"} else None
                )
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
        actor = _actor(actor_id, tenant)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"asset_id", "idempotency_key", "event_type", "occurred_at", "actor_ref"},
        )
        asset_id = _uuid(values.pop("asset_id"), "asset_id")
        schema_policy = BlockchainTraceabilityConfigurationService().document(tenant)["schema_policy"]
        values.setdefault("schema_version", schema_policy["default_version"])
        if values["schema_version"] not in schema_policy["allowed_versions"]:
            raise BlockchainTraceabilityError(
                "validation_error", "Schema version is not in the tenant allow-list.", status_code=400
            )
        values.setdefault("location", {})
        values.setdefault("payload", {})
        with transaction.atomic():
            try:
                asset = TraceabilityAsset.objects.select_for_update().get(
                    tenant_id=tenant, id=asset_id, is_deleted=False
                )
            except TraceabilityAsset.DoesNotExist as exc:
                raise DomainNotFoundError("traceability asset") from exc
            if asset.status == TraceabilityAssetStatus.RETIRED:
                raise DomainConflictError("asset_retired", "Events cannot be appended to a retired asset.")
            existing = TraceabilityEvent.objects.filter(
                tenant_id=tenant, asset=asset, idempotency_key=values["idempotency_key"]
            ).first()
            if existing is not None:
                comparable = {
                    key: values[key]
                    for key in ("event_type", "schema_version", "occurred_at", "actor_ref", "location", "payload")
                }
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
        chunk_size = int(
            BlockchainTraceabilityConfigurationService().document(asset.tenant_id)["list_policy"][
                "verification_chunk_size"
            ]
        )
        for event in (
            TraceabilityEvent.objects.filter(tenant_id=asset.tenant_id, asset=asset)
            .order_by("sequence")
            .iterator(chunk_size=chunk_size)
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
                "actor_id": _actor(actor_id, asset.tenant_id),
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
        queryset = LedgerAnchor.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related(
            "asset", "network"
        )
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
        actor = _actor(actor_id, tenant)
        values = _data(data, allowed=self.CREATE_FIELDS, required={"asset_id", "network_id", "idempotency_key"})
        asset = TraceabilityAssetService().get_asset(tenant, values.pop("asset_id"))
        network = LedgerNetworkService().get_network(tenant, values.pop("network_id"))
        if network.status != LedgerNetworkStatus.ACTIVE:
            raise DomainConflictError("network_not_active", "Anchors require an active ledger network.")
        anchor_policy = BlockchainTraceabilityConfigurationService().document(tenant)["anchor_policy"]
        start_sequence = int(values.pop("start_sequence", anchor_policy["default_start_sequence"]))
        if "end_sequence" in values:
            end_sequence = int(values.pop("end_sequence"))
        elif bool(anchor_policy["use_current_head_default"]):
            end_sequence = int(asset.head_sequence)
        else:
            raise BlockchainTraceabilityError(
                "validation_error", "end_sequence is required by the tenant anchoring policy.", status_code=400
            )
        if start_sequence < 1 or end_sequence < start_sequence or end_sequence > asset.head_sequence:
            raise BlockchainTraceabilityError(
                "invalid_anchor_range", "The requested event range is invalid.", status_code=400
            )
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
            anchor = _transition("anchor", anchor, "fail", transition_key, "system", failure_code=code)
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
            raise BlockchainTraceabilityError(
                "invalid_job", "The job command is not an anchor submission.", status_code=400
            )
        tenant = _uuid(job.tenant_id, "tenant_id")
        anchor_id = job.payload.get("anchor_id") if isinstance(job.payload, dict) else None
        if not anchor_id:
            raise BlockchainTraceabilityError(
                "invalid_job", "The durable job is missing anchor identity.", status_code=400
            )
        with transaction.atomic():
            anchor = (
                LedgerAnchor.objects.select_for_update()
                .select_related("network", "asset")
                .get(tenant_id=tenant, id=_uuid(anchor_id, "anchor_id"))
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
            anchor = _transition("anchor", anchor, "start_submission", f"job:{job.id}:start", "system")
        try:
            provider = self._provider(anchor.network)
            receipt = execute_resilient_provider_call(
                anchor.tenant_id,
                "anchor_submission",
                lambda: provider.submit_anchor(anchor.network, anchor, str(job.id)),
            )
            if not isinstance(receipt, SubmissionReceipt):
                raise InvalidProviderResponseError("provider returned invalid submission evidence")
        except (AdapterNotRegisteredError, ProviderUnavailableError) as exc:
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
                self._fail_anchor(
                    locked,
                    "PROVIDER_UNAVAILABLE",
                    "The ledger provider could not submit the anchor.",
                    f"job:{job.id}:fail",
                )
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
                "invalid_provider_response",
                "The ledger provider returned invalid submission evidence.",
                status_code=502,
            ) from exc
        if receipt.simulated or not receipt.accepted:
            code = "SIMULATED_PROVIDER" if receipt.simulated else (receipt.failure_code or "PROVIDER_REJECTED")
            message = (
                "Simulated provider evidence cannot anchor a traceability proof."
                if receipt.simulated
                else (receipt.failure_message or "The provider rejected the anchor.")
            )
            with transaction.atomic():
                locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
                self._fail_anchor(locked, code, message, f"job:{job.id}:rejected")
            raise BlockchainTraceabilityError(code.lower(), message, status_code=422)
        with transaction.atomic():
            locked = LedgerAnchor.objects.select_for_update().get(tenant_id=tenant, id=anchor.id)
            locked = _transition("anchor", locked, "accept_submission", f"job:{job.id}:accepted", "system")
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
                "anchor",
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

    def refresh_receipt(self, tenant_id: UUID, anchor_id: UUID | str, actor_id: str) -> OperationResult[LedgerAnchor]:
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
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
            provider = self._provider(anchor.network)
            receipt = execute_resilient_provider_call(
                anchor.tenant_id,
                "anchor_receipt",
                lambda: provider.get_receipt(anchor.network, anchor.provider_transaction_id),
            )
            if not isinstance(receipt, AnchorReceipt):
                raise InvalidProviderResponseError("provider returned invalid receipt evidence")
            with transaction.atomic():
                locked = (
                    LedgerAnchor.objects.select_for_update()
                    .select_related("network")
                    .get(tenant_id=anchor.tenant_id, id=anchor.id)
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
                capability="ledger_receipt",
                provider=anchor.network.provider_type,
                evidence={"anchor_id": str(anchor.id)},
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        anchor = self.get_anchor(tenant_id, anchor_id)
        outcome = VerificationOutcome.INCONCLUSIVE
        reason = "ANCHOR_NOT_CONFIRMED"
        evidence: dict[str, Any] = {"anchor_status": anchor.status, "root_hash": anchor.root_hash}
        try:
            provider = self._provider(anchor.network)
            proof = execute_resilient_provider_call(
                anchor.tenant_id, "anchor_verification", lambda: provider.verify_anchor(anchor.network, anchor)
            )
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
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id, tenant)
        with transaction.atomic():
            anchor = LedgerAnchor.objects.select_for_update().get(pk=self.get_anchor(tenant, anchor_id).pk)
            anchor = _transition("anchor", anchor, "retry", transition_key, actor)
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

    def _issuer_for_issue(self, tenant_id: UUID) -> tuple[CredentialIssuerAdapter, str]:
        adapter = self.issuer_adapter
        if adapter is None:
            issuer_type = BlockchainTraceabilityConfigurationService().document(tenant_id)["credential_policy"][
                "issuer_type"
            ]
            try:
                adapter = get_credential_issuer(str(issuer_type))
            except AdapterNotRegisteredError as exc:
                raise DependencyUnavailableError(
                    "credential_issuer", "The configured credential issuer is not registered."
                ) from exc
        key_ref = (
            self.issuer_key_ref
            or getattr(adapter, "issuer_key_ref", "")
            or getattr(settings, "BLOCKCHAIN_TRACEABILITY_ISSUER_KEY_REF", "")
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
        actor = _actor(actor_id, tenant)
        asset = TraceabilityAssetService().get_asset(tenant, asset_id)
        if asset.status == TraceabilityAssetStatus.RETIRED:
            raise DomainConflictError("asset_retired", "Credentials cannot be issued for a retired asset.")
        if not isinstance(claims, Mapping):
            raise BlockchainTraceabilityError("validation_error", "claims must be an object.", status_code=400)
        if {"asset_id", "public_id"} & set(claims):
            raise BlockchainTraceabilityError(
                "reserved_claim", "asset_id and public_id are issuer-managed claims.", status_code=400
            )
        issued_at = timezone.now()
        if expires_at is not None and expires_at <= issued_at:
            raise BlockchainTraceabilityError("validation_error", "expires_at must be in the future.", status_code=400)
        public_id = str(uuid.uuid4())
        bound_claims = {**dict(claims), "asset_id": str(asset.id), "public_id": public_id}
        canonical_claims = canonical_json(bound_claims)
        claims_hash = sha256_hex(canonical_claims)
        credential_policy = BlockchainTraceabilityConfigurationService().document(tenant)["credential_policy"]
        token = secrets.token_urlsafe(int(credential_policy["token_entropy_bytes"]))
        token_digest = sha256_hex(token)
        adapter, issuer_key_ref = self._issuer_for_issue(tenant)
        saga_id = uuid.uuid4()
        CredentialIssuanceSagaEvent.objects.create(
            tenant_id=tenant,
            saga_id=saga_id,
            event_type="signing_requested",
            evidence={"claims_hash": claims_hash, "public_id": public_id},
            actor_id=actor,
            correlation_id=_correlation(),
        )
        try:
            signature_result = execute_resilient_provider_call(
                tenant,
                "credential_signing",
                lambda: adapter.sign_claims(tenant, issuer_key_ref, canonical_claims),
            )
        except ProviderUnavailableError as exc:
            CredentialIssuanceSagaEvent.objects.create(
                tenant_id=tenant,
                saga_id=saga_id,
                event_type="signing_failed",
                evidence={"reason_code": "PROVIDER_UNAVAILABLE"},
                actor_id=actor,
                correlation_id=_correlation(),
            )
            metrics.PROVIDER_UNAVAILABLE.labels(capability="credential_signing").inc()
            raise DependencyUnavailableError("credential_issuer") from exc
        except ProviderError as exc:
            CredentialIssuanceSagaEvent.objects.create(
                tenant_id=tenant,
                saga_id=saga_id,
                event_type="signing_failed",
                evidence={"reason_code": "INVALID_PROVIDER_RESPONSE"},
                actor_id=actor,
                correlation_id=_correlation(),
            )
            raise BlockchainTraceabilityError(
                "credential_signing_failed", "The credential could not be signed.", status_code=502
            ) from exc
        credential_type = str(getattr(adapter, "issuer_type", "signed_claims"))
        maximum_type = int(
            BlockchainTraceabilityConfigurationService().document(tenant)["validation"]["credential_type_max_chars"]
        )
        if not credential_type or len(credential_type) > maximum_type:
            raise BlockchainTraceabilityError(
                "invalid_provider_schema",
                "Credential issuer type violates the configured provider schema.",
                status_code=502,
            )
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
                CredentialIssuanceSagaEvent.objects.create(
                    tenant_id=tenant,
                    saga_id=saga_id,
                    credential_id=credential.id,
                    event_type="credential_persisted",
                    evidence={"claims_hash": claims_hash},
                    actor_id=actor,
                    correlation_id=_correlation(),
                )
                _emit_domain_event(
                    tenant,
                    "authenticity_credential",
                    credential.id,
                    "blockchain_traceability.credential.issued",
                    {"credential_id": str(credential.id), "asset_id": str(asset.id), "public_id": credential.public_id},
                )
        except (ValidationError, IntegrityError) as exc:
            invalidator = getattr(adapter, "invalidate_signature", None)
            compensation = "signature_invalidated" if callable(invalidator) else "compensation_unavailable"
            if callable(invalidator):
                try:
                    invalidator(tenant, issuer_key_ref, signature_result)
                except ProviderError:
                    compensation = "compensation_failed"
            CredentialIssuanceSagaEvent.objects.create(
                tenant_id=tenant,
                saga_id=saga_id,
                event_type=compensation,
                evidence={"claims_hash": claims_hash},
                actor_id=actor,
                correlation_id=_correlation(),
            )
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
        queryset = AuthenticityCredential.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related(
            "asset"
        )
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        if not isinstance(reason, str) or not reason.strip():
            raise BlockchainTraceabilityError("validation_error", "A revocation reason is required.", status_code=400)
        with transaction.atomic():
            credential = AuthenticityCredential.objects.select_for_update().get(
                pk=self.get_credential(tenant_id, credential_id).pk
            )
            credential.revoked_at = timezone.now()
            credential.revocation_reason = reason.strip()
            credential.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
            credential = _transition("credential", credential, "revoke", transition_key, actor, reason=reason.strip())
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
                "actor_id": _actor(actor_id, _uuid(tenant_id, "tenant_id")),
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
        credential = (
            AuthenticityCredential.objects.select_related("asset").filter(tenant_id=tenant, public_id=public_id).first()
        )
        if credential is None:
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_NOT_FOUND",
                {"credential_found": False},
            )
        if not hmac.compare_digest(token_digest, credential.token_digest):
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.NOT_AUTHENTIC,
                "TOKEN_MISMATCH",
                {"credential_found": True, "token_match": False},
                credential,
            )
        if credential.status == AuthenticityCredentialStatus.REVOKED:
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_REVOKED",
                {"token_match": True, "credential_status": credential.status},
                credential,
            )
        if credential.expires_at is not None and credential.expires_at <= timezone.now():
            with transaction.atomic():
                locked = AuthenticityCredential.objects.select_for_update().get(tenant_id=tenant, id=credential.id)
                if locked.status == AuthenticityCredentialStatus.ACTIVE:
                    credential = _transition(
                        "credential", locked, "expire", f"expiry:{credential.expires_at.isoformat()}", "system"
                    )
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.NOT_AUTHENTIC,
                "CREDENTIAL_EXPIRED",
                {"token_match": True, "credential_status": credential.status},
                credential,
            )
        if (
            credential.claims.get("asset_id") != str(credential.asset_id)
            or credential.claims.get("public_id") != public_id
        ):
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.INVALID,
                "CLAIM_BINDING_INVALID",
                {"token_match": True, "claim_binding": False},
                credential,
            )
        try:
            adapter = self.issuer_adapter or get_credential_issuer(credential.credential_type)
            proof = execute_resilient_provider_call(
                tenant, "credential_verification", lambda: adapter.verify_signature(tenant, credential)
            )
            if not isinstance(proof, ProofResult):
                raise InvalidProviderResponseError("issuer returned invalid proof")
        except (AdapterNotRegisteredError, ProviderUnavailableError):
            metrics.PROVIDER_UNAVAILABLE.labels(capability="credential_verification").inc()
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.DEPENDENCY_UNAVAILABLE,
                "ISSUER_UNAVAILABLE",
                {"token_match": True, "claim_binding": True},
                credential,
            )
        except ProviderError:
            return self._record_authenticity(
                tenant,
                actor_id,
                idempotency_key,
                started,
                token_digest,
                VerificationOutcome.INVALID,
                "INVALID_SIGNATURE_EVIDENCE",
                {"token_match": True, "claim_binding": True},
                credential,
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
            result = execute_resilient_provider_call(
                tenant, "document_reference", lambda: resolver.validate_reference(tenant, document_id)
            )
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
        actor = _actor(actor_id, tenant)
        values = _data(
            data,
            allowed=self.CREATE_FIELDS,
            required={"asset_id", "evidence_key", "evidence_type", "standard", "result", "observed_at"},
        )
        fingerprint_values = dict(values)
        idempotency_key = str(values["evidence_key"])
        replay = _mutation_replay(tenant, "compliance.create", idempotency_key, fingerprint_values, ComplianceEvidence)
        if replay is not None:
            return replay
        self._validate_document(tenant, values)
        values = self._references(tenant, values)
        try:
            with transaction.atomic():
                evidence = ComplianceEvidence(tenant_id=tenant, created_by=actor, **values)
                evidence.save()
                _record_mutation(tenant, "compliance.create", idempotency_key, fingerprint_values, evidence)
                _emit_domain_event(
                    tenant,
                    "compliance_evidence",
                    evidence.id,
                    "blockchain_traceability.compliance.created",
                    {"evidence_id": str(evidence.id), "actor_id": actor},
                )
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
        queryset = ComplianceEvidence.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), is_deleted=False
        ).select_related("asset", "event", "supersedes")
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
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id, tenant)
        values = _data(data, allowed=self.UPDATE_FIELDS)
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        with transaction.atomic():
            evidence = ComplianceEvidence.objects.select_for_update().get(
                pk=self.get_evidence(tenant_id, evidence_id).pk
            )
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
        actor = _actor(actor_id, _uuid(tenant_id, "tenant_id"))
        with transaction.atomic():
            evidence = ComplianceEvidence.objects.select_for_update().get(
                pk=self.get_evidence(tenant_id, evidence_id).pk
            )
            if evidence.status != ComplianceEvidenceStatus.DRAFT:
                raise DomainConflictError("evidence_not_draft", "Only draft evidence can be finalized.")
            evidence.content_hash = sha256_hex(canonical_json(self._content_document(evidence)))
            evidence.finalized_at = timezone.now()
            evidence.updated_by = actor
            evidence.save(update_fields=["content_hash", "finalized_at", "updated_by", "updated_at"])
            evidence = _transition("compliance_evidence", evidence, "finalize", transition_key, actor)
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
        actor = _actor(actor_id, tenant)
        with transaction.atomic():
            original = ComplianceEvidence.objects.select_for_update().get(pk=self.get_evidence(tenant, evidence_id).pk)
            if original.status != ComplianceEvidenceStatus.FINALIZED:
                raise DomainConflictError("evidence_not_finalized", "Only finalized evidence can be superseded.")
            values = dict(replacement_data)
            values["asset_id"] = original.asset_id
            values["supersedes_id"] = original.id
            replacement = self.create_draft(tenant, actor, values)
            replacement = self.finalize(tenant, replacement.id, actor, f"{transition_key}:replacement")
            _transition(
                "compliance_evidence", original, "supersede", transition_key, actor, replacement_id=str(replacement.id)
            )
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
                "actor_id": _actor(actor_id, evidence.tenant_id),
                "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
            },
        )

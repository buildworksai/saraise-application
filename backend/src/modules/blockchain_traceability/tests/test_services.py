"""Transactional domain-flow, cryptographic, and failure-semantics tests."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from src.core.api import CapabilityUnavailable
from src.core.async_jobs.models import AsyncJob, JobTransition, OutboxEvent

from .. import services
from ..hashing import CanonicalizationError, compute_event_hash, compute_merkle_root
from ..models import (
    AuthenticityCredentialStatus,
    ComplianceEvidenceStatus,
    ImmutableEvidenceError,
    LedgerAnchorStatus,
    LifecycleTransition,
    MutationIdempotencyRecord,
    TraceabilityAsset,
    TraceabilityAssetStatus,
    TraceabilityEvent,
    VerificationOutcome,
    VerificationType,
)
from ..providers import (
    AnchorReceipt,
    CapabilityMetadata,
    DocumentReferenceResult,
    InvalidProviderResponseError,
    InventoryReferenceResult,
    ProofResult,
    ProviderCircuitOpenError,
    ProviderHealth,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SignatureResult,
    SubmissionReceipt,
    ledger_provider_registry,
)
from ..services import (
    DEFAULT_CONFIGURATION,
    AuthenticityService,
    BlockchainTraceabilityConfigurationService,
    BlockchainTraceabilityError,
    ComplianceEvidenceService,
    DependencyUnavailableError,
    DomainConflictError,
    DomainNotFoundError,
    IdempotencyConflictError,
    LedgerAnchorService,
    LedgerNetworkService,
    TraceabilityAssetService,
    TraceabilityEventService,
    VerificationService,
    _actor,
    _data,
    _matches,
    _model_error,
    _provider_failure,
    _safe_receipt,
)

pytestmark = pytest.mark.django_db(transaction=True)


class WorkingLedger:
    provider_type = "test-ledger"

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key=self.provider_type, display_name="Test ledger", capabilities=("anchor",))

    def validate_options(self, options: Any) -> None:
        if options.get("invalid"):
            raise ValueError("invalid")

    def health(self, network: Any) -> ProviderHealth:
        return ProviderHealth(available=True, code="READY", checked_at=timezone.now())

    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt:
        return SubmissionReceipt(
            accepted=True,
            provider_transaction_id=f"tx-{idempotency_key}",
            transaction_hash="0xabc",
            submitted_at=timezone.now(),
            receipt={"accepted": True},
        )

    def get_receipt(self, network: Any, provider_transaction_id: str) -> AnchorReceipt:
        return AnchorReceipt(
            provider_transaction_id=provider_transaction_id,
            transaction_hash="0xabc",
            block_number=42,
            block_hash="0xblock42",
            confirmations=network.confirmation_depth,
            final=True,
            observed_at=timezone.now(),
            receipt={"final": True},
        )

    def verify_anchor(self, network: Any, anchor: Any) -> ProofResult:
        return ProofResult(
            verified=True,
            reason_code="ANCHOR_VERIFIED",
            evidence={"transaction_hash": anchor.transaction_hash, "block_hash": anchor.block_hash},
        )


class TimeoutLedger(WorkingLedger):
    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt:
        raise ProviderTimeoutError("timeout")


class InvalidLedger(WorkingLedger):
    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt:
        raise InvalidProviderResponseError("invalid")


class RejectingLedger(WorkingLedger):
    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt:
        return SubmissionReceipt(
            accepted=False,
            failure_code="POLICY_REJECTED",
            failure_message="Anchor violates provider policy",
        )


class SimulatedLedger(WorkingLedger):
    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt:
        return SubmissionReceipt(
            accepted=True,
            provider_transaction_id=f"sim-{idempotency_key}",
            transaction_hash="0xsimulated",
            submitted_at=timezone.now(),
            receipt={"simulated": True},
            simulated=True,
        )


class MismatchedReceiptLedger(WorkingLedger):
    def get_receipt(self, network: Any, provider_transaction_id: str) -> AnchorReceipt:
        return AnchorReceipt(
            provider_transaction_id=f"unexpected-{provider_transaction_id}",
            transaction_hash="0xmismatch",
            confirmations=1,
            final=False,
        )


class UnavailableReceiptLedger(WorkingLedger):
    def get_receipt(self, network: Any, provider_transaction_id: str) -> AnchorReceipt:
        raise ProviderUnavailableError("receipt unavailable")


class NegativeProofLedger(WorkingLedger):
    def verify_anchor(self, network: Any, anchor: Any) -> ProofResult:
        return ProofResult(verified=False, reason_code="PROOF_REJECTED", evidence={"anchor_id": str(anchor.id)})


class UnhealthyLedger(WorkingLedger):
    def health(self, network: Any) -> ProviderHealth:
        return ProviderHealth(available=False, code="MAINTENANCE", checked_at=timezone.now())


class InvalidHealthLedger(WorkingLedger):
    def health(self, network: Any) -> dict[str, str]:
        return {"status": "not-a-provider-health"}


class CredentialIssuer:
    issuer_type = "unit-issuer"
    issuer_key_ref = "issuer://unit"

    def __init__(self, *, verification: ProofResult | Exception | None = None) -> None:
        self.verification = verification or ProofResult(
            verified=True,
            reason_code="SIGNATURE_VALID",
            evidence={"signature": "verified"},
        )

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key=self.issuer_type, display_name="Unit issuer")

    def sign_claims(self, tenant_id: uuid.UUID, issuer_key_ref: str, canonical_claims: bytes) -> SignatureResult:
        return SignatureResult(
            signature_algorithm="unit-signature-v1",
            signature=f"sig-{len(canonical_claims)}-{tenant_id}",
            evidence={"issuer_key_ref": issuer_key_ref},
        )

    def verify_signature(self, tenant_id: uuid.UUID, credential: Any) -> ProofResult:
        del tenant_id, credential
        if isinstance(self.verification, Exception):
            raise self.verification
        return self.verification

    def invalidate_signature(self, tenant_id: uuid.UUID, issuer_key_ref: str, signature: SignatureResult) -> None:
        del tenant_id, issuer_key_ref, signature


class DocumentResolver:
    resolver_type = "default"

    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key="default", display_name="DMS resolver")

    def validate_reference(self, tenant_id: uuid.UUID, document_ref: uuid.UUID) -> DocumentReferenceResult:
        return DocumentReferenceResult(valid=self.valid, reason_code="FOUND" if self.valid else "NOT_FOUND")


class InventoryResolver:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key="default", display_name="Inventory resolver")

    def validate_reference(self, tenant_id: uuid.UUID, product_ref: str, batch_ref: str) -> InventoryReferenceResult:
        return InventoryReferenceResult(valid=self.valid, reason_code="FOUND" if self.valid else "NOT_FOUND")


@pytest.fixture
def ledger() -> WorkingLedger:
    prior = ledger_provider_registry.unregister("test-ledger")
    adapter = WorkingLedger()
    ledger_provider_registry.register("test-ledger", adapter)
    try:
        yield adapter
    finally:
        ledger_provider_registry.unregister("test-ledger")
        if prior is not None:
            ledger_provider_registry.register("test-ledger", prior)


def register_asset(tenant: uuid.UUID, key: str = "asset-1") -> TraceabilityAsset:
    return TraceabilityAssetService().register_asset(
        tenant,
        "user:creator",
        {
            "asset_key": key,
            "name": "Serialized medicine",
            "serial_number": f"SERIAL-{key}",
            "asset_type": "medicine",
            "attributes": {"cold_chain": True},
        },
    )


def append_event(
    tenant: uuid.UUID, asset: TraceabilityAsset, key: str, event_type: str = "manufactured"
) -> TraceabilityEvent:
    return TraceabilityEventService().append_event(
        tenant,
        "user:recorder",
        {
            "asset_id": asset.id,
            "idempotency_key": key,
            "event_type": event_type,
            "occurred_at": timezone.now(),
            "actor_ref": "operator:42",
            "location": {"site": "plant-a"},
            "payload": {"step": key},
        },
    )


def active_network(tenant: uuid.UUID, ledger: WorkingLedger) -> Any:
    service = LedgerNetworkService()
    network = service.create_network(
        tenant,
        "admin",
        {
            "network_key": "primary",
            "name": "Primary ledger",
            "provider_type": ledger.provider_type,
            "dependency_key": "ledger.primary",
            "network_namespace": "saraise:test",
            "confirmation_depth": 2,
        },
    )
    return service.activate_network(tenant, network.id, "admin", "activate-network")


def test_golden_hash_fixture_and_nonfinite_rejection() -> None:
    vector = json.loads((Path(__file__).parent / "fixtures" / "event_hash_v1.json").read_text())
    fields = vector["input"]
    fields["occurred_at"] = datetime.fromisoformat(fields["occurred_at"].replace("Z", "+00:00"))
    assert compute_event_hash(**fields) == vector["event_hash"]
    with pytest.raises(CanonicalizationError, match="non-finite"):
        compute_event_hash(**{**fields, "payload": {"invalid": float("nan")}})
    assert compute_merkle_root(["a" * 64]) == "a" * 64


def test_append_first_chain_idempotency_conflict_and_atomic_outbox() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    occurred = timezone.now()
    request = {
        "asset_id": asset.id,
        "idempotency_key": "evt-1",
        "event_type": "manufactured",
        "occurred_at": occurred,
        "actor_ref": "operator",
        "location": {},
        "payload": {"quantity": 1},
    }
    service = TraceabilityEventService()
    first = service.append_event(tenant, "creator", request)
    replay = service.append_event(tenant, "creator", request)
    assert replay.id == first.id and first.sequence == 1 and first.previous_hash == ""
    second = append_event(tenant, asset, "evt-2", "packed")
    assert second.sequence == 2 and second.previous_hash == first.event_hash
    asset.refresh_from_db()
    assert asset.head_sequence == 2 and asset.head_hash == second.event_hash
    assert OutboxEvent.objects.filter(
        tenant_id=tenant, aggregate_id=first.id, event_type="blockchain_traceability.event.appended"
    ).exists()
    with pytest.raises(IdempotencyConflictError):
        service.append_event(tenant, "creator", {**request, "event_type": "tampered"})
    assert TraceabilityEvent.objects.filter(tenant_id=tenant, asset=asset).count() == 2


def test_mutation_idempotency_and_lifecycle_audit_are_tenant_scoped_and_immutable(
    ledger: WorkingLedger,
) -> None:
    tenant = uuid.uuid4()
    network_request = {
        "network_key": "idempotent-network",
        "name": "Idempotent network",
        "provider_type": ledger.provider_type,
        "dependency_key": "ledger.idempotent",
        "network_namespace": "saraise:idempotent",
    }
    network_service = LedgerNetworkService()
    network = network_service.create_network(tenant, "admin", network_request)
    assert network_service.create_network(tenant, "admin", network_request).id == network.id
    with pytest.raises(IdempotencyConflictError):
        network_service.create_network(tenant, "admin", {**network_request, "name": "Tampered"})

    asset_request = {
        "asset_key": "idempotent-asset",
        "name": "Idempotent asset",
        "asset_type": "medicine",
        "serial_number": "SERIAL-IDEMPOTENT",
    }
    asset_service = TraceabilityAssetService()
    asset = asset_service.register_asset(tenant, "operator", asset_request)
    assert asset_service.register_asset(tenant, "operator", asset_request).id == asset.id
    with pytest.raises(IdempotencyConflictError):
        asset_service.register_asset(tenant, "operator", {**asset_request, "name": "Tampered"})

    evidence_request = {
        "asset_id": asset.id,
        "evidence_key": "idempotent-evidence",
        "evidence_type": "certificate",
        "standard": "ISO-1",
        "result": "pass",
        "observed_at": timezone.now(),
    }
    evidence_service = ComplianceEvidenceService()
    evidence = evidence_service.create_draft(tenant, "auditor", evidence_request)
    assert evidence_service.create_draft(tenant, "auditor", evidence_request).id == evidence.id
    with pytest.raises(IdempotencyConflictError):
        evidence_service.create_draft(tenant, "auditor", {**evidence_request, "standard": "ISO-2"})

    assert MutationIdempotencyRecord.objects.filter(tenant_id=tenant).count() == 3
    network_service.activate_network(tenant, network.id, "admin", "activate-idempotent")
    transition = LifecycleTransition.objects.get(tenant_id=tenant, aggregate_id=network.id)
    transition.command = "tampered"
    with pytest.raises(ImmutableEvidenceError, match="cannot be updated"):
        transition.save()
    with pytest.raises(ImmutableEvidenceError, match="cannot be deleted"):
        LifecycleTransition.objects.filter(pk=transition.pk).delete()


def test_configuration_service_rejects_malformed_imports_and_invalid_policy_edges() -> None:
    tenant = uuid.uuid4()
    service = BlockchainTraceabilityConfigurationService()
    current = service.current(tenant)

    malformed = {"schema": "x", "document": current.document, "unexpected": True}
    with pytest.raises(BlockchainTraceabilityError) as invalid_import:
        service.import_document(tenant, "operator", malformed)
    assert invalid_import.value.error_code == "invalid_configuration_import"

    missing_document = {"schema": "x"}
    with pytest.raises(BlockchainTraceabilityError) as missing:
        service.import_document(tenant, "operator", missing_document)
    assert missing.value.error_code == "invalid_configuration_import"

    invalid = json.loads(json.dumps(DEFAULT_CONFIGURATION))
    invalid["workflow"]["machines"]["asset"]["transitions"][0] = ["activate", "draft", "unknown"]
    with pytest.raises(BlockchainTraceabilityError) as bad_edge:
        service.preview(tenant, invalid)
    assert bad_edge.value.error_code == "invalid_configuration"

    invalid = json.loads(json.dumps(DEFAULT_CONFIGURATION))
    invalid["features"]["roles"] = ["tenant admin"]
    with pytest.raises(BlockchainTraceabilityError) as bad_role:
        service.update(tenant, "operator", invalid)
    assert bad_role.value.error_code == "invalid_configuration"


def test_configuration_validation_rejects_unsafe_limits_and_workflow_allowlists() -> None:
    base = json.loads(json.dumps(DEFAULT_CONFIGURATION))
    invalid_cases = [
        ("missing section", {key: value for key, value in base.items() if key != "ui"}),
        ("section type", {**base, "ui": []}),
        ("gtin allow-list", {**base, "validation": {**base["validation"], "gtin_lengths": [7]}}),
        (
            "backoff order",
            {**base, "resilience": {**base["resilience"], "base_backoff_seconds": 2.0, "max_backoff_seconds": 1.0}},
        ),
        (
            "machine states",
            {
                **base,
                "workflow": {
                    **base["workflow"],
                    "machines": {
                        **base["workflow"]["machines"],
                        "asset": {**base["workflow"]["machines"]["asset"], "states": ["draft"]},
                    },
                },
            },
        ),
        (
            "presentation statuses",
            {**base, "ui": {**base["ui"], "positive_statuses": ["impossible"]}},
        ),
        ("feature flag", {**base, "features": {**base["features"], "enabled": "yes"}}),
    ]

    for label, document in invalid_cases:
        with pytest.raises(BlockchainTraceabilityError) as raised:
            BlockchainTraceabilityConfigurationService.validate_document(document)
        assert raised.value.error_code == "invalid_configuration", label


def test_shared_guards_redact_receipts_and_fail_closed_on_invalid_input() -> None:
    tenant = uuid.uuid4()

    with pytest.raises(BlockchainTraceabilityError) as bad_uuid:
        TraceabilityAssetService().get_asset("not-a-uuid", uuid.uuid4())
    assert bad_uuid.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as missing_actor:
        _actor(" ", tenant)
    assert missing_actor.value.error_code == "validation_error"

    long_actor = "x" * (DEFAULT_CONFIGURATION["validation"]["max_actor_id_chars"] + 1)
    with pytest.raises(BlockchainTraceabilityError) as long_actor_error:
        _actor(long_actor, tenant)
    assert long_actor_error.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as non_object:
        _data([], allowed={"name"})
    assert non_object.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as unknown:
        _data({"name": "ok", "secret": "blocked"}, allowed={"name"})  # pragma: allowlist secret
    assert unknown.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as missing:
        _data({"name": "ok"}, allowed={"name", "key"}, required={"key"})
    assert missing.value.error_code == "validation_error"

    safe = _safe_receipt(
        {
            "transaction": "tx-1",
            "authorization": "Bearer secret",  # pragma: allowlist secret
            "nested": {"api_token": "secret", "proof": "public"},  # pragma: allowlist secret
            "items": [{"password": "secret", "height": 5}],  # pragma: allowlist secret
        }
    )
    assert safe == {"transaction": "tx-1", "nested": {"proof": "public"}, "items": [{"height": 5}]}

    with pytest.raises(InvalidProviderResponseError):
        _safe_receipt("not-an-object")

    timeout_failure = _provider_failure(ProviderTimeoutError("timeout"), "anchor")
    assert timeout_failure.error_code == "dependency_unavailable"
    assert str(timeout_failure.detail) == "The provider call timed out."


def test_shared_matching_model_error_and_mutation_replay_failure_paths() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    assert _matches(asset, {"id": str(asset.id), "asset_key": asset.asset_key}) is True
    assert _matches(asset, {"id": uuid.uuid4()}) is False

    mapped = _model_error(ValidationError({"asset_key": ["duplicate"]}))
    assert mapped.error_code == "validation_error"
    assert str(mapped) == "The traceability data is invalid."

    MutationIdempotencyRecord.objects.create(
        tenant_id=tenant,
        operation="asset.register",
        idempotency_key="missing-resource",
        request_fingerprint=services._mutation_fingerprint({"asset_key": "missing-resource"}),
        resource_type="traceabilityasset",
        resource_id=uuid.uuid4(),
        correlation_id="mutation-missing-result",
    )

    with pytest.raises(DomainConflictError) as caught:
        services._mutation_replay(
            tenant,
            "asset.register",
            "missing-resource",
            {"asset_key": "missing-resource"},
            TraceabilityAsset,
        )

    assert caught.value.error_code == "idempotency_result_missing"


def test_resilient_provider_call_retries_opens_circuit_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = uuid.uuid4()
    document = json.loads(json.dumps(DEFAULT_CONFIGURATION))
    document["resilience"].update(
        {
            "max_attempts": 2,
            "base_backoff_seconds": 0.0,
            "max_backoff_seconds": 0.0,
            "circuit_failure_threshold": 2,
            "circuit_recovery_seconds": 30,
        }
    )
    BlockchainTraceabilityConfigurationService().update(tenant, "operator", document)
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    capability = "unit-provider"
    calls = 0

    def unavailable() -> object:
        nonlocal calls
        calls += 1
        raise ProviderUnavailableError("provider offline")

    with services._PROVIDER_CIRCUIT_LOCK:
        services._PROVIDER_CIRCUITS.pop((tenant, capability), None)
    try:
        with pytest.raises(ProviderCircuitOpenError, match="opened"):
            services.execute_resilient_provider_call(tenant, capability, unavailable)
        assert calls == 2

        with pytest.raises(ProviderCircuitOpenError, match="is open"):
            services.execute_resilient_provider_call(tenant, capability, lambda: "not-called")
        assert calls == 2

        with services._PROVIDER_CIRCUIT_LOCK:
            services._PROVIDER_CIRCUITS[(tenant, capability)] = (2, services.time.monotonic() - 31)
        assert services.execute_resilient_provider_call(tenant, capability, lambda: {"healthy": True}) == {
            "healthy": True
        }
        with services._PROVIDER_CIRCUIT_LOCK:
            assert services._PROVIDER_CIRCUITS[(tenant, capability)] == (0, None)
    finally:
        with services._PROVIDER_CIRCUIT_LOCK:
            services._PROVIDER_CIRCUITS.pop((tenant, capability), None)


def test_network_filter_update_delete_and_probe_failure_branches(ledger: WorkingLedger) -> None:
    tenant = uuid.uuid4()
    service = LedgerNetworkService()

    with pytest.raises(BlockchainTraceabilityError) as invalid_depth:
        service.create_network(
            tenant,
            "admin",
            {
                "network_key": "bad-depth",
                "name": "Bad depth",
                "provider_type": ledger.provider_type,
                "dependency_key": "ledger.bad",
                "network_namespace": "saraise:bad",
                "confirmation_depth": 0,
            },
        )
    assert invalid_depth.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as invalid_options:
        service.create_network(
            tenant,
            "admin",
            {
                "network_key": "bad-options",
                "name": "Bad options",
                "provider_type": ledger.provider_type,
                "dependency_key": "ledger.bad-options",
                "network_namespace": "saraise:bad-options",
                "provider_options": [],
            },
        )
    assert invalid_options.value.error_code == "validation_error"

    draft = service.create_network(
        tenant,
        "admin",
        {
            "network_key": "draft-delete",
            "name": "Draft delete",
            "provider_type": ledger.provider_type,
            "dependency_key": "ledger.draft",
            "network_namespace": "saraise:draft",
        },
    )
    assert (
        service.list_networks(tenant, {"status": "draft", "provider_type": ledger.provider_type}).get().id == draft.id
    )
    updated = service.update_network(tenant, draft.id, "admin", {"description": "retained"})
    assert updated.description == "retained"
    service.delete_network(tenant, draft.id, "admin")
    assert not service.list_networks(tenant, {"status": "draft"}).filter(id=draft.id).exists()

    active = active_network(tenant, ledger)
    with pytest.raises(DomainConflictError) as active_change:
        service.update_network(tenant, active.id, "admin", {"provider_options": {"region": "us"}})
    assert active_change.value.error_code == "network_active"
    with pytest.raises(DomainConflictError) as active_delete:
        service.delete_network(tenant, active.id, "admin")
    assert active_delete.value.error_code == "network_in_use"

    provider = ledger_provider_registry.unregister(ledger.provider_type)
    ledger_provider_registry.register(ledger.provider_type, InvalidHealthLedger())
    try:
        failed = service.probe_network(tenant, active.id, "admin")
    finally:
        ledger_provider_registry.unregister(ledger.provider_type)
        if provider is not None:
            ledger_provider_registry.register(ledger.provider_type, provider)
    assert failed.status == "failed"
    assert failed.error_code == "INVALID_PROVIDER_RESPONSE"


def test_asset_inventory_validation_filtering_retention_and_lifecycle() -> None:
    tenant = uuid.uuid4()
    actor = "operator"
    service = TraceabilityAssetService(inventory_resolver=InventoryResolver(valid=True))

    with pytest.raises(BlockchainTraceabilityError) as invalid_gtin:
        service.register_asset(
            tenant,
            actor,
            {
                "asset_key": "bad-gtin",
                "name": "Bad GTIN",
                "asset_type": "medicine",
                "gtin": "12345",
            },
        )
    assert invalid_gtin.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError) as invalid_inventory:
        TraceabilityAssetService(inventory_resolver=InventoryResolver(valid=False)).register_asset(
            tenant,
            actor,
            {
                "asset_key": "bad-inventory",
                "name": "Bad Inventory",
                "asset_type": "medicine",
                "product_ref": "SKU-1",
            },
        )
    assert invalid_inventory.value.error_code == "invalid_inventory_reference"

    asset = service.register_asset(
        tenant,
        actor,
        {
            "asset_key": "tracked-asset",
            "name": "Tracked Asset",
            "asset_type": "medicine",
            "product_ref": "SKU-2",
            "batch_ref": "BATCH-1",
            "gtin": "12345678",
        },
    )
    replay = service.register_asset(
        tenant,
        actor,
        {
            "asset_key": "tracked-asset",
            "name": "Tracked Asset",
            "asset_type": "medicine",
            "product_ref": "SKU-2",
            "batch_ref": "BATCH-1",
            "gtin": "12345678",
        },
    )
    assert replay.id == asset.id
    assert service.list_assets(tenant, {"product_ref": "SKU-2", "status": "draft"}).get().id == asset.id

    updated = service.update_asset(tenant, asset.id, actor, {"description": "updated"})
    assert updated.description == "updated"
    activated = service.activate_asset(tenant, asset.id, actor, "activate-asset")
    recalled = service.recall_asset(tenant, asset.id, actor, "quality hold", "recall-asset")
    released = service.release_recall(tenant, asset.id, actor, "release-recall")
    assert activated.activated_at is not None
    assert recalled.recalled_at is not None
    assert released.recalled_at is None

    append_event(tenant, released, "retention-event")
    with pytest.raises(DomainConflictError) as protected:
        service.delete_asset(tenant, released.id, actor)
    assert protected.value.error_code == "asset_has_evidence"

    retired = service.retire_asset(tenant, released.id, actor, "retire-asset")
    with pytest.raises(DomainConflictError) as immutable:
        service.update_asset(tenant, retired.id, actor, {"description": "forbidden"})
    assert immutable.value.error_code == "asset_retired"


def test_event_append_rolls_back_event_outbox_and_head_on_head_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    original_save = TraceabilityAsset.save

    def fail_head(instance: TraceabilityAsset, *args: Any, **kwargs: Any) -> None:
        if instance.head_sequence:
            raise RuntimeError("simulated head persistence failure")
        original_save(instance, *args, **kwargs)

    monkeypatch.setattr(TraceabilityAsset, "save", fail_head)
    with pytest.raises(RuntimeError, match="head persistence"):
        append_event(tenant, asset, "will-rollback")
    assert TraceabilityEvent.objects.filter(tenant_id=tenant).count() == 0
    assert not OutboxEvent.objects.filter(
        tenant_id=tenant, event_type="blockchain_traceability.event.appended"
    ).exists()
    asset.refresh_from_db()
    assert asset.head_sequence == 0 and asset.head_hash == ""


def test_chain_verification_records_valid_and_exact_broken_sequence() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    first = append_event(tenant, asset, "evt-1")
    append_event(tenant, asset, "evt-2")
    valid = TraceabilityEventService().verify_chain(tenant, asset.id, "auditor", "verify-valid")
    assert valid.outcome == VerificationOutcome.VERIFIED
    assert valid.proof_evidence["event_count"] == 2
    # SQL is intentionally used only in this test to emulate at-rest corruption;
    # production code remains Django ORM-only and blocks this update path.
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE blockchain_traceability_events SET event_hash = %s WHERE id = %s",
            ["f" * 64, first.id.hex if connection.vendor == "sqlite" else first.id],
        )
    invalid = TraceabilityEventService().verify_chain(tenant, asset.id, "auditor", "verify-invalid")
    assert invalid.outcome == VerificationOutcome.INVALID
    assert invalid.reason_code == "CHAIN_HASH_MISMATCH"
    assert invalid.proof_evidence["failing_sequence"] == 1


def test_chain_verification_detects_sequence_gap_empty_chain_and_asset_head_mismatch() -> None:
    tenant = uuid.uuid4()
    empty_asset = register_asset(tenant, "empty-chain")
    empty = TraceabilityEventService().verify_chain(tenant, empty_asset.id, "auditor", "verify-empty")
    assert empty.outcome == VerificationOutcome.INCONCLUSIVE
    assert empty.reason_code == "EMPTY_CHAIN"
    assert empty.proof_evidence == {"event_count": 0, "locally_consistent": True}

    gapped_asset = register_asset(tenant, "gapped-chain")
    first = append_event(tenant, gapped_asset, "evt-1")
    append_event(tenant, gapped_asset, "evt-2")
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {TraceabilityEvent._meta.db_table} WHERE id = %s",
            [first.id.hex if connection.vendor == "sqlite" else first.id],
        )
    gapped = TraceabilityEventService().verify_chain(tenant, gapped_asset.id, "auditor", "verify-gap")
    assert gapped.outcome == VerificationOutcome.INVALID
    assert gapped.reason_code == "CHAIN_SEQUENCE_GAP"
    assert gapped.proof_evidence["failing_sequence"] == 1
    assert gapped.proof_evidence["observed_sequence"] == 2

    head_asset = register_asset(tenant, "head-mismatch")
    append_event(tenant, head_asset, "evt-1")
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE blockchain_traceability_assets SET head_sequence = %s, head_hash = %s WHERE id = %s",
            [99, "e" * 64, head_asset.id.hex if connection.vendor == "sqlite" else head_asset.id],
        )
    head_mismatch = TraceabilityEventService().verify_chain(tenant, head_asset.id, "auditor", "verify-head")
    assert head_mismatch.outcome == VerificationOutcome.INVALID
    assert head_mismatch.reason_code == "ASSET_HEAD_MISMATCH"
    assert head_mismatch.proof_evidence["stored_head_sequence"] == 99


def test_asset_lifecycle_guards_history_and_rejected_transition_nonmutation() -> None:
    tenant = uuid.uuid4()
    service = TraceabilityAssetService()
    asset = register_asset(tenant)
    asset = service.activate_asset(tenant, asset.id, "operator", "activate")
    assert asset.status == TraceabilityAssetStatus.ACTIVE
    asset = service.recall_asset(tenant, asset.id, "operator", "quality issue", "recall")
    assert asset.status == TraceabilityAssetStatus.RECALLED
    asset = service.release_recall(tenant, asset.id, "operator", "release")
    assert asset.status == TraceabilityAssetStatus.ACTIVE
    asset = service.retire_asset(tenant, asset.id, "operator", "retire")
    before = (asset.status, list(asset.transition_history), asset.updated_at)
    with pytest.raises(DomainConflictError):
        service.activate_asset(tenant, asset.id, "operator", "illegal")
    asset.refresh_from_db()
    assert (asset.status, asset.transition_history, asset.updated_at) == before
    with pytest.raises(DomainConflictError):
        append_event(tenant, asset, "retired-event")
    history = service.product_history(tenant, asset.id, 1, 25)
    assert history.asset["id"] == str(asset.id) and history.proof_status.startswith("Locally consistent")


def test_anchor_range_durable_job_replay_refresh_and_verification(ledger: WorkingLedger) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    first = append_event(tenant, asset, "evt-1")
    second = append_event(tenant, asset, "evt-2")
    network = active_network(tenant, ledger)
    service = LedgerAnchorService(provider=ledger)
    anchor, job = service.request_anchor(
        tenant,
        "anchor-user",
        {
            "asset_id": asset.id,
            "network_id": network.id,
            "start_sequence": 1,
            "end_sequence": 2,
            "idempotency_key": "a-1",
        },
    )
    assert anchor.root_hash == compute_merkle_root([first.event_hash, second.event_hash])
    assert anchor.status == LedgerAnchorStatus.QUEUED and anchor.async_job_id == job.id
    assert AsyncJob.objects.filter(id=job.id).exists()
    assert JobTransition.objects.filter(job=job, to_status="queued").exists()
    assert OutboxEvent.objects.filter(aggregate_id=job.id, event_type="async_job.enqueued").exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=anchor.id, event_type="blockchain_traceability.anchor.queued"
    ).exists()
    result = service.submit_anchor_job(job)
    replay = service.submit_anchor_job(job)
    assert result == replay and result["status"] == LedgerAnchorStatus.SUBMITTED
    refreshed = service.refresh_receipt(tenant, anchor.id, "auditor")
    assert refreshed.status == "succeeded" and refreshed.value is not None
    assert refreshed.value.status == LedgerAnchorStatus.CONFIRMED
    attempt = service.verify_anchor(tenant, anchor.id, "auditor", "proof-1")
    assert attempt.outcome == VerificationOutcome.VERIFIED


@pytest.mark.parametrize(
    ("adapter", "expected_code", "expected_status"),
    [
        (TimeoutLedger(), "PROVIDER_UNAVAILABLE", 503),
        (InvalidLedger(), "INVALID_PROVIDER_RESPONSE", 502),
    ],
)
def test_anchor_provider_failures_are_durable_and_never_fabricate_success(
    ledger: WorkingLedger, adapter: WorkingLedger, expected_code: str, expected_status: int
) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    network = active_network(tenant, ledger)
    service = LedgerAnchorService(provider=adapter)
    anchor, job = service.request_anchor(
        tenant, "user", {"asset_id": asset.id, "network_id": network.id, "idempotency_key": str(uuid.uuid4())}
    )
    with pytest.raises(BlockchainTraceabilityError) as raised:
        service.submit_anchor_job(job)
    assert raised.value.status_code == expected_status
    anchor.refresh_from_db()
    assert anchor.status == LedgerAnchorStatus.FAILED and anchor.failure_code == expected_code
    assert anchor.confirmed_at is None and not anchor.block_hash


def test_anchor_provider_rejection_is_durable_and_retry_resets_failure_evidence(
    ledger: WorkingLedger,
) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    network = active_network(tenant, ledger)
    service = LedgerAnchorService(provider=RejectingLedger())
    anchor, job = service.request_anchor(
        tenant,
        "user",
        {"asset_id": asset.id, "network_id": network.id, "idempotency_key": "reject-me"},
    )

    with pytest.raises(BlockchainTraceabilityError, match="provider policy"):
        service.submit_anchor_job(job)

    anchor.refresh_from_db()
    assert anchor.status == LedgerAnchorStatus.FAILED
    assert anchor.failure_code == "POLICY_REJECTED"
    assert anchor.provider_transaction_id == ""
    retried, retry_job = LedgerAnchorService(provider=ledger).retry_anchor(tenant, anchor.id, "user", "retry-reject")
    assert retried.status == LedgerAnchorStatus.QUEUED
    assert retried.failure_code == ""
    assert retried.async_job_id == retry_job.id
    assert retry_job.id != job.id


def test_anchor_simulated_submission_is_rejected_without_provider_identity(ledger: WorkingLedger) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    network = active_network(tenant, ledger)
    service = LedgerAnchorService(provider=SimulatedLedger())
    anchor, job = service.request_anchor(
        tenant,
        "user",
        {"asset_id": asset.id, "network_id": network.id, "idempotency_key": "simulated-anchor"},
    )

    with pytest.raises(BlockchainTraceabilityError) as raised:
        service.submit_anchor_job(job)

    assert raised.value.error_code == "simulated_provider"
    anchor.refresh_from_db()
    assert anchor.status == LedgerAnchorStatus.FAILED
    assert anchor.failure_code == "SIMULATED_PROVIDER"
    assert anchor.provider_transaction_id == ""


def test_anchor_refresh_and_verify_provider_failures_record_truthful_attempts(ledger: WorkingLedger) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    network = active_network(tenant, ledger)
    service = LedgerAnchorService(provider=ledger)
    anchor, job = service.request_anchor(
        tenant,
        "anchor-user",
        {"asset_id": asset.id, "network_id": network.id, "idempotency_key": "refresh-edge"},
    )
    service.submit_anchor_job(job)

    unavailable = LedgerAnchorService(provider=UnavailableReceiptLedger()).refresh_receipt(tenant, anchor.id, "auditor")
    assert unavailable.status == "unavailable"
    assert unavailable.detail["capability"] == "ledger_receipt"

    invalid = LedgerAnchorService(provider=MismatchedReceiptLedger()).refresh_receipt(tenant, anchor.id, "auditor")
    assert invalid.status == "failed"
    assert invalid.error_code == "INVALID_PROVIDER_RECEIPT"

    negative = LedgerAnchorService(provider=NegativeProofLedger()).verify_anchor(
        tenant, anchor.id, "auditor", "proof-bad"
    )
    assert negative.outcome == VerificationOutcome.INVALID
    assert negative.reason_code == "PROOF_REJECTED"


def test_network_probe_unavailable_persists_health_without_activating(
    ledger: WorkingLedger,
) -> None:
    tenant = uuid.uuid4()
    network_service = LedgerNetworkService()
    network = network_service.create_network(
        tenant,
        "admin",
        {
            "network_key": "unhealthy",
            "name": "Unhealthy ledger",
            "provider_type": ledger.provider_type,
            "dependency_key": "ledger.unhealthy",
            "network_namespace": "saraise:unhealthy",
        },
    )
    prior_status = network.status
    prior_history = list(network.transition_history)
    provider = ledger_provider_registry.unregister(ledger.provider_type)
    ledger_provider_registry.register(ledger.provider_type, UnhealthyLedger())
    try:
        result = network_service.probe_network(tenant, network.id, "admin")
        with pytest.raises(CapabilityUnavailable):
            network_service.activate_network(tenant, network.id, "admin", "activate-unhealthy")
    finally:
        ledger_provider_registry.unregister(ledger.provider_type)
        if provider is not None:
            ledger_provider_registry.register(ledger.provider_type, provider)

    network.refresh_from_db()
    assert result.status == "unavailable"
    assert network.status == prior_status
    assert network.transition_history == prior_history
    assert network.last_health_status == "unavailable"
    assert network.last_health_code == "MAINTENANCE"


def test_verification_attempt_replay_and_conflict_are_explicit() -> None:
    tenant = uuid.uuid4()
    actor = "auditor"
    asset = register_asset(tenant)
    service = VerificationService()
    request = {
        "verification_type": VerificationType.CHAIN,
        "asset": asset,
        "idempotency_key": "verify-once",
        "outcome": VerificationOutcome.INCONCLUSIVE,
        "reason_code": "EMPTY_CHAIN",
        "actor_id": actor,
        "latency_ms": 3,
        "proof_evidence": {"event_count": 0},
    }

    first = service.record_attempt(tenant, request)
    replay = service.record_attempt(tenant, request)
    assert replay.id == first.id
    with pytest.raises(IdempotencyConflictError):
        service.record_attempt(tenant, {**request, "reason_code": "CHAIN_HASH_MISMATCH"})


def test_credential_one_time_token_digest_chain_expiry_and_revoke() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    service = AuthenticityService()
    issued = service.issue_credential(
        tenant,
        asset.id,
        "issuer",
        {"sku": "MED-1"},
        timezone.now() + timedelta(days=1),
    )
    assert issued.token and issued.token not in json.dumps(issued.credential.claims)
    assert issued.token != issued.credential.token_digest and len(issued.credential.token_digest) == 64
    assert not hasattr(issued.credential, "token")
    verified = service.verify_authenticity(tenant, "checker", issued.credential.public_id, issued.token, "auth-1")
    assert verified.outcome == VerificationOutcome.VERIFIED
    invalid = service.verify_authenticity(tenant, "checker", issued.credential.public_id, "wrong-token", "auth-2")
    assert invalid.outcome == VerificationOutcome.NOT_AUTHENTIC
    credential = service.revoke_credential(tenant, issued.credential.id, "issuer", "withdrawn", "revoke")
    assert credential.status == AuthenticityCredentialStatus.REVOKED
    revoked = service.verify_authenticity(tenant, "checker", credential.public_id, issued.token, "auth-3")
    assert revoked.outcome == VerificationOutcome.NOT_AUTHENTIC and revoked.reason_code == "CREDENTIAL_REVOKED"


@pytest.mark.parametrize(
    ("verification", "expected_outcome", "expected_reason"),
    [
        (
            ProviderUnavailableError("issuer unavailable"),
            VerificationOutcome.DEPENDENCY_UNAVAILABLE,
            "ISSUER_UNAVAILABLE",
        ),
        (
            InvalidProviderResponseError("bad proof"),
            VerificationOutcome.INVALID,
            "INVALID_SIGNATURE_EVIDENCE",
        ),
        (
            ProofResult(verified=False, reason_code="SIGNATURE_REJECTED", evidence={"provider": "unit"}),
            VerificationOutcome.NOT_AUTHENTIC,
            "SIGNATURE_REJECTED",
        ),
        (
            ProofResult(verified=False, reason_code="SIMULATED", evidence={"provider": "unit"}, simulated=True),
            VerificationOutcome.INCONCLUSIVE,
            "SIMULATED_PROVIDER",
        ),
    ],
)
def test_authenticity_provider_outcomes_are_recorded_without_claiming_success(
    verification: ProofResult | Exception,
    expected_outcome: str,
    expected_reason: str,
) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    issuer = CredentialIssuer(verification=verification)
    issued = AuthenticityService(issuer_adapter=issuer).issue_credential(
        tenant,
        asset.id,
        "issuer",
        {"sku": "MED-1"},
        timezone.now() + timedelta(days=1),
    )

    attempt = AuthenticityService(issuer_adapter=issuer).verify_authenticity(
        tenant,
        "checker",
        issued.credential.public_id,
        issued.token,
        f"auth-{expected_reason.lower()}",
    )

    assert attempt.outcome == expected_outcome
    assert attempt.reason_code == expected_reason


def test_authenticity_detects_credential_claim_binding_tamper() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    append_event(tenant, asset, "evt")
    issuer = CredentialIssuer()
    issued = AuthenticityService(issuer_adapter=issuer).issue_credential(
        tenant,
        asset.id,
        "issuer",
        {"sku": "MED-1"},
        timezone.now() + timedelta(days=1),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {issued.credential._meta.db_table} SET claims = %s WHERE id = %s",
            [
                json.dumps({"asset_id": str(asset.id), "public_id": "tampered"}),
                issued.credential.id.hex if connection.vendor == "sqlite" else issued.credential.id,
            ],
        )

    attempt = AuthenticityService(issuer_adapter=issuer).verify_authenticity(
        tenant,
        "checker",
        issued.credential.public_id,
        issued.token,
        "auth-claim-binding",
    )

    assert attempt.outcome == VerificationOutcome.INVALID
    assert attempt.reason_code == "CLAIM_BINDING_INVALID"
    assert attempt.proof_evidence["claim_binding"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.pop("validation"),
        lambda document: document.update({"validation": []}),
        lambda document: document["validation"].update({"max_json_bytes": 1}),
        lambda document: document["validation"].update({"gtin_lengths": [7]}),
        lambda document: document["network_policy"].update(
            {"default_confirmation_depth": 3, "max_confirmation_depth": 2}
        ),
        lambda document: document["schema_policy"].update({"allowed_versions": []}),
        lambda document: document["schema_policy"].update({"default_version": 999}),
        lambda document: document["list_policy"].update({"default_page_size": 11, "max_page_size": 10}),
        lambda document: document["inventory_policy"].update({"validation_required": "yes"}),
        lambda document: document["anchor_policy"].update({"use_current_head_default": "yes"}),
        lambda document: document["credential_policy"].update({"issuer_type": ""}),
        lambda document: document["resilience"].update({"timeout_seconds": True}),
        lambda document: document["resilience"].update({"base_backoff_seconds": 2.0, "max_backoff_seconds": 1.0}),
        lambda document: document["workflow"].update({"machines": {}}),
        lambda document: document["workflow"]["machines"]["asset"].update({"states": ["draft"]}),
        lambda document: document["workflow"]["machines"]["asset"].update({"terminal_states": ["unknown"]}),
        lambda document: document["workflow"]["machines"]["asset"].update({"transitions": []}),
        lambda document: document["workflow"]["machines"]["asset"].update(
            {"transitions": [["bad", "draft", "unknown"]]}
        ),
        lambda document: document["workflow"].update({"asset_deletable_statuses": ["missing"]}),
        lambda document: document["ui"].update({"positive_statuses": ["missing"]}),
        lambda document: document["ui"].update({"default_recall_reason": 99}),
        lambda document: document["features"].update({"enabled": "yes"}),
        lambda document: document["features"].update({"roles": ["bad role"]}),
    ],
)
def test_configuration_document_rejects_invalid_policy_branches(mutation) -> None:
    document = json.loads(json.dumps(DEFAULT_CONFIGURATION))
    mutation(document)

    with pytest.raises(BlockchainTraceabilityError) as caught:
        BlockchainTraceabilityConfigurationService.validate_document(document)

    assert caught.value.error_code == "invalid_configuration"


@pytest.mark.parametrize("environment", ["   ", "Prod", "bad_env", "x" * 65])
def test_configuration_environment_is_normalized_and_bounded(environment: str) -> None:
    service = BlockchainTraceabilityConfigurationService()
    if environment == "Prod":
        assert service._environment(environment) == "prod"
    else:
        with pytest.raises(BlockchainTraceabilityError) as caught:
            service._environment(environment)
        assert caught.value.error_code == "invalid_environment"


def test_traceability_validation_helpers_reject_bad_inputs_and_redact_provider_receipts() -> None:
    tenant = uuid.uuid4()

    with pytest.raises(BlockchainTraceabilityError) as uuid_error:
        services._uuid("not-a-uuid", "asset_id")
    assert uuid_error.value.error_code == "validation_error"

    with pytest.raises(BlockchainTraceabilityError):
        _actor("", tenant)
    with pytest.raises(BlockchainTraceabilityError):
        _actor("x" * 1025, tenant)

    with pytest.raises(BlockchainTraceabilityError):
        _data("not-object", allowed={"asset_id"})
    with pytest.raises(BlockchainTraceabilityError):
        _data({"asset_id": "a", "unknown": "b"}, allowed={"asset_id"})
    with pytest.raises(BlockchainTraceabilityError):
        _data({}, allowed={"asset_id"}, required={"asset_id"})

    timeout_failure = _provider_failure(ProviderTimeoutError("late"), "ledger")
    circuit_failure = _provider_failure(ProviderCircuitOpenError("open"), "ledger")
    generic_failure = _provider_failure(ProviderUnavailableError("down"), "ledger")
    assert timeout_failure.public_message == "The provider call timed out."
    assert circuit_failure.public_message == "The provider circuit is open."
    assert generic_failure.error_code == "dependency_unavailable"

    receipt = _safe_receipt(
        {
            "transaction_hash": "0xabc",
            "secret": "remove-me",  # pragma: allowlist secret
            "nested": {"private_key": "remove-me", "public": "keep"},  # pragma: allowlist secret
            "items": [{"token": "remove-me", "value": 1}],  # pragma: allowlist secret
        }
    )
    assert receipt == {"transaction_hash": "0xabc", "nested": {"public": "keep"}, "items": [{"value": 1}]}
    with pytest.raises(InvalidProviderResponseError):
        _safe_receipt(["not", "object"])  # type: ignore[arg-type]


def test_expired_credential_transitions_terminal_and_empty_chain_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    service = AuthenticityService()
    issued = service.issue_credential(tenant, asset.id, "issuer", {}, timezone.now() + timedelta(seconds=1))
    empty = service.verify_authenticity(tenant, "checker", issued.credential.public_id, issued.token, "empty")
    assert empty.outcome == VerificationOutcome.INCONCLUSIVE and empty.reason_code == "EMPTY_CHAIN"
    future_now = issued.credential.expires_at + timedelta(seconds=1)
    monkeypatch.setattr("src.modules.blockchain_traceability.services.timezone.now", lambda: future_now)
    expired = service.verify_authenticity(tenant, "checker", issued.credential.public_id, issued.token, "expired")
    assert expired.reason_code == "CREDENTIAL_EXPIRED"
    issued.credential.refresh_from_db()
    assert issued.credential.status == AuthenticityCredentialStatus.EXPIRED


def test_compliance_finalize_verify_supersede_and_document_tenant_resolution() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    document_ref = uuid.uuid4()
    with pytest.raises(DependencyUnavailableError):
        ComplianceEvidenceService().create_draft(
            tenant,
            "auditor",
            {
                "asset_id": asset.id,
                "evidence_key": "doc-missing-resolver",
                "evidence_type": "certificate",
                "standard": "ISO-1",
                "result": "pass",
                "observed_at": timezone.now(),
                "document_ref": document_ref,
            },
        )
    with pytest.raises(DomainNotFoundError):
        ComplianceEvidenceService(document_resolver=DocumentResolver(False)).create_draft(
            tenant,
            "auditor",
            {
                "asset_id": asset.id,
                "evidence_key": "foreign-doc",
                "evidence_type": "certificate",
                "standard": "ISO-1",
                "result": "pass",
                "observed_at": timezone.now(),
                "document_ref": document_ref,
            },
        )
    service = ComplianceEvidenceService(document_resolver=DocumentResolver(True))
    draft = service.create_draft(
        tenant,
        "auditor",
        {
            "asset_id": asset.id,
            "evidence_key": "cert-1",
            "evidence_type": "certificate",
            "standard": "ISO-1",
            "result": "pass",
            "details": {"lab": "approved"},
            "observed_at": timezone.now(),
            "document_ref": document_ref,
        },
    )
    finalized = service.finalize(tenant, draft.id, "auditor", "finalize")
    assert finalized.status == ComplianceEvidenceStatus.FINALIZED and len(finalized.content_hash) == 64
    attempt = service.verify_evidence(tenant, finalized.id, "auditor", "verify-evidence")
    assert attempt.outcome == VerificationOutcome.VERIFIED
    replacement = service.supersede(
        tenant,
        finalized.id,
        "auditor",
        {
            "evidence_key": "cert-2",
            "evidence_type": "certificate",
            "standard": "ISO-1",
            "result": "warning",
            "observed_at": timezone.now(),
        },
        "supersede",
    )
    finalized.refresh_from_db()
    assert finalized.status == ComplianceEvidenceStatus.SUPERSEDED
    assert replacement.status == ComplianceEvidenceStatus.FINALIZED and replacement.supersedes_id == finalized.id


def test_finalized_compliance_evidence_rejects_draft_mutations_and_can_be_deleted_before_finalize() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    service = ComplianceEvidenceService()
    draft = service.create_draft(
        tenant,
        "auditor",
        {
            "asset_id": asset.id,
            "evidence_key": "draft-delete",
            "evidence_type": "certificate",
            "standard": "ISO-1",
            "result": "pass",
            "observed_at": timezone.now(),
        },
    )
    service.delete_draft(tenant, draft.id, "auditor")
    with pytest.raises(DomainNotFoundError):
        service.get_evidence(tenant, draft.id)

    finalized_draft = service.create_draft(
        tenant,
        "auditor",
        {
            "asset_id": asset.id,
            "evidence_key": "finalized-guard",
            "evidence_type": "certificate",
            "standard": "ISO-1",
            "result": "pass",
            "observed_at": timezone.now(),
        },
    )
    finalized = service.finalize(tenant, finalized_draft.id, "auditor", "finalize-guard")

    with pytest.raises(DomainConflictError) as update_error:
        service.update_draft(tenant, finalized.id, "auditor", {"result": "fail"})
    with pytest.raises(DomainConflictError) as delete_error:
        service.delete_draft(tenant, finalized.id, "auditor")

    assert update_error.value.error_code == "evidence_finalized"
    assert delete_error.value.error_code == "evidence_finalized"


def test_cross_tenant_gets_and_relationship_commands_fail_closed(ledger: WorkingLedger) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    asset_b = register_asset(tenant_b, "asset-b")
    network_a = active_network(tenant_a, ledger)
    with pytest.raises(DomainNotFoundError):
        TraceabilityAssetService().get_asset(tenant_a, asset_b.id)
    with pytest.raises(DomainNotFoundError):
        TraceabilityEventService().append_event(
            tenant_a,
            "user",
            {
                "asset_id": asset_b.id,
                "idempotency_key": "foreign",
                "event_type": "move",
                "occurred_at": timezone.now(),
                "actor_ref": "operator",
            },
        )
    with pytest.raises(DomainNotFoundError):
        LedgerAnchorService(provider=ledger).request_anchor(
            tenant_a,
            "user",
            {"asset_id": asset_b.id, "network_id": network_a.id, "idempotency_key": "foreign-anchor"},
        )


@pytest.mark.skipif(connection.vendor != "postgresql", reason="real concurrent row locks require PostgreSQL gate")
def test_concurrent_append_allocates_unique_monotonic_sequences() -> None:
    tenant = uuid.uuid4()
    asset = register_asset(tenant)
    barrier = threading.Barrier(2)
    results: list[int] = []

    def worker(key: str) -> None:
        barrier.wait()
        results.append(append_event(tenant, asset, key).sequence)

    threads = [threading.Thread(target=worker, args=(f"concurrent-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [1, 2]

"""Transactional domain-flow, cryptographic, and failure-semantics tests."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, JobTransition, OutboxEvent

from ..hashing import CanonicalizationError, compute_event_hash, compute_merkle_root
from ..models import (
    AuthenticityCredentialStatus,
    ComplianceEvidenceStatus,
    ImmutableEvidenceError,
    LedgerAnchor,
    LedgerAnchorStatus,
    LedgerNetworkStatus,
    LifecycleTransition,
    MutationIdempotencyRecord,
    TraceabilityAsset,
    TraceabilityAssetStatus,
    TraceabilityEvent,
    VerificationOutcome,
)
from ..providers import (
    AnchorReceipt,
    CapabilityMetadata,
    DocumentReferenceResult,
    InvalidProviderResponseError,
    ProofResult,
    ProviderHealth,
    ProviderTimeoutError,
    SubmissionReceipt,
    ledger_provider_registry,
)
from ..services import (
    AuthenticityService,
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


class DocumentResolver:
    resolver_type = "default"

    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key="default", display_name="DMS resolver")

    def validate_reference(self, tenant_id: uuid.UUID, document_ref: uuid.UUID) -> DocumentReferenceResult:
        return DocumentReferenceResult(valid=self.valid, reason_code="FOUND" if self.valid else "NOT_FOUND")


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

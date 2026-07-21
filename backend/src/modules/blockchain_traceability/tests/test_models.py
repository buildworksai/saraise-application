"""Persistence invariants for every traceability entity."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel

from ..models import (
    AuthenticityCredential,
    AuthenticityCredentialStatus,
    ComplianceEvidence,
    ComplianceEvidenceStatus,
    ImmutableEvidenceError,
    LedgerAnchor,
    LedgerAnchorStatus,
    LedgerNetwork,
    TraceabilityAsset,
    TraceabilityEvent,
    VerificationAttempt,
    VerificationOutcome,
    VerificationType,
)
from .factories import make_anchor, make_asset, make_credential, make_evidence, make_network

pytestmark = pytest.mark.django_db


def test_all_seven_models_use_uuid_tenant_ownership_and_explicit_tables() -> None:
    models = (
        LedgerNetwork,
        TraceabilityAsset,
        TraceabilityEvent,
        LedgerAnchor,
        AuthenticityCredential,
        ComplianceEvidence,
        VerificationAttempt,
    )
    assert len(models) == 7
    for model in models:
        assert issubclass(model, TenantScopedModel)
        assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
        assert model._meta.get_field("tenant_id").db_index is True
        assert model._meta.pk.get_internal_type() == "UUIDField"
        assert model._meta.db_table.startswith("blockchain_traceability_")
        assert any("tenant_id" in index.fields for index in model._meta.indexes)


def test_mutable_defaults_are_real_empty_objects_and_lists() -> None:
    tenant = uuid.uuid4()
    network = make_network(tenant)
    asset = make_asset(tenant)
    evidence = make_evidence(tenant, asset)
    assert network.confirmation_depth == 1
    assert network.provider_options == {} and network.transition_history == []
    assert network.supports_batch_anchors is False and network.supports_finality is True
    assert asset.head_sequence == 0 and asset.head_hash == ""
    assert asset.attributes == {} and asset.transition_history == []
    assert evidence.details == {} and evidence.transition_history == []
    assert not network.is_deleted and not asset.is_deleted and not evidence.is_deleted


def test_network_rejects_blank_dependency_secret_options_urls_and_duplicate_key() -> None:
    tenant = uuid.uuid4()
    with pytest.raises(ValidationError):
        make_network(tenant, dependency_key="")
    with pytest.raises(ValidationError):
        make_network(tenant, provider_options={"api_token": "unsafe"})
    with pytest.raises(ValidationError):
        make_network(tenant, provider_options={"endpoint": "https://provider.invalid"})
    first = make_network(tenant, network_key="primary")
    with pytest.raises(ValidationError):
        make_network(tenant, network_key=first.network_key)
    make_network(uuid.uuid4(), network_key=first.network_key)


def test_asset_reference_head_gtin_and_unique_constraints() -> None:
    tenant = uuid.uuid4()
    with pytest.raises(ValidationError):
        make_asset(tenant, serial_number="")
    with pytest.raises(ValidationError):
        make_asset(tenant, gtin="not-digits", serial_number="")
    with pytest.raises(ValidationError):
        make_asset(tenant, head_sequence=1, head_hash="bad")
    first = make_asset(tenant, asset_key="same-key")
    with pytest.raises(ValidationError):
        make_asset(tenant, asset_key=first.asset_key)


def test_append_only_event_rejects_instance_and_queryset_mutation() -> None:
    tenant = uuid.uuid4()
    asset = make_asset(tenant)
    event = TraceabilityEvent.objects.create(
        tenant_id=tenant,
        asset=asset,
        sequence=1,
        idempotency_key="event-1",
        event_type="manufactured",
        occurred_at=timezone.now(),
        actor_ref="operator:1",
        event_hash="a" * 64,
        created_by="user:1",
        correlation_id=str(uuid.uuid4()),
    )
    assert event.location == {} and event.payload == {} and event.hash_algorithm == "sha256"
    event.actor_ref = "tampered"
    with pytest.raises(ImmutableEvidenceError):
        event.save()
    with pytest.raises(ImmutableEvidenceError):
        event.delete()
    with pytest.raises(ImmutableEvidenceError):
        TraceabilityEvent.objects.filter(pk=event.pk).update(actor_ref="tampered")
    with pytest.raises(ImmutableEvidenceError):
        TraceabilityEvent.objects.filter(pk=event.pk).delete()


def test_event_sequence_previous_hash_and_cross_tenant_relationship_are_rejected() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    asset_b = make_asset(tenant_b)
    common = {
        "tenant_id": tenant_a,
        "asset": asset_b,
        "sequence": 1,
        "idempotency_key": "cross",
        "event_type": "move",
        "occurred_at": timezone.now(),
        "actor_ref": "operator",
        "event_hash": "a" * 64,
        "created_by": "creator",
        "correlation_id": str(uuid.uuid4()),
    }
    with pytest.raises(ValidationError):
        TraceabilityEvent.objects.create(**common)
    asset_a = make_asset(tenant_a)
    with pytest.raises(ValidationError):
        TraceabilityEvent.objects.create(**{**common, "asset": asset_a, "sequence": 2, "previous_hash": ""})


def test_anchor_range_cross_tenant_confirmation_and_terminal_immutability() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    asset = make_asset(tenant_a)
    network = make_network(tenant_a, confirmation_depth=2)
    with pytest.raises(ValidationError):
        make_anchor(tenant_a, asset, network, start_sequence=2, end_sequence=1)
    with pytest.raises(ValidationError):
        make_anchor(tenant_b, asset, make_network(tenant_b))
    anchor = make_anchor(tenant_a, asset, network)
    anchor.status = LedgerAnchorStatus.CONFIRMED
    anchor.provider_transaction_id = "tx-1"
    anchor.block_number = 10
    anchor.block_hash = "block-10"
    anchor.confirmations = 2
    anchor.confirmed_at = timezone.now()
    anchor.save()
    anchor.failure_message = "tamper"
    with pytest.raises(ImmutableEvidenceError):
        anchor.save()
    with pytest.raises(ImmutableEvidenceError):
        LedgerAnchor.objects.filter(pk=anchor.pk).update(confirmations=3)


def test_credential_expiry_hashes_cross_tenant_and_terminal_state() -> None:
    tenant = uuid.uuid4()
    asset = make_asset(tenant)
    with pytest.raises(ValidationError):
        make_credential(tenant, asset, expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        make_credential(tenant, asset, token_digest="not-a-hash")
    with pytest.raises(ValidationError):
        make_credential(uuid.uuid4(), asset)
    credential = make_credential(tenant, asset)
    credential.status = AuthenticityCredentialStatus.REVOKED
    credential.revoked_at = timezone.now()
    credential.save()
    credential.revocation_reason = "changed"
    with pytest.raises(ImmutableEvidenceError):
        credential.save()
    assert "redacted-signature-evidence" not in str(credential)


def test_finalized_evidence_content_and_relationships_are_immutable() -> None:
    tenant = uuid.uuid4()
    asset = make_asset(tenant)
    evidence = make_evidence(tenant, asset)
    evidence.content_hash = "d" * 64
    evidence.finalized_at = timezone.now()
    evidence.status = ComplianceEvidenceStatus.FINALIZED
    evidence.save()
    evidence.details = {"tampered": True}
    with pytest.raises(ImmutableEvidenceError):
        evidence.save()
    with pytest.raises(ImmutableEvidenceError):
        ComplianceEvidence.objects.filter(pk=evidence.pk).update(details={})
    with pytest.raises(ImmutableEvidenceError):
        evidence.delete()
    other_tenant_asset = make_asset(uuid.uuid4())
    with pytest.raises(ValidationError):
        make_evidence(tenant, other_tenant_asset)


def test_verification_attempt_requires_target_evidence_and_rejects_raw_sources() -> None:
    tenant = uuid.uuid4()
    asset = make_asset(tenant)
    base = {
        "tenant_id": tenant,
        "verification_type": VerificationType.CHAIN,
        "asset": asset,
        "idempotency_key": "verify-1",
        "outcome": VerificationOutcome.VERIFIED,
        "reason_code": "CHAIN_VALID",
        "proof_evidence": {"event_count": 1},
        "actor_id": "auditor",
        "correlation_id": str(uuid.uuid4()),
        "latency_ms": 2,
    }
    attempt = VerificationAttempt.objects.create(**base)
    assert attempt.created_at is not None
    with pytest.raises(ImmutableEvidenceError):
        attempt.save()
    with pytest.raises(ValidationError):
        VerificationAttempt.objects.create(**{**base, "idempotency_key": "verify-2", "asset": None})
    for proof in ({"source_ip": "192.0.2.1"}, {"provider_url": "https://ledger.invalid/proof"}):
        with pytest.raises(ValidationError):
            VerificationAttempt.objects.create(
                **{
                    **base,
                    "idempotency_key": str(uuid.uuid4()),
                    "outcome": VerificationOutcome.INVALID,
                    "proof_evidence": proof,
                }
            )
    with pytest.raises(ValidationError):
        VerificationAttempt.objects.create(
            **{
                **base,
                "idempotency_key": "simulated",
                "outcome": VerificationOutcome.VERIFIED,
                "reason_code": "SIMULATED_PROVIDER",
            }
        )


def test_database_unique_constraint_remains_race_authority() -> None:
    tenant = uuid.uuid4()
    asset = make_asset(tenant)
    # bulk_create bypasses model full_clean, proving the database constraint is real.
    duplicate = TraceabilityAsset(
        tenant_id=tenant,
        asset_key=asset.asset_key,
        name="Duplicate",
        serial_number="duplicate",
        asset_type="serialized_product",
        created_by="creator",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        TraceabilityAsset.objects.bulk_create([duplicate])

"""Small deterministic domain factories shared by focused tests."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.utils import timezone

from ..models import (
    AuthenticityCredential,
    ComplianceEvidence,
    LedgerAnchor,
    LedgerNetwork,
    TraceabilityAsset,
)


def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


def make_network(tenant: uuid.UUID, **overrides: Any) -> LedgerNetwork:
    values = {
        "tenant_id": tenant,
        "network_key": f"network-{uuid.uuid4().hex[:8]}",
        "name": "Production ledger",
        "provider_type": "test-ledger",
        "dependency_key": "ledger.test",
        "network_namespace": "saraise:test",
        "created_by": "user:creator",
    }
    values.update(overrides)
    return LedgerNetwork.objects.create(**values)


def make_asset(tenant: uuid.UUID, **overrides: Any) -> TraceabilityAsset:
    values = {
        "tenant_id": tenant,
        "asset_key": f"asset-{uuid.uuid4().hex[:10]}",
        "name": "Traceable product",
        "serial_number": uuid.uuid4().hex[:16],
        "asset_type": "serialized_product",
        "created_by": "user:creator",
    }
    values.update(overrides)
    return TraceabilityAsset.objects.create(**values)


def make_anchor(tenant: uuid.UUID, asset: TraceabilityAsset, network: LedgerNetwork, **overrides: Any) -> LedgerAnchor:
    values = {
        "tenant_id": tenant,
        "asset": asset,
        "network": network,
        "start_sequence": 1,
        "end_sequence": 1,
        "root_hash": "a" * 64,
        "idempotency_key": f"anchor-{uuid.uuid4()}",
        "created_by": "user:creator",
    }
    values.update(overrides)
    return LedgerAnchor.objects.create(**values)


def make_credential(tenant: uuid.UUID, asset: TraceabilityAsset, **overrides: Any) -> AuthenticityCredential:
    now = timezone.now()
    values = {
        "tenant_id": tenant,
        "asset": asset,
        "public_id": str(uuid.uuid4()),
        "credential_type": "django_signing_v1",
        "token_digest": "b" * 64,
        "claims": {"asset_id": str(asset.id)},
        "claims_hash": "c" * 64,
        "signature_algorithm": "hmac-sha256",
        "issuer_key_ref": "django:secret-key:v1",
        "signature": "redacted-signature-evidence",
        "issued_at": now,
        "expires_at": now + timedelta(days=1),
        "created_by": "user:creator",
    }
    values.update(overrides)
    return AuthenticityCredential.objects.create(**values)


def make_evidence(tenant: uuid.UUID, asset: TraceabilityAsset, **overrides: Any) -> ComplianceEvidence:
    values = {
        "tenant_id": tenant,
        "asset": asset,
        "evidence_key": f"evidence-{uuid.uuid4().hex[:10]}",
        "evidence_type": "inspection",
        "standard": "ISO-TEST",
        "result": "pass",
        "observed_at": timezone.now(),
        "created_by": "user:creator",
    }
    values.update(overrides)
    return ComplianceEvidence.objects.create(**values)

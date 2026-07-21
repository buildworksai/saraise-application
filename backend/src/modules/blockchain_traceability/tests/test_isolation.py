"""Black-box tenant isolation for every mutable traceability boundary."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.async_jobs.models import AsyncJob
from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.blockchain_traceability.api import ComplianceEvidenceViewSet
from src.modules.blockchain_traceability.models import (
    AuthenticityCredential,
    ComplianceEvidence,
    LedgerAnchor,
    LedgerNetwork,
    TraceabilityAsset,
    TraceabilityEvent,
    VerificationAttempt,
)
from src.modules.blockchain_traceability.providers import CapabilityMetadata, DocumentReferenceResult
from src.modules.blockchain_traceability.services import LedgerAnchorService, SUBMIT_ANCHOR_COMMAND

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep real session/CSRF authentication while replacing remote policy IO."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows declared capability",
            tenant_id=UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def create_network(tenant_id, suffix: str) -> LedgerNetwork:
    return LedgerNetwork.objects.create(
        tenant_id=tenant_id,
        network_key=f"network-{suffix}-{uuid4().hex[:6]}",
        name=f"Network {suffix}",
        provider_type="isolation-provider",
        dependency_key=f"traceability.isolation.{suffix}",
        network_namespace=f"isolation-{suffix}",
        created_by="isolation-test",
    )


def create_asset(tenant_id, suffix: str) -> TraceabilityAsset:
    return TraceabilityAsset.objects.create(
        tenant_id=tenant_id,
        asset_key=f"asset-{suffix}-{uuid4().hex[:6]}",
        name=f"Asset {suffix}",
        serial_number=f"SERIAL-{suffix}-{uuid4().hex[:6]}",
        asset_type="serialized_product",
        created_by="isolation-test",
    )


def create_evidence(tenant_id, asset: TraceabilityAsset, suffix: str) -> ComplianceEvidence:
    return ComplianceEvidence.objects.create(
        tenant_id=tenant_id,
        asset=asset,
        evidence_key=f"evidence-{suffix}-{uuid4().hex[:6]}",
        evidence_type="certificate",
        standard="ISO-TEST",
        result="pass",
        observed_at=timezone.now(),
        created_by="isolation-test",
    )


def create_event(tenant_id, asset: TraceabilityAsset, suffix: str) -> TraceabilityEvent:
    return TraceabilityEvent.objects.create(
        tenant_id=tenant_id,
        asset=asset,
        sequence=1,
        idempotency_key=f"event-{suffix}-{uuid4()}",
        event_type="inspection",
        occurred_at=timezone.now(),
        actor_ref="partner:isolation",
        previous_hash="",
        event_hash=sha256(f"event:{suffix}:{uuid4()}".encode()).hexdigest(),
        created_by="isolation-test",
        correlation_id=f"isolation-{uuid4()}",
    )


def create_anchor(tenant_id, asset: TraceabilityAsset, network: LedgerNetwork, suffix: str) -> LedgerAnchor:
    return LedgerAnchor.objects.create(
        tenant_id=tenant_id,
        asset=asset,
        network=network,
        start_sequence=1,
        end_sequence=1,
        root_hash=sha256(f"anchor:{suffix}:{uuid4()}".encode()).hexdigest(),
        idempotency_key=f"anchor-{suffix}-{uuid4()}",
        created_by="isolation-test",
    )


def create_credential(tenant_id, asset: TraceabilityAsset, suffix: str, raw_token: str) -> AuthenticityCredential:
    public_id = f"credential-{suffix}-{uuid4()}"
    return AuthenticityCredential.objects.create(
        tenant_id=tenant_id,
        asset=asset,
        public_id=public_id,
        credential_type="isolation-issuer",
        token_digest=sha256(raw_token.encode()).hexdigest(),
        claims={"asset_id": str(asset.id), "public_id": public_id},
        claims_hash=sha256(f"claims:{suffix}:{uuid4()}".encode()).hexdigest(),
        signature_algorithm="ed25519",
        issuer_key_ref="issuer://isolation-test",
        signature="opaque-signature",
        issued_at=timezone.now(),
        created_by="isolation-test",
    )


class V2IsolationContract(TenantIsolationContract):
    """Teach the shared contract how to read the governed v2 envelope."""

    def get_list_items(self, response):
        return response.json()["data"]


class TestLedgerNetworkIsolation(V2IsolationContract):
    model = LedgerNetwork
    list_url = "/api/v2/blockchain-traceability/networks/"
    detail_url_template = "/api/v2/blockchain-traceability/networks/{pk}/"
    create_payload = {
        "network_key": "spoofed-network",
        "name": "Spoofed network",
        "provider_type": "isolation-provider",
        "dependency_key": "traceability.isolation.spoof",
        "network_namespace": "spoof",
    }
    update_payload = {"name": "Cross-tenant overwrite"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = create_network(tenant_a.id, "a")
        self.tenant_b_row = create_network(tenant_b.id, "b")


class TestTraceabilityAssetIsolation(V2IsolationContract):
    model = TraceabilityAsset
    list_url = "/api/v2/blockchain-traceability/assets/"
    detail_url_template = "/api/v2/blockchain-traceability/assets/{pk}/"
    create_payload = {
        "asset_key": "spoofed-asset",
        "name": "Spoofed asset",
        "serial_number": "SERIAL-SPOOF",
        "asset_type": "serialized_product",
    }
    update_payload = {"name": "Cross-tenant overwrite"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = create_asset(tenant_a.id, "a")
        self.tenant_b_row = create_asset(tenant_b.id, "b")


class TestComplianceEvidenceIsolation(V2IsolationContract):
    model = ComplianceEvidence
    list_url = "/api/v2/blockchain-traceability/compliance-evidence/"
    detail_url_template = "/api/v2/blockchain-traceability/compliance-evidence/{pk}/"
    update_payload = {"standard": "CROSS-TENANT-OVERWRITE"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        asset_a = create_asset(tenant_a.id, "evidence-a")
        asset_b = create_asset(tenant_b.id, "evidence-b")
        self.tenant_a_row = create_evidence(tenant_a.id, asset_a, "a")
        self.tenant_b_row = create_evidence(tenant_b.id, asset_b, "b")
        self.create_payload = {
            "asset_id": str(asset_a.id),
            "evidence_key": f"spoofed-{uuid4().hex[:8]}",
            "evidence_type": "certificate",
            "standard": "ISO-TEST",
            "result": "pass",
            "observed_at": timezone.now().isoformat(),
        }


@pytest.fixture
def cross_tenant_assets(tenant_a, tenant_b):
    return create_asset(tenant_a.id, "explicit-a"), create_asset(tenant_b.id, "explicit-b")


def test_event_append_cannot_reference_another_tenants_asset(
    authenticated_tenant_a_client, cross_tenant_assets
) -> None:
    _, asset_b = cross_tenant_assets
    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/events/",
        {
            "asset_id": str(asset_b.id),
            "idempotency_key": f"event-{uuid4()}",
            "event_type": "shipment",
            "occurred_at": timezone.now().isoformat(),
            "actor_ref": "partner:test",
            "location": {},
            "payload": {},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_anchor_cannot_combine_cross_tenant_asset_and_network(
    authenticated_tenant_a_client, tenant_a, tenant_b, cross_tenant_assets
) -> None:
    asset_a, asset_b = cross_tenant_assets
    network_a = create_network(tenant_a.id, "anchor-a")
    network_b = create_network(tenant_b.id, "anchor-b")
    for asset_id, network_id in ((asset_b.id, network_a.id), (asset_a.id, network_b.id)):
        response = authenticated_tenant_a_client.post(
            "/api/v2/blockchain-traceability/anchors/",
            {
                "asset_id": str(asset_id),
                "network_id": str(network_id),
                "start_sequence": 1,
                "end_sequence": 1,
                "idempotency_key": f"anchor-{uuid4()}",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


def test_credential_issue_cannot_reference_another_tenants_asset(
    authenticated_tenant_a_client, cross_tenant_assets
) -> None:
    _, asset_b = cross_tenant_assets
    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/credentials/",
        {"asset_id": str(asset_b.id), "claims": {"sku": "private"}},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_compliance_cannot_reference_another_tenants_asset(authenticated_tenant_a_client, cross_tenant_assets) -> None:
    _, asset_b = cross_tenant_assets
    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/compliance-evidence/",
        {
            "asset_id": str(asset_b.id),
            "evidence_key": f"cross-{uuid4()}",
            "evidence_type": "certificate",
            "standard": "ISO-TEST",
            "result": "pass",
            "observed_at": timezone.now().isoformat(),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("post", "activate/", {"transition_key": "cross-activate"}),
        ("post", "recall/", {"transition_key": "cross-recall", "reason": "test"}),
        ("post", "release-recall/", {"transition_key": "cross-release"}),
        ("post", "retire/", {"transition_key": "cross-retire"}),
        ("post", "verify-chain/", {"idempotency_key": "cross-verify"}),
        ("get", "history/", None),
    ],
)
def test_asset_actions_and_history_hide_cross_tenant_ids(
    authenticated_tenant_a_client,
    cross_tenant_assets,
    method,
    suffix,
    payload,
) -> None:
    _, asset_b = cross_tenant_assets
    url = f"/api/v2/blockchain-traceability/assets/{asset_b.id}/{suffix}"
    request_method = getattr(authenticated_tenant_a_client, method)
    response = request_method(url, payload, format="json") if payload is not None else request_method(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cross_tenant_denials_leave_target_byte_for_byte_unchanged(
    authenticated_tenant_a_client, cross_tenant_assets
) -> None:
    _, asset_b = cross_tenant_assets
    before = TraceabilityAsset.objects.filter(pk=asset_b.pk).values().get()
    authenticated_tenant_a_client.patch(
        f"/api/v2/blockchain-traceability/assets/{asset_b.id}/",
        {"name": "tampered"},
        format="json",
    )
    authenticated_tenant_a_client.delete(f"/api/v2/blockchain-traceability/assets/{asset_b.id}/")
    after = TraceabilityAsset.objects.filter(pk=asset_b.pk).values().get()
    assert after == before


def test_compliance_cannot_reference_another_tenants_event(authenticated_tenant_a_client, tenant_a, tenant_b) -> None:
    asset_a = create_asset(tenant_a.id, "event-ref-a")
    asset_b = create_asset(tenant_b.id, "event-ref-b")
    event_b = create_event(tenant_b.id, asset_b, "event-ref-b")
    before = TraceabilityEvent.objects.filter(pk=event_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/compliance-evidence/",
        {
            "asset_id": str(asset_a.id),
            "event_id": str(event_b.id),
            "evidence_key": f"cross-event-{uuid4()}",
            "evidence_type": "certificate",
            "standard": "ISO-TEST",
            "result": "pass",
            "observed_at": timezone.now().isoformat(),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert TraceabilityEvent.objects.filter(pk=event_b.pk).values().get() == before


def test_compliance_create_rejects_client_supplied_cross_tenant_supersedes(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    asset_a = create_asset(tenant_a.id, "supersedes-a")
    asset_b = create_asset(tenant_b.id, "supersedes-b")
    evidence_b = create_evidence(tenant_b.id, asset_b, "supersedes-b")
    before = ComplianceEvidence.objects.filter(pk=evidence_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/compliance-evidence/",
        {
            "asset_id": str(asset_a.id),
            "supersedes_id": str(evidence_b.id),
            "evidence_key": f"cross-supersedes-{uuid4()}",
            "evidence_type": "certificate",
            "standard": "ISO-TEST",
            "result": "pass",
            "observed_at": timezone.now().isoformat(),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert ComplianceEvidence.objects.filter(pk=evidence_b.pk).values().get() == before


def test_compliance_document_reference_is_validated_in_request_tenant(
    monkeypatch, authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    document_b = uuid4()
    calls: list[tuple[UUID, UUID]] = []

    class TenantAwareDocumentResolver:
        resolver_type = "isolation-document-resolver"

        def capability_metadata(self) -> CapabilityMetadata:
            return CapabilityMetadata(key=self.resolver_type, display_name="Isolation document resolver")

        def validate_reference(self, tenant_id: UUID, document_ref: UUID) -> DocumentReferenceResult:
            calls.append((tenant_id, document_ref))
            return DocumentReferenceResult(valid=tenant_id == tenant_b.id and document_ref == document_b)

    monkeypatch.setattr(
        ComplianceEvidenceViewSet.service,
        "document_resolver",
        TenantAwareDocumentResolver(),
    )
    asset_a = create_asset(tenant_a.id, "document-ref-a")

    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/compliance-evidence/",
        {
            "asset_id": str(asset_a.id),
            "document_ref": str(document_b),
            "evidence_key": f"cross-document-{uuid4()}",
            "evidence_type": "certificate",
            "standard": "ISO-TEST",
            "result": "pass",
            "observed_at": timezone.now().isoformat(),
        },
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert calls == [(tenant_a.id, document_b)]
    assert not ComplianceEvidence.objects.filter(tenant_id=tenant_a.id, document_ref=document_b).exists()


def test_authenticity_verification_does_not_discover_another_tenants_credential(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    asset_b = create_asset(tenant_b.id, "credential-verify-b")
    raw_token = f"cross-tenant-token-{uuid4()}"
    credential_b = create_credential(tenant_b.id, asset_b, "verify-b", raw_token)
    before = AuthenticityCredential.objects.filter(pk=credential_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/credentials/verify/",
        {
            "public_id": credential_b.public_id,
            "token": raw_token,
            "idempotency_key": f"cross-credential-{uuid4()}",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()["data"]
    assert payload["tenant_id"] == str(tenant_a.id)
    assert payload["credential_id"] is None
    assert payload["outcome"] == "not_authentic"
    assert payload["reason_code"] == "CREDENTIAL_NOT_FOUND"
    assert raw_token not in repr(payload)
    assert AuthenticityCredential.objects.filter(pk=credential_b.pk).values().get() == before
    assert not VerificationAttempt.objects.filter(tenant_id=tenant_a.id, credential_id=credential_b.id).exists()


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        ("refresh/", {}),
        ("retry/", {"transition_key": "cross-retry"}),
        ("verify/", {"idempotency_key": "cross-anchor-proof"}),
    ],
)
def test_anchor_provider_and_proof_actions_hide_cross_tenant_anchors(
    authenticated_tenant_a_client, tenant_b, suffix, payload
) -> None:
    action_name = suffix.rstrip("/")
    asset_b = create_asset(tenant_b.id, f"anchor-action-{action_name}")
    network_b = create_network(tenant_b.id, f"anchor-action-{action_name}")
    anchor_b = create_anchor(tenant_b.id, asset_b, network_b, f"anchor-action-{action_name}")
    before = LedgerAnchor.objects.filter(pk=anchor_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        f"/api/v2/blockchain-traceability/anchors/{anchor_b.id}/{suffix}", payload, format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert LedgerAnchor.objects.filter(pk=anchor_b.pk).values().get() == before
    assert not VerificationAttempt.objects.filter(anchor_id=anchor_b.id).exists()


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        ("finalize/", {"transition_key": "cross-finalize"}),
        (
            "supersede/",
            {
                "transition_key": "cross-supersede",
                "evidence_key": "replacement-cross",
                "evidence_type": "certificate",
                "standard": "ISO-TEST",
                "result": "pass",
                "observed_at": "2026-01-01T00:00:00Z",
                "asset_id": str(uuid4()),
            },
        ),
        ("verify/", {"idempotency_key": "cross-evidence-proof"}),
    ],
)
def test_compliance_proof_actions_hide_cross_tenant_evidence(
    authenticated_tenant_a_client, tenant_b, suffix, payload
) -> None:
    asset_b = create_asset(tenant_b.id, f"evidence-action-{suffix}")
    evidence_b = create_evidence(tenant_b.id, asset_b, f"evidence-action-{suffix}")
    before = ComplianceEvidence.objects.filter(pk=evidence_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        f"/api/v2/blockchain-traceability/compliance-evidence/{evidence_b.id}/{suffix}",
        payload,
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert ComplianceEvidence.objects.filter(pk=evidence_b.pk).values().get() == before
    assert not VerificationAttempt.objects.filter(compliance_evidence_id=evidence_b.id).exists()


def test_async_job_handler_rejects_foreign_anchor_payload_without_mutation(tenant_a, tenant_b) -> None:
    asset_b = create_asset(tenant_b.id, "job-b")
    network_b = create_network(tenant_b.id, "job-b")
    anchor_b = create_anchor(tenant_b.id, asset_b, network_b, "job-b")
    job_a = AsyncJob.objects.create(
        tenant_id=tenant_a.id,
        actor_id="isolation-test",
        command=SUBMIT_ANCHOR_COMMAND,
        idempotency_key=f"cross-job-{uuid4()}",
        payload={"anchor_id": str(anchor_b.id), "tenant_id": str(tenant_b.id)},
        correlation_id=f"cross-job-{uuid4()}",
    )
    before = LedgerAnchor.objects.filter(pk=anchor_b.pk).values().get()

    with pytest.raises(LedgerAnchor.DoesNotExist):
        LedgerAnchorService().submit_anchor_job(job_a)

    assert LedgerAnchor.objects.filter(pk=anchor_b.pk).values().get() == before


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        ("activate/", {"transition_key": "cross-network-activate"}),
        ("disable/", {"transition_key": "cross-network-disable"}),
        ("probe/", {}),
    ],
)
def test_network_state_and_provider_actions_hide_cross_tenant_networks(
    authenticated_tenant_a_client, tenant_b, suffix, payload
) -> None:
    network_b = create_network(tenant_b.id, f"network-action-{suffix.rstrip('/')}")
    before = LedgerNetwork.objects.filter(pk=network_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        f"/api/v2/blockchain-traceability/networks/{network_b.id}/{suffix}", payload, format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert LedgerNetwork.objects.filter(pk=network_b.pk).values().get() == before


def test_credential_revoke_hides_cross_tenant_credential(authenticated_tenant_a_client, tenant_b) -> None:
    asset_b = create_asset(tenant_b.id, "credential-revoke-b")
    credential_b = create_credential(tenant_b.id, asset_b, "revoke-b", f"token-{uuid4()}")
    before = AuthenticityCredential.objects.filter(pk=credential_b.pk).values().get()

    response = authenticated_tenant_a_client.post(
        f"/api/v2/blockchain-traceability/credentials/{credential_b.id}/revoke/",
        {"reason": "cross-tenant attempt", "transition_key": "cross-revoke"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert AuthenticityCredential.objects.filter(pk=credential_b.pk).values().get() == before

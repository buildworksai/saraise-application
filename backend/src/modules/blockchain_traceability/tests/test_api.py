"""Contract tests for the governed traceability API v2 boundary."""

from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.api.results import OperationResult
from src.modules.blockchain_traceability import serializers
from src.modules.blockchain_traceability.api import (
    AuthenticityCredentialViewSet,
    ComplianceEvidenceViewSet,
    LedgerAnchorViewSet,
    LedgerNetworkViewSet,
    TraceabilityAssetViewSet,
    TraceabilityEventViewSet,
    VerificationAttemptViewSet,
)
from src.modules.blockchain_traceability.models import (
    AuthenticityCredential,
    LedgerAnchor,
    LedgerNetwork,
    TraceabilityAsset,
    TraceabilityEvent,
)
from src.modules.blockchain_traceability.permissions import PERMISSIONS
from src.modules.blockchain_traceability.providers import ProviderHealth
from src.modules.blockchain_traceability.services import AssetHistory, AssetHistoryItem

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _network(tenant_id, suffix: str, *, status_value: str = "draft") -> LedgerNetwork:
    return LedgerNetwork.objects.create(
        tenant_id=tenant_id,
        network_key=f"network-{suffix}-{uuid4().hex[:6]}",
        name=f"Network {suffix}",
        provider_type="test-ledger",
        dependency_key=f"traceability.test.{suffix}",
        network_namespace="test",
        status=status_value,
        created_by="api-test",
    )


def _asset(tenant_id, suffix: str) -> TraceabilityAsset:
    return TraceabilityAsset.objects.create(
        tenant_id=tenant_id,
        asset_key=f"asset-{suffix}-{uuid4().hex[:6]}",
        name=f"Asset {suffix}",
        serial_number=f"SERIAL-{suffix}-{uuid4().hex[:6]}",
        asset_type="serialized_product",
        created_by="api-test",
    )


def _credential(tenant_id, asset: TraceabilityAsset) -> AuthenticityCredential:
    return AuthenticityCredential.objects.create(
        tenant_id=tenant_id,
        asset=asset,
        public_id=f"cred-{uuid4()}",
        credential_type="test-issuer",
        token_digest="a" * 64,
        claims={"sku": "SKU-1"},
        claims_hash="b" * 64,
        signature_algorithm="ed25519",
        issuer_key_ref="issuer://test",
        signature="signed-claims",
        issued_at=timezone.now(),
        created_by="api-test",
    )


REQUIRED_SERIALIZERS = {
    "LedgerNetworkListSerializer",
    "LedgerNetworkDetailSerializer",
    "LedgerNetworkCreateSerializer",
    "LedgerNetworkUpdateSerializer",
    "TraceabilityAssetListSerializer",
    "TraceabilityAssetDetailSerializer",
    "TraceabilityAssetCreateSerializer",
    "TraceabilityAssetUpdateSerializer",
    "TraceabilityEventListSerializer",
    "TraceabilityEventDetailSerializer",
    "TraceabilityEventCreateSerializer",
    "LedgerAnchorListSerializer",
    "LedgerAnchorDetailSerializer",
    "LedgerAnchorCreateSerializer",
    "AuthenticityCredentialListSerializer",
    "AuthenticityCredentialDetailSerializer",
    "AuthenticityCredentialIssueSerializer",
    "CredentialRevokeSerializer",
    "AuthenticityVerificationSerializer",
    "ComplianceEvidenceListSerializer",
    "ComplianceEvidenceDetailSerializer",
    "ComplianceEvidenceCreateSerializer",
    "ComplianceEvidenceUpdateSerializer",
    "EvidenceSupersedeSerializer",
    "VerificationAttemptListSerializer",
    "VerificationAttemptDetailSerializer",
    "ChainVerificationSerializer",
}


def test_all_operation_specific_serializers_exist() -> None:
    assert REQUIRED_SERIALIZERS.issubset(set(dir(serializers)))


def test_unknown_server_owned_and_unbounded_json_fields_are_rejected(tenant_b) -> None:
    unknown = serializers.LedgerNetworkCreateSerializer(
        data={
            "network_key": "strict",
            "name": "Strict",
            "provider_type": "test",
            "dependency_key": "traceability.test",
            "network_namespace": "test",
            "tenant_id": str(tenant_b.id),
            "status": "active",
        }
    )
    assert not unknown.is_valid()
    assert set(unknown.errors) == {"tenant_id", "status"}

    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(serializers.MAX_JSON_DEPTH + 1):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    too_deep = serializers.TraceabilityEventCreateSerializer(
        data={
            "asset_id": str(uuid4()),
            "idempotency_key": "deep",
            "event_type": "test",
            "occurred_at": timezone.now().isoformat(),
            "actor_ref": "actor",
            "payload": nested,
        }
    )
    assert not too_deep.is_valid()
    assert "payload" in too_deep.errors


def test_network_options_reject_urls_and_secret_material() -> None:
    for options in ({"endpoint": "https://ledger.invalid"}, {"api_token": "do-not-store"}):
        serializer = serializers.LedgerNetworkCreateSerializer(
            data={
                "network_key": "unsafe",
                "name": "Unsafe",
                "provider_type": "test",
                "dependency_key": "traceability.test",
                "network_namespace": "test",
                "provider_options": options,
            }
        )
        assert not serializer.is_valid()
        assert "provider_options" in serializer.errors


def test_unauthenticated_routes_return_exact_governed_401(api_client) -> None:
    for resource in (
        "networks",
        "assets",
        "events",
        "anchors",
        "credentials",
        "compliance-evidence",
        "verification-attempts",
    ):
        response = api_client.get(f"/api/v2/blockchain-traceability/{resource}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        payload = response.json()
        assert set(payload) == {"error"}
        assert payload["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert set(payload["error"]) == {"code", "message", "detail", "correlation_id"}


def test_network_list_envelope_filter_search_order_and_pagination(authenticated_tenant_a_client, tenant_a) -> None:
    LedgerNetwork.objects.bulk_create(
        [
            LedgerNetwork(
                tenant_id=tenant_a.id,
                network_key=f"alpha-{index:03d}",
                name=f"Alpha {index:03d}",
                provider_type="test-ledger",
                dependency_key=f"traceability.test.{index}",
                network_namespace="test",
                status="draft",
                created_by="api-test",
            )
            for index in range(101)
        ]
    )
    correlation_id = str(uuid4())
    response = authenticated_tenant_a_client.get(
        "/api/v2/blockchain-traceability/networks/"
        "?status=draft&provider_type=test-ledger&search=Alpha&ordering=-name&page_size=500",
        HTTP_X_CORRELATION_ID=correlation_id,
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["correlation_id"] == correlation_id
    assert payload["meta"]["pagination"]["page_size"] == 100
    assert payload["meta"]["pagination"]["count"] == 101
    assert len(payload["data"]) == 100
    assert payload["data"][0]["name"] == "Alpha 100"
    assert payload["data"][0]["tenant_id"] == str(tenant_a.id)


def test_invalid_ordering_and_date_filters_return_validation_envelopes(authenticated_tenant_a_client) -> None:
    ordering = authenticated_tenant_a_client.get("/api/v2/blockchain-traceability/assets/?ordering=secret_ref")
    assert ordering.status_code == status.HTTP_400_BAD_REQUEST
    assert ordering.json()["error"]["code"] == "VALIDATION_ERROR"

    date_filter = authenticated_tenant_a_client.get("/api/v2/blockchain-traceability/events/?occurred_after=not-a-date")
    assert date_filter.status_code == status.HTTP_400_BAD_REQUEST
    assert date_filter.json()["error"]["code"] == "VALIDATION_ERROR"


def test_policy_denial_is_403_and_names_the_governed_error(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision.deny(
            AccessReasonCode.POLICY_DENIED,
            "denied by test policy",
            tenant_id=UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", deny)
    response = authenticated_tenant_a_client.get("/api/v2/blockchain-traceability/assets/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"


@pytest.mark.parametrize(
    ("method", "path", "capability"),
    [
        ("get", "networks/", "network:read"),
        ("post", "networks/", "network:manage"),
        ("get", "networks/{id}/", "network:read"),
        ("patch", "networks/{id}/", "network:manage"),
        ("delete", "networks/{id}/", "network:manage"),
        ("post", "networks/{id}/activate/", "network:manage"),
        ("post", "networks/{id}/disable/", "network:manage"),
        ("post", "networks/{id}/probe/", "network:probe"),
        ("get", "assets/", "asset:read"),
        ("post", "assets/", "asset:create"),
        ("get", "assets/{id}/", "asset:read"),
        ("patch", "assets/{id}/", "asset:update"),
        ("delete", "assets/{id}/", "asset:delete"),
        ("post", "assets/{id}/activate/", "asset:transition"),
        ("post", "assets/{id}/recall/", "asset:transition"),
        ("post", "assets/{id}/release-recall/", "asset:transition"),
        ("post", "assets/{id}/retire/", "asset:transition"),
        ("get", "assets/{id}/history/", "asset:read"),
        ("post", "assets/{id}/verify-chain/", "event:verify"),
        ("get", "events/", "event:read"),
        ("post", "events/", "event:append"),
        ("get", "events/{id}/", "event:read"),
        ("get", "anchors/", "anchor:read"),
        ("post", "anchors/", "anchor:create"),
        ("get", "anchors/{id}/", "anchor:read"),
        ("post", "anchors/{id}/retry/", "anchor:retry"),
        ("post", "anchors/{id}/refresh/", "anchor:verify"),
        ("post", "anchors/{id}/verify/", "anchor:verify"),
        ("get", "credentials/", "credential:read"),
        ("post", "credentials/", "credential:issue"),
        ("get", "credentials/{id}/", "credential:read"),
        ("post", "credentials/{id}/revoke/", "credential:revoke"),
        ("post", "credentials/verify/", "credential:verify"),
        ("get", "compliance-evidence/", "compliance:read"),
        ("post", "compliance-evidence/", "compliance:create"),
        ("get", "compliance-evidence/{id}/", "compliance:read"),
        ("patch", "compliance-evidence/{id}/", "compliance:update"),
        ("delete", "compliance-evidence/{id}/", "compliance:delete"),
        ("post", "compliance-evidence/{id}/finalize/", "compliance:finalize"),
        ("post", "compliance-evidence/{id}/supersede/", "compliance:finalize"),
        ("post", "compliance-evidence/{id}/verify/", "compliance:verify"),
        ("get", "verification-attempts/", "verification:read"),
        ("get", "verification-attempts/{id}/", "verification:read"),
        ("get", "health/", "health:read"),
    ],
)
def test_every_endpoint_fails_closed_with_its_action_capability(
    monkeypatch, authenticated_tenant_a_client, method, path, capability
) -> None:
    decisions: list[str] = []

    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, kwargs
        decisions.append(required_permission)
        return AccessDecision.deny(
            AccessReasonCode.POLICY_DENIED,
            "denied by capability matrix",
            tenant_id=UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", deny)
    url = "/api/v2/blockchain-traceability/" + path.format(id=uuid4())
    response = getattr(authenticated_tenant_a_client, method)(url, {}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    assert decisions == [f"blockchain_traceability.{capability}"]


def test_every_router_action_has_an_explicit_declared_capability() -> None:
    viewsets = (
        LedgerNetworkViewSet,
        TraceabilityAssetViewSet,
        TraceabilityEventViewSet,
        LedgerAnchorViewSet,
        AuthenticityCredentialViewSet,
        ComplianceEvidenceViewSet,
        VerificationAttemptViewSet,
    )
    for viewset in viewsets:
        assert viewset.action_permissions
        assert set(viewset.action_permissions.values()).issubset(set(PERMISSIONS))
        assert all(value for value in viewset.action_permissions.values())


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("put", "/api/v2/blockchain-traceability/networks/{network}/"),
        ("put", "/api/v2/blockchain-traceability/assets/{asset}/"),
        ("put", "/api/v2/blockchain-traceability/compliance-evidence/{evidence}/"),
        ("patch", "/api/v2/blockchain-traceability/events/{event}/"),
        ("delete", "/api/v2/blockchain-traceability/anchors/{anchor}/"),
        ("patch", "/api/v2/blockchain-traceability/credentials/{credential}/"),
        ("post", "/api/v2/blockchain-traceability/verification-attempts/"),
    ],
)
def test_immutable_or_unsupported_methods_return_405(authenticated_tenant_a_client, method, url) -> None:
    resolved = url.format(
        network=uuid4(),
        asset=uuid4(),
        evidence=uuid4(),
        event=uuid4(),
        anchor=uuid4(),
        credential=uuid4(),
    )
    response = getattr(authenticated_tenant_a_client, method)(resolved, {}, format="json")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_anchor_request_is_honest_202_queued(monkeypatch, authenticated_tenant_a_client, tenant_a) -> None:
    asset = _asset(tenant_a.id, "anchor")
    network = _network(tenant_a.id, "anchor", status_value="active")
    anchor = LedgerAnchor.objects.create(
        tenant_id=tenant_a.id,
        asset=asset,
        network=network,
        start_sequence=1,
        end_sequence=1,
        root_hash="c" * 64,
        idempotency_key="anchor-api",
        created_by="api-test",
    )
    job = SimpleNamespace(
        id=uuid4(),
        status="pending",
        command="internal.command.value",
        correlation_id="job-correlation",
    )
    monkeypatch.setattr(LedgerAnchorViewSet.service, "request_anchor", lambda tenant_id, actor_id, data: (anchor, job))

    response = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/anchors/",
        {
            "asset_id": str(asset.id),
            "network_id": str(network.id),
            "start_sequence": 1,
            "end_sequence": 1,
            "idempotency_key": "anchor-api",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()["data"]
    assert data["queued"] is True
    assert data["job"] == {
        "id": str(job.id),
        "status": "queued",
        "command": "blockchain_traceability.submit_anchor",
        "correlation_id": "job-correlation",
    }
    assert "verified" not in repr(data).lower()


def test_probe_returns_evidence_backed_provider_health_shape(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    network = _network(tenant_a.id, "probe", status_value="active")
    provider_health = ProviderHealth(
        available=True,
        code="ready",
        checked_at=datetime.now(datetime_timezone.utc),
        evidence={"provider_ack": True},
    )
    result = OperationResult.succeeded(provider_health, evidence={"provider_ack": True}, provider="test-ledger")
    monkeypatch.setattr(LedgerNetworkViewSet.service, "probe_network", lambda tenant_id, network_id, actor_id: result)

    response = authenticated_tenant_a_client.post(
        f"/api/v2/blockchain-traceability/networks/{network.id}/probe/", {}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    value = response.json()["data"]
    assert value["ok"] is True
    assert value["value"]["status"] == "healthy"
    assert value["value"]["provider_type"] == "test-ledger"
    assert value["value"]["simulated"] is False


def test_asset_history_has_complete_discriminated_items_and_pagination(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    asset = _asset(tenant_a.id, "history")
    occurred_at = timezone.now()
    event = TraceabilityEvent.objects.create(
        tenant_id=tenant_a.id,
        asset=asset,
        sequence=1,
        idempotency_key="history-event",
        event_type="commissioned",
        occurred_at=occurred_at,
        actor_ref="manufacturer:test",
        previous_hash="",
        event_hash="d" * 64,
        created_by="api-test",
        correlation_id="history-correlation",
    )
    history = AssetHistory(
        asset={"id": str(asset.id)},
        items=(
            AssetHistoryItem(
                kind="event",
                occurred_at=occurred_at.isoformat(),
                identifier=event.id,
                sequence=1,
                event={"id": str(event.id)},
            ),
        ),
        proof_status="Locally consistent — not externally anchored",
        failing_sequence=None,
        pagination={"page": 1, "page_size": 25, "total": 1, "has_next": False},
    )
    monkeypatch.setattr(
        TraceabilityAssetViewSet.service,
        "product_history",
        lambda tenant_id, asset_id, page, page_size: history,
    )

    response = authenticated_tenant_a_client.get(f"/api/v2/blockchain-traceability/assets/{asset.id}/history/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["asset"]["tenant_id"] == str(tenant_a.id)
    assert data["proof_status"] == "locally_consistent"
    assert data["items"][0]["kind"] == "event"
    assert data["items"][0]["event"]["event_hash"] == "d" * 64
    assert data["pagination"] == {
        "page": 1,
        "page_size": 25,
        "total_pages": 1,
        "count": 1,
        "has_next": False,
        "has_previous": False,
    }


def test_raw_token_appears_only_once_in_issue_response(monkeypatch, authenticated_tenant_a_client, tenant_a) -> None:
    asset = _asset(tenant_a.id, "credential")
    credential = _credential(tenant_a.id, asset)
    raw_token = "one-time-token-value"
    monkeypatch.setattr(
        AuthenticityCredentialViewSet.service,
        "issue_credential",
        lambda tenant_id, asset_id, actor_id, claims, expires_at: SimpleNamespace(
            credential=credential,
            token=raw_token,
        ),
    )
    issue = authenticated_tenant_a_client.post(
        "/api/v2/blockchain-traceability/credentials/",
        {"asset_id": str(asset.id), "claims": {"sku": "SKU-1"}},
        format="json",
    )
    assert issue.status_code == status.HTTP_201_CREATED
    assert issue["Cache-Control"] == "no-store"
    assert issue.json()["data"]["token"] == raw_token
    assert issue.json()["data"]["token_recoverable"] is False

    detail = authenticated_tenant_a_client.get(f"/api/v2/blockchain-traceability/credentials/{credential.id}/")
    listing = authenticated_tenant_a_client.get("/api/v2/blockchain-traceability/credentials/")
    assert raw_token not in detail.content.decode()
    assert raw_token not in listing.content.decode()
    assert "token_digest" not in detail.content.decode()


def test_health_endpoint_is_governed_and_sanitized(monkeypatch, authenticated_tenant_a_client) -> None:
    report = {
        "status": "degraded",
        "checked_at": timezone.now().isoformat(),
        "dependencies": [
            {
                "name": "network",
                "status": "degraded",
                "code": "active_network_not_configured",
                "checked_at": timezone.now().isoformat(),
                "circuit_state": "not_applicable",
            }
        ],
    }
    monkeypatch.setattr("src.modules.blockchain_traceability.api.module_health", lambda tenant_id: (report, 200))
    response = authenticated_tenant_a_client.get("/api/v2/blockchain-traceability/health/")
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["data"] == report
    rendered = response.content.decode().lower()
    assert "count" not in rendered
    assert "secret" not in rendered
    assert "traceback" not in rendered

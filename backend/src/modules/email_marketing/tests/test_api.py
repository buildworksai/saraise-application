"""Black-box v2 routing, envelope, serializer, and delegation tests."""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import override_settings
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.user_models import UserProfile
from src.modules.email_marketing import api
from src.modules.email_marketing import services as email_services
from src.modules.email_marketing.models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    DeliveryEvent,
    EmailCampaign,
    EmailMarketingConfigurationVersion,
    EmailTemplate,
    SuppressionEntry,
)
from src.modules.email_marketing.serializers import CampaignCreateSerializer, CampaignUpdateSerializer
from src.modules.email_marketing.services import _apply_transition, get_platform_runtime_defaults
from src.modules.email_marketing.state_machines import RECIPIENT_STATE_MACHINE

pytestmark = pytest.mark.django_db
User = get_user_model()
BASE = "/api/v2/email-marketing"


@pytest.fixture(autouse=True)
def isolate_controller_from_external_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authorization branches are tested separately; controller tests retain auth."""

    monkeypatch.setattr(
        api.EmailMarketingAccessMixin,
        "get_permissions",
        lambda self: [IsAuthenticated()],
    )


@pytest.fixture
def identity() -> tuple[object, uuid.UUID, uuid.UUID]:
    tenant = uuid.uuid4()
    user = User.objects.create_user(username=f"user-{tenant}", password="test-password")
    with patch.object(UserProfile, "clean"):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"tenant_id": str(tenant), "tenant_role": "tenant_admin"},
        )
    return (
        User.objects.get(pk=user.pk),
        tenant,
        uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{user.pk}"),
    )


@pytest.fixture
def client(identity: tuple[object, uuid.UUID, uuid.UUID]) -> APIClient:
    value = APIClient()
    value.force_authenticate(user=identity[0])
    return value


def create_template(tenant: uuid.UUID, code: str = "WELCOME") -> EmailTemplate:
    return EmailTemplate.objects.create(
        tenant_id=tenant,
        template_code=code,
        template_name="Welcome",
        subject="Welcome",
        body_html="<p>Welcome</p>",
        design_json={"version": 1},
    )


def create_campaign(
    tenant: uuid.UUID,
    template: EmailTemplate | None = None,
    code: str = "LAUNCH",
) -> EmailCampaign:
    return EmailCampaign.objects.create(
        tenant_id=tenant,
        campaign_code=code,
        campaign_name="Launch",
        subject="Launch",
        from_name="SARAISE",
        from_email="sender@example.com",
        audience_definition={
            "version": 1,
            "resolver": "manual",
            "recipients": [],
        },
        template=template,
    )


def campaign_payload(template: EmailTemplate) -> dict[str, object]:
    return {
        "campaign_code": "newsletter",
        "campaign_name": "Newsletter",
        "template_id": str(template.id),
        "subject": "Monthly news",
        "from_name": "SARAISE",
        "from_email": "news@example.com",
        "audience_definition": {
            "version": 1,
            "resolver": "manual",
            "recipients": [],
        },
        "timezone": "UTC",
    }


def test_public_throttle_and_common_viewset_helpers_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    throttle = api.PublicEmailThrottle()
    assert throttle.get_rate()
    assert throttle.allow_request(SimpleNamespace(), SimpleNamespace()) is False

    tenant = uuid.uuid4()
    monkeypatch.setattr(
        api,
        "get_runtime_configuration",
        lambda tenant_id: SimpleNamespace(document={"rate_limits": {"public_per_minute": 7}}),
    )
    monkeypatch.setattr(api.SimpleRateThrottle, "allow_request", lambda self, request, view: True)
    request = SimpleNamespace(tenant_id=tenant, META={"REMOTE_ADDR": "203.0.113.10"})
    assert throttle.allow_request(request, SimpleNamespace()) is True
    assert throttle.rate == "7/min"

    view = api.EmailMarketingViewSet()
    view.request = SimpleNamespace(headers={}, data={"campaign_code": "LAUNCH"})
    assert view.mutation_idempotency_key().startswith("request:")
    view.request = SimpleNamespace(headers={"Idempotency-Key": "  explicit-key  "}, data={})
    assert view.mutation_idempotency_key() == "explicit-key"
    view.request = SimpleNamespace(headers={"Idempotency-Key": "x" * 256}, data={})
    with pytest.raises(api.ValidationError):
        view.mutation_idempotency_key()


def test_real_permission_helpers_select_manage_permission_and_bind_webhook_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = uuid.uuid4()
    configuration_view = api.ConfigurationViewSet()
    configuration_view.action = "current"
    configuration_view.request = SimpleNamespace(method="PUT")
    assert configuration_view.required_permission_for_action("current") == "email_marketing.configuration:manage"
    configuration_view.request = SimpleNamespace(method="GET")
    assert configuration_view.required_permission_for_action("current") == "email_marketing.configuration:read"
    assert configuration_view.required_permission_for_action("missing") is None

    signing_key = "provider-fixture-key"
    body = b'{"event":"delivered"}'
    timestamp = str(int(time.time()))
    signature = hmac.new(signing_key.encode(), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(
        email_services,
        "get_runtime_configuration",
        lambda tenant_id: SimpleNamespace(document={"resilience": {"webhook_replay_window_seconds": 300}}),
    )
    request = SimpleNamespace(
        headers={
            "X-Email-Gateway": "provider",
            "X-Email-Timestamp": timestamp,
            "X-Email-Signature": signature,
        },
        body=body,
    )
    permission = api.ProviderWebhookPermission()

    with override_settings(
        EMAIL_MARKETING_PROVIDER_ACCOUNTS={"provider": {"tenant_id": str(tenant), "webhook_secret": signing_key}}
    ):
        assert permission.has_permission(request, SimpleNamespace()) is True
    assert request.tenant_id == tenant
    assert request.gateway_key == "provider"


def test_campaign_mutation_serializers_reject_owned_and_lifecycle_fields() -> None:
    base = {
        "campaign_code": "launch",
        "campaign_name": "Launch",
        "subject": "Subject",
        "from_name": "Sender",
        "from_email": "sender@example.com",
    }
    for forbidden in (
        "tenant_id",
        "status",
        "sent_count",
        "transition_history",
        "legacy_template_id",
    ):
        serializer = CampaignCreateSerializer(data={**base, forbidden: "spoofed"})
        assert not serializer.is_valid()
        assert forbidden in serializer.errors
        update = CampaignUpdateSerializer(data={forbidden: "spoofed"})
        assert not update.is_valid()
        assert forbidden in update.errors


def test_campaign_list_is_paginated_and_governed(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    create_campaign(tenant)
    response = client.get(f"{BASE}/campaigns/?page=1&page_size=25&ordering=-created_at")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["meta"]["pagination"] == {
        "count": 1,
        "page": 1,
        "page_size": 25,
        "total_pages": 1,
        "has_next": False,
        "has_previous": False,
    }
    assert body["meta"]["correlation_id"]
    assert body["meta"]["timestamp"]


def test_campaign_create_ignores_tenant_spoof_and_is_always_draft(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    template = create_template(tenant)
    payload = {
        **campaign_payload(template),
        "tenant_id": str(uuid.uuid4()),
        "status": "sent",
    }
    response = client.post(f"{BASE}/campaigns/", payload, format="json")
    assert response.status_code == 400  # unknown ownership/lifecycle input is rejected
    payload.pop("tenant_id")
    payload.pop("status")
    response = client.post(f"{BASE}/campaigns/", payload, format="json")
    assert response.status_code == 201
    created = EmailCampaign.objects.get(campaign_code="NEWSLETTER")
    assert created.tenant_id == tenant and created.status == "draft"


def test_campaign_patch_delegates_and_put_is_not_supported(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    campaign = create_campaign(tenant)
    response = client.patch(
        f"{BASE}/campaigns/{campaign.id}/",
        {"campaign_name": "Updated"},
        format="json",
    )
    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.campaign_name == "Updated"
    assert client.put(f"{BASE}/campaigns/{campaign.id}/", {}, format="json").status_code == 405


def test_campaign_filters_search_order_and_reject_unknown(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    create_campaign(tenant, code="ALPHA")
    create_campaign(tenant, code="BETA")
    response = client.get(f"{BASE}/campaigns/?search=alpha&status=draft&ordering=campaign_name")
    assert response.status_code == 200 and len(response.json()["data"]) == 1
    invalid = client.get(f"{BASE}/campaigns/?unsafe=1")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_template_crud_preview_and_lifecycle_routes_exist(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    response = client.post(
        f"{BASE}/templates/",
        {
            "template_code": "welcome",
            "template_name": "Welcome",
            "subject": "Hello {{ name }}",
            "body_html": "<p>Hello {{ name }}</p>",
            "body_text": "Hello {{ name }}",
            "design_json": {"version": 1},
        },
        format="json",
    )
    assert response.status_code == 201
    template = EmailTemplate.objects.get(tenant_id=tenant, template_code="WELCOME")
    preview = client.post(
        f"{BASE}/templates/{template.id}/preview/",
        {"sample_data": {"name": "Ada"}},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["subject"] == "Hello Ada"
    activate = client.post(
        f"{BASE}/templates/{template.id}/activate/",
        {"idempotency_key": "activate-welcome"},
        format="json",
    )
    assert activate.status_code == 200
    archive = client.post(
        f"{BASE}/templates/{template.id}/archive/",
        {"idempotency_key": "archive-welcome"},
        format="json",
    )
    assert archive.status_code == 200


def test_compliance_collections_are_real_and_lifecycle_controlled(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    consent = client.post(
        f"{BASE}/consents/",
        {
            "email": "Customer@EXAMPLE.COM",
            "purpose": "marketing",
            "status": "granted",
            "lawful_basis": "consent",
            "source": "api",
            "notice_version": "v1",
            "evidence": {},
        },
        format="json",
    )
    assert consent.status_code == 201
    assert ConsentRecord.objects.filter(tenant_id=tenant, email="Customer@example.com").exists()
    suppression = client.post(
        f"{BASE}/suppressions/",
        {
            "email": "Customer@example.com",
            "scope": "marketing",
            "reason": "manual",
            "source": "administrator",
            "notes": "Compliance review",
        },
        format="json",
    )
    assert suppression.status_code == 201
    entry = SuppressionEntry.objects.get(tenant_id=tenant)
    deactivated = client.post(
        f"{BASE}/suppressions/{entry.id}/deactivate/",
        {"reason": "Correction approved"},
        format="json",
    )
    assert deactivated.status_code == 200
    entry.refresh_from_db()
    assert not entry.active and entry.deactivated_at is not None


def test_configuration_routes_validate_preview_version_and_history(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    current = client.get(f"{BASE}/configuration/current/")
    assert current.status_code == 200
    current_body = current.json()["data"]
    assert current_body["version"] == 1

    document = deepcopy(current_body["document"])
    document["pagination"]["default_page_size"] = 50
    preview = client.post(f"{BASE}/configuration/preview/", {"document": document}, format="json")
    assert preview.status_code == 200
    assert preview.json()["data"]["valid"] is True
    assert any(change["path"] == "pagination.default_page_size" for change in preview.json()["data"]["changes"])

    stale = client.put(
        f"{BASE}/configuration/current/",
        {"document": document, "expected_version": 99},
        format="json",
    )
    assert stale.status_code == 409

    updated = client.put(
        f"{BASE}/configuration/current/",
        {"document": document, "expected_version": 1},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["version"] == 2

    history = client.get(f"{BASE}/configuration/history/")
    assert history.status_code == 200
    assert [version["version"] for version in history.json()["data"]] == [2, 1]

    exported = client.get(f"{BASE}/configuration/export-document/")
    assert exported.status_code == 200
    assert exported.json()["data"]["document"]["pagination"]["default_page_size"] == 50

    imported_document = deepcopy(exported.json()["data"]["document"])
    imported_document["rate_limits"]["public_per_minute"] = 20
    imported = client.post(
        f"{BASE}/configuration/import-document/",
        {"document": imported_document, "expected_version": 2},
        format="json",
    )
    assert imported.status_code == 200
    assert imported.json()["data"]["version"] == 3
    assert EmailMarketingConfigurationVersion.objects.get(tenant_id=tenant, version=3).change_type == "imported"

    rolled_back = client.post(
        f"{BASE}/configuration/rollback/",
        {"target_version": 1, "expected_version": 3},
        format="json",
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["data"]["version"] == 4
    assert rolled_back.json()["data"]["document"] == get_platform_runtime_defaults()


def test_signed_public_tracking_and_unsubscribe_routes_update_delivery_truth(
    client: APIClient, identity: tuple[object, uuid.UUID, uuid.UUID]
) -> None:
    _, tenant, _ = identity
    campaign = create_campaign(tenant)
    recipient = CampaignRecipient.objects.create(
        tenant_id=tenant,
        campaign=campaign,
        email="Customer@example.com",
        status="resolved",
        resolved_at=timezone.now(),
    )
    attempt = DeliveryAttempt.objects.create(
        tenant_id=tenant,
        recipient=recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key=f"attempt:{uuid.uuid4()}",
        gateway_key=campaign.gateway_key,
        status="accepted",
        provider_message_id="provider-message-1",
        accepted_at=timezone.now(),
    )
    recipient = _apply_transition(
        RECIPIENT_STATE_MACHINE,
        recipient,
        "queue",
        tenant,
        "api-test-queue",
        identity[2],
    )
    recipient = _apply_transition(
        RECIPIENT_STATE_MACHINE,
        recipient,
        "start_send",
        tenant,
        "api-test-start",
        identity[2],
    )
    recipient = _apply_transition(
        RECIPIENT_STATE_MACHINE,
        recipient,
        "accepted",
        tenant,
        "api-test-accepted",
        identity[2],
    )
    recipient.accepted_at = timezone.now()
    recipient.save(update_fields=["accepted_at", "updated_at"])

    tracking_token = signing.dumps(
        {"tenant_id": str(tenant), "recipient_id": str(recipient.id)},
        salt="email_marketing.tracking",
    )
    opened = APIClient().get(f"{BASE}/t/{tracking_token}/open.gif")
    assert opened.status_code == 200
    assert opened["Cache-Control"] == "no-store, private"
    assert DeliveryEvent.objects.filter(
        tenant_id=tenant,
        attempt=attempt,
        event_type="opened",
        metadata={"source": "tracking"},
    ).exists()

    signed_destination = signing.dumps(
        "https://example.test/product/1",
        salt="email_marketing.destination",
        compress=True,
    )
    clicked = APIClient().get(f"{BASE}/t/{tracking_token}/click/?destination={signed_destination}")
    assert clicked.status_code == 302
    assert clicked["Location"] == "https://example.test/product/1"
    assert DeliveryEvent.objects.filter(tenant_id=tenant, attempt=attempt, event_type="clicked").exists()

    unsubscribe_token = signing.dumps(
        {"tenant_id": str(tenant), "recipient_id": str(recipient.id)},
        salt="email_marketing.unsubscribe",
    )
    unsubscribed = APIClient().post(f"{BASE}/public/unsubscribe/", {"token": unsubscribe_token}, format="json")
    assert unsubscribed.status_code == 200
    recipient.refresh_from_db()
    assert recipient.status == "unsubscribed"
    assert SuppressionEntry.objects.filter(
        tenant_id=tenant, email="Customer@example.com", reason="unsubscribe"
    ).exists()


def test_unauthenticated_private_mutation_denies() -> None:
    anonymous = APIClient(enforce_csrf_checks=True)
    response = anonymous.post(f"{BASE}/campaigns/", {}, format="json")
    assert response.status_code in {401, 403}
    assert response.json()["error"]["code"] in {
        "AUTHENTICATION_REQUIRED",
        "POLICY_DENIED",
    }

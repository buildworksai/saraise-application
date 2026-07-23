"""Black-box v2 routing, envelope, serializer, and delegation tests."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.user_models import UserProfile
from src.modules.email_marketing import api
from src.modules.email_marketing.models import (
    ConsentRecord,
    EmailCampaign,
    EmailTemplate,
    SuppressionEntry,
)
from src.modules.email_marketing.serializers import (
    CampaignCreateSerializer,
    CampaignUpdateSerializer,
)

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


def test_unauthenticated_private_mutation_denies() -> None:
    anonymous = APIClient(enforce_csrf_checks=True)
    response = anonymous.post(f"{BASE}/campaigns/", {}, format="json")
    assert response.status_code in {401, 403}
    assert response.json()["error"]["code"] in {
        "AUTHENTICATION_REQUIRED",
        "POLICY_DENIED",
    }

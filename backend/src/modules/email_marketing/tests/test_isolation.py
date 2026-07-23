"""Two-tenant isolation proofs across mutable and append-only resources."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient

from src.core.user_models import UserProfile
from src.modules.email_marketing import api
from src.modules.email_marketing.models import (
    CampaignRecipient,
    ConsentRecord,
    DeliveryAttempt,
    EmailCampaign,
    EmailTemplate,
)
from src.modules.email_marketing.services import (
    ComplianceService,
    DeliveryService,
)

pytestmark = pytest.mark.django_db
User = get_user_model()
BASE = "/api/v2/email-marketing"


@pytest.fixture(autouse=True)
def isolate_external_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.EmailMarketingAccessMixin,
        "get_permissions",
        lambda self: [IsAuthenticated()],
    )


def user_for(tenant: uuid.UUID, suffix: str) -> object:
    user = User.objects.create_user(username=f"tenant-{suffix}", password="test-password")
    with patch.object(UserProfile, "clean"):
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"tenant_id": str(tenant), "tenant_role": "tenant_admin"},
        )
    return User.objects.get(pk=user.pk)


def template_for(tenant: uuid.UUID, code: str) -> EmailTemplate:
    return EmailTemplate.objects.create(
        tenant_id=tenant,
        template_code=code,
        template_name=code,
        subject="Subject",
        body_html="<p>Body</p>",
        design_json={"version": 1},
    )


def campaign_for(tenant: uuid.UUID, code: str, template: EmailTemplate | None = None) -> EmailCampaign:
    return EmailCampaign.objects.create(
        tenant_id=tenant,
        campaign_code=code,
        campaign_name=code,
        subject="Subject",
        from_name="Sender",
        from_email="sender@example.com",
        audience_definition={
            "version": 1,
            "resolver": "manual",
            "recipients": [],
        },
        template=template,
    )


@pytest.fixture
def tenants() -> tuple[uuid.UUID, uuid.UUID, APIClient]:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    client = APIClient()
    client.force_authenticate(user=user_for(tenant_a, "a"))
    user_for(tenant_b, "b")
    return tenant_a, tenant_b, client


def test_campaign_list_detail_update_delete_and_actions_hide_foreign_rows(
    tenants: tuple[uuid.UUID, uuid.UUID, APIClient],
) -> None:
    tenant_a, tenant_b, client = tenants
    own = campaign_for(tenant_a, "OWN")
    foreign = campaign_for(tenant_b, "FOREIGN")
    listed = client.get(f"{BASE}/campaigns/").json()["data"]
    assert {row["id"] for row in listed} == {str(own.id)}
    assert client.get(f"{BASE}/campaigns/{foreign.id}/").status_code == 404
    assert (
        client.patch(
            f"{BASE}/campaigns/{foreign.id}/",
            {"campaign_name": "stolen"},
            format="json",
        ).status_code
        == 404
    )
    assert client.delete(f"{BASE}/campaigns/{foreign.id}/").status_code == 404
    for route, method in (
        ("analytics", "get"),
        ("preflight", "get"),
        ("resolve-audience", "post"),
        ("schedule", "post"),
        ("send", "post"),
        ("pause", "post"),
        ("resume", "post"),
        ("cancel", "post"),
    ):
        response = getattr(client, method)(
            f"{BASE}/campaigns/{foreign.id}/{route}/",
            {"idempotency_key": f"cross-{route}"},
            format="json",
        )
        assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.campaign_name == "FOREIGN" and not foreign.is_deleted


def test_template_reference_and_template_mutations_are_tenant_safe(
    tenants: tuple[uuid.UUID, uuid.UUID, APIClient],
) -> None:
    tenant_a, tenant_b, client = tenants
    foreign = template_for(tenant_b, "FOREIGN")
    payload = {
        "campaign_code": "spoof",
        "campaign_name": "Spoof",
        "template_id": str(foreign.id),
        "subject": "Subject",
        "from_name": "Sender",
        "from_email": "sender@example.com",
        "audience_definition": {
            "version": 1,
            "resolver": "manual",
            "recipients": [],
        },
    }
    assert client.post(f"{BASE}/campaigns/", payload, format="json").status_code == 400
    assert not EmailCampaign.objects.filter(tenant_id=tenant_a, campaign_code="SPOOF").exists()
    assert client.get(f"{BASE}/templates/{foreign.id}/").status_code == 404
    assert (
        client.patch(
            f"{BASE}/templates/{foreign.id}/",
            {"template_name": "stolen"},
            format="json",
        ).status_code
        == 404
    )
    assert client.delete(f"{BASE}/templates/{foreign.id}/").status_code == 404


def test_every_resource_collection_and_detail_are_tenant_isolated(
    tenants: tuple[uuid.UUID, uuid.UUID, APIClient],
) -> None:
    tenant_a, tenant_b, client = tenants
    own_template = template_for(tenant_a, "OWN-TEMPLATE")
    foreign_template = template_for(tenant_b, "FOREIGN-TEMPLATE")
    foreign_campaign = campaign_for(tenant_b, "FOREIGN-RESOURCE", foreign_template)
    foreign_recipient = CampaignRecipient.objects.create(
        tenant_id=tenant_b,
        campaign=foreign_campaign,
        email="foreign@example.com",
        personalization_data={},
    )
    foreign_attempt = DeliveryAttempt.objects.create(
        tenant_id=tenant_b,
        recipient=foreign_recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key="foreign-attempt",
        gateway_key="django",
    )
    foreign_suppression = ComplianceService.suppress(
        tenant_b,
        uuid.uuid4(),
        {
            "email": "foreign@example.com",
            "scope": "marketing",
            "reason": "manual",
            "source": "administrator",
        },
    )
    foreign_consent = ConsentRecord.objects.create(
        tenant_id=tenant_b,
        email="foreign@example.com",
        purpose="marketing",
        status="granted",
        lawful_basis="consent",
        source="api",
        notice_version="v1",
        captured_at=timezone.now(),
        evidence={},
    )

    expected_visible = {
        "campaigns": set(),
        "templates": {str(own_template.id)},
        "recipients": set(),
        "deliveries": set(),
        "suppressions": set(),
        "consents": set(),
    }
    foreign_ids = {
        "campaigns": foreign_campaign.id,
        "templates": foreign_template.id,
        "recipients": foreign_recipient.id,
        "deliveries": foreign_attempt.id,
        "suppressions": foreign_suppression.id,
        "consents": foreign_consent.id,
    }
    for resource, expected_ids in expected_visible.items():
        response = client.get(f"{BASE}/{resource}/")
        assert response.status_code == 200
        assert {row["id"] for row in response.json()["data"]} == expected_ids
        assert client.get(f"{BASE}/{resource}/{foreign_ids[resource]}/").status_code == 404


@pytest.mark.parametrize(
    ("resource", "payload"),
    (
        (
            "templates",
            {
                "template_code": "TENANT-SPOOF",
                "template_name": "Tenant spoof",
                "subject": "Subject",
                "body_html": "<p>Body</p>",
            },
        ),
        (
            "suppressions",
            {
                "email": "spoof@example.com",
                "scope": "marketing",
                "reason": "manual",
                "source": "administrator",
            },
        ),
        (
            "consents",
            {
                "email": "spoof@example.com",
                "purpose": "marketing",
                "status": "granted",
                "lawful_basis": "consent",
                "source": "api",
                "notice_version": "v1",
            },
        ),
    ),
)
def test_create_rejects_client_supplied_tenant_id(
    tenants: tuple[uuid.UUID, uuid.UUID, APIClient],
    resource: str,
    payload: dict[str, object],
) -> None:
    _, tenant_b, client = tenants
    response = client.post(
        f"{BASE}/{resource}/",
        {**payload, "tenant_id": str(tenant_b)},
        format="json",
    )
    assert response.status_code == 400


def test_recipient_attempt_and_append_only_consent_relationships_reject_cross_tenant() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    campaign_b = campaign_for(tenant_b, "B")
    consent_b = ConsentRecord.objects.create(
        tenant_id=tenant_b,
        email="customer@example.com",
        purpose="marketing",
        status="granted",
        lawful_basis="consent",
        source="api",
        notice_version="v1",
        captured_at=timezone.now(),
        evidence={},
    )
    recipient = CampaignRecipient(
        tenant_id=tenant_a,
        campaign=campaign_b,
        email=consent_b.email,
        consent_record=consent_b,
        personalization_data={},
    )
    with pytest.raises(DjangoValidationError):
        recipient.full_clean()
    own_campaign = campaign_for(tenant_a, "A")
    own_recipient = CampaignRecipient.objects.create(
        tenant_id=tenant_a,
        campaign=own_campaign,
        email="customer@example.com",
        personalization_data={},
    )
    attempt = DeliveryAttempt(
        tenant_id=tenant_b,
        recipient=own_recipient,
        attempt_number=1,
        job_id=uuid.uuid4(),
        idempotency_key="cross-attempt",
        gateway_key="django",
    )
    with pytest.raises(DjangoValidationError):
        attempt.full_clean()


def test_suppression_deactivate_and_recipient_retry_cannot_cross_tenants(
    tenants: tuple[uuid.UUID, uuid.UUID, APIClient],
) -> None:
    tenant_a, tenant_b, client = tenants
    suppression = ComplianceService.suppress(
        tenant_b,
        uuid.uuid4(),
        {
            "email": "customer@example.com",
            "scope": "marketing",
            "reason": "manual",
            "source": "administrator",
        },
    )
    response = client.post(
        f"{BASE}/suppressions/{suppression.id}/deactivate/",
        {"reason": "cross tenant"},
        format="json",
    )
    assert response.status_code == 404
    suppression.refresh_from_db()
    assert suppression.active
    campaign = campaign_for(tenant_b, "RETRY")
    recipient = CampaignRecipient.objects.create(
        tenant_id=tenant_b,
        campaign=campaign,
        email="customer@example.com",
        personalization_data={},
    )
    assert (
        client.post(
            f"{BASE}/recipients/{recipient.id}/retry/",
            {"idempotency_key": "cross-retry"},
            format="json",
        ).status_code
        == 404
    )


def test_unsubscribe_token_is_cryptographically_tenant_bound() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    campaign = campaign_for(tenant_b, "UNSUB")
    recipient = CampaignRecipient.objects.create(
        tenant_id=tenant_b,
        campaign=campaign,
        email="customer@example.com",
        personalization_data={},
    )
    token = signing.dumps(
        {"tenant_id": str(tenant_b), "recipient_id": str(recipient.id)},
        salt="email_marketing.unsubscribe",
    )
    with pytest.raises(Exception):
        DeliveryService.unsubscribe(tenant_a, token, timezone.now())
    recipient.refresh_from_db()
    assert recipient.status == "resolved"

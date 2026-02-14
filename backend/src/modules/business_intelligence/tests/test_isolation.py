"""
Tenant Isolation Tests for Business Intelligence module.
"""

import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.business_intelligence.models import Report

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestReportTenantIsolation:
    """CRITICAL: Tenant isolation tests for Report model."""

    def test_user_cannot_list_other_tenant_reports(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's reports in list."""
        tenant_a_id = uuid.UUID(get_user_tenant_id(tenant_a_user))
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create report for tenant A
        report_a = Report.objects.create(
            tenant_id=tenant_a_id,
            report_code="RPT-A",
            report_name="Report A",
            report_type="financial",
            query="SELECT * FROM accounts",
        )

        # Create report for tenant B
        report_b = Report.objects.create(
            tenant_id=tenant_b_id,
            report_code="RPT-B",
            report_name="Report B",
            report_type="financial",
            query="SELECT * FROM accounts",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/business-intelligence/reports/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        report_ids = [r["id"] for r in data]

        # User A should see tenant A's report, but NOT tenant B's report
        assert str(report_a.id) in report_ids
        assert str(report_b.id) not in report_ids

    def test_user_cannot_get_other_tenant_report_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's report by ID (returns 404)."""
        tenant_b_id = uuid.UUID(get_user_tenant_id(tenant_b_user))

        # Create report for tenant B
        report_b = Report.objects.create(
            tenant_id=tenant_b_id,
            report_code="RPT-B",
            report_name="Report B",
            report_type="financial",
            query="SELECT * FROM accounts",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's report
        response = api_client.get(f"/api/v1/business-intelligence/reports/{report_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

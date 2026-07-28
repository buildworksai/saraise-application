"""Regression tests for development user seeding guardrails."""

from __future__ import annotations

import os
import sys
import uuid
from io import StringIO

import pytest

if os.environ.get("DJANGO_USE_SQLITE_FOR_TESTS") == "1" or (
    os.environ.get("DJANGO_USE_SQLITE_FOR_TESTS") is None and any("pytest" in arg for arg in sys.argv)
):
    pytest.skip(
        "seed_default_users identity-scope regression requires PostgreSQL migrations",
        allow_module_level=True,
    )

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from src.core.access.entitlements import Entitlement, Quota
from src.core.licensing.models import License, LicenseStatus, Organization
from src.core.tenancy.rls import tenant_context
from src.core.user_models import UserProfile
from src.modules.security_access_control.models import PermissionSet, PermissionSetPermission, UserPermissionSet
from src.modules.tenant_management.models import Tenant

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.postgresql
@override_settings(SARAISE_MODE="development")
def test_development_seed_binds_tenant_users_to_organization_scope() -> None:
    """Seeded tenant users must satisfy the development Organization guardrail."""

    password = "UatSeedRegression123!"  # pragma: allowlist secret

    call_command("seed_default_users", password=password, force=True, stdout=StringIO())

    organization = Organization.objects.get(domain="buildworks.ai")
    Tenant.objects.get(slug="buildworks")
    license_record = License.objects.get(organization=organization)
    tenant_admin = User.objects.get(email="admin@buildworks.ai")
    profile = UserProfile.objects.get(user=tenant_admin)

    assert license_record.status == LicenseStatus.ACTIVE
    assert profile.tenant_id == str(organization.id)
    assert profile.tenant_role == "tenant_admin"
    assert profile.platform_role is None

    profile.full_clean()
    assert tenant_admin.check_password(password)

    tenant_uuid = uuid.UUID(profile.tenant_id)
    with tenant_context(tenant_uuid):
        permission_set = PermissionSet.objects.for_tenant(tenant_uuid).get(
            name="Local development administrator",
            is_active=True,
            is_deleted=False,
        )
        grant = UserPermissionSet.objects.for_tenant(tenant_uuid).get(
            user=tenant_admin,
            permission_set=permission_set,
            revoked_at__isnull=True,
        )

        assert grant.expires_at is not None
        assert (
            PermissionSetPermission.objects.for_tenant(tenant_uuid)
            .filter(
                permission_set=permission_set,
                removed_at__isnull=True,
                permission__module="document_intelligence",
                permission__resource="configuration",
                permission__action="read",
            )
            .exists()
        )
        assert (
            Entitlement.objects.filter(tenant_id=tenant_uuid)
            .filter(
                capability="document_intelligence.configuration:read",
                enabled=True,
            )
            .exists()
        )
        assert (
            Entitlement.objects.filter(tenant_id=tenant_uuid)
            .filter(
                capability="module.workflow_automation",
                enabled=True,
            )
            .exists()
        )
        assert (
            Quota.objects.filter(tenant_id=tenant_uuid)
            .filter(
                resource="budget_management.api_reads",
                limit__gte=1,
                remaining__gte=1,
            )
            .exists()
        )
        assert (
            Quota.objects.filter(tenant_id=tenant_uuid)
            .filter(
                resource="automation_orchestration.definition:view:read",
                limit__gte=1,
                remaining__gte=1,
            )
            .exists()
        )
        assert (
            Quota.objects.filter(tenant_id=tenant_uuid)
            .filter(
                resource="document_intelligence.configuration:read",
                limit__gte=1,
                remaining__gte=1,
            )
            .exists()
        )

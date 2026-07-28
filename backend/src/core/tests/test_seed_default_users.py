"""Regression tests for development user seeding guardrails."""

from __future__ import annotations

import os
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from src.core.licensing.models import License, LicenseStatus, Organization
from src.core.user_models import UserProfile
from src.modules.tenant_management.models import Tenant

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DJANGO_USE_SQLITE_FOR_TESTS") == "1",
    reason="seed_default_users identity-scope regression requires PostgreSQL migrations",
)
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

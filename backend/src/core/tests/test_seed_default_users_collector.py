"""Local access collector regression tests for development seeding."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from src.core.licensing.models import Organization
from src.core.management.commands.seed_default_users import Command
from src.core.user_models import UserProfile

User = get_user_model()


def test_local_access_collector_includes_crm_configuration_and_dynamic_api_quotas() -> None:
    permissions, resources, capabilities = Command()._collect_local_access_contracts()

    assert "crm" in capabilities
    assert "module.crm" in capabilities
    assert "crm.configuration:read" in permissions
    assert "crm.configuration:read" in capabilities | permissions
    assert "crm.api.list" in resources
    assert "crm.api.retrieve" in resources
    assert "backup-recovery" in capabilities
    assert "backup-recovery.job" in resources
    assert "backup-jobs-per-period" in resources
    assert "active-schedules" in resources
    assert "provider-probes" in resources
    assert "integrity-verifications" in resources


def test_seeded_tenant_emails_extracts_configured_email_keys() -> None:
    assert isinstance(Command.__dict__["_seeded_tenant_emails"], staticmethod)
    assert Command._seeded_tenant_emails(
        (
            {"email": "admin@example.com", "role": "tenant_admin"},
            {"email": "user@example.com", "role": "tenant_user"},
        )
    ) == ("admin@example.com", "user@example.com")


@pytest.mark.django_db
def test_local_access_users_include_seeded_emails_and_active_tenant_admins() -> None:
    organization = Organization.objects.create(name="Local seed test", domain="local-seed.example")
    other_organization = Organization.objects.create(
        name="Other local seed test",
        domain="other-local-seed.example",
    )
    tenant_id = str(organization.id)
    other_tenant_id = str(other_organization.id)
    password = "LocalSeedAccess123!"  # pragma: allowlist secret
    seeded = User.objects.create_user(
        username="seeded@example.com",
        email="seeded@example.com",
        password=password,
    )
    tenant_admin = User.objects.create_user(
        username="tenant-admin@example.com",
        email="tenant-admin@example.com",
        password=password,
    )
    tenant_user = User.objects.create_user(
        username="tenant-user@example.com",
        email="tenant-user@example.com",
        password=password,
    )
    inactive_admin = User.objects.create_user(
        username="inactive-admin@example.com",
        email="inactive-admin@example.com",
        password=password,
        is_active=False,
    )
    other_tenant_admin = User.objects.create_user(
        username="other-admin@example.com",
        email="other-admin@example.com",
        password=password,
    )

    UserProfile.objects.update_or_create(user=seeded, defaults={"tenant_id": None, "tenant_role": None})
    UserProfile.objects.update_or_create(
        user=tenant_admin,
        defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
    )
    UserProfile.objects.update_or_create(
        user=tenant_user,
        defaults={"tenant_id": tenant_id, "tenant_role": "tenant_user"},
    )
    UserProfile.objects.update_or_create(
        user=inactive_admin,
        defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
    )
    UserProfile.objects.update_or_create(
        user=other_tenant_admin,
        defaults={"tenant_id": other_tenant_id, "tenant_role": "tenant_admin"},
    )

    users = Command()._local_access_users(tenant_id, ("seeded@example.com",))

    assert tuple(user.email for user in users) == ("seeded@example.com", "tenant-admin@example.com")

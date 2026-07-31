"""Local access collector regression tests for development seeding."""

from __future__ import annotations

import ast
import uuid
from datetime import timedelta
from datetime import timezone as datetime_timezone

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from src.core.licensing.models import Organization
from src.core.management.commands import seed_default_users as seed_default_users_module
from src.core.management.commands.seed_default_users import Command
from src.core.tenancy.rls import tenant_context
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
    assert all(not resource.startswith("None.api.") for resource in resources)


def test_declared_action_quota_collector_handles_permission_map_shapes(tmp_path) -> None:
    permissions_file = tmp_path / "permissions.py"
    permissions_file.write_text(
        """
UNRELATED = {"ignored": []}
CRM_ACTION_PERMISSIONS = {
    99: [],
    "win_rate": [],
    " by_stage ": [],
    "bad-action": [],
    "after_invalid": [],
}
permission_map: dict[str, object] = {"predict": []}
wrapped = MappingProxyType({"not_a_target": []})
permission_map = MappingProxyType({"pipeline": []})
self.permission_map = {"attr_map": []}
view.CRM_ACTION_PERMISSIONS = {"attr_action": []}
""",
        encoding="utf-8",
    )
    resources: set[str] = set()

    Command()._collect_declared_action_quotas("crm", permissions_file, resources)

    assert resources == {
        "crm.api.attr_action",
        "crm.api.attr_map",
        "crm.api.after_invalid",
        "crm.api.by_stage",
        "crm.api.pipeline",
        "crm.api.predict",
        "crm.api.win_rate",
    }


def test_permission_action_dictionary_accepts_only_governed_targets() -> None:
    command = Command()

    ignored = ast.parse('OTHER = {"ignored": []}').body[0]
    direct = ast.parse('CRM_ACTION_PERMISSIONS = {"win_rate": []}').body[0]
    annotated = ast.parse('permission_map: dict[str, object] = {"predict": []}').body[0]
    wrapped = ast.parse('permission_map = MappingProxyType({"pipeline": []})').body[0]
    attribute = ast.parse('view.permission_map = {"attr_map": []}').body[0]
    empty_annotation = ast.parse("permission_map: dict[str, object]").body[0]

    assert command._permission_action_dictionary(ignored) is None
    assert command._permission_action_dictionary(direct) is not None
    assert command._permission_action_dictionary(annotated) is not None
    assert command._permission_action_dictionary(wrapped) is not None
    assert command._permission_action_dictionary(attribute) is not None
    assert command._permission_action_dictionary(empty_annotation) is None


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


@pytest.mark.django_db
def test_create_or_update_user_reconciles_existing_password_without_force() -> None:
    old_password = "LocalSeedOld123!"  # pragma: allowlist secret
    new_password = "LocalSeedNew123!"  # pragma: allowlist secret
    user = User.objects.create_user(
        username="seed-password@example.com",
        email="seed-password@example.com",
        password=old_password,
        is_staff=False,
        is_superuser=False,
    )
    UserProfile.objects.get(user=user)

    updated, created = Command()._create_or_update_user(
        email="seed-password@example.com",
        password=new_password,
        username="seed-password-renamed@example.com",
        is_staff=True,
        is_superuser=True,
        platform_role="platform_operator",
        tenant_id=None,
        tenant_role=None,
        force=False,
    )

    assert created is False
    assert updated.check_password(new_password)
    assert not updated.check_password(old_password)
    assert updated.username == "seed-password-renamed@example.com"
    assert updated.is_staff is True
    assert updated.is_superuser is True


@pytest.mark.django_db
def test_bootstrap_local_access_creates_exact_permission_set_membership_grant_and_limits(monkeypatch) -> None:
    from src.core.access.entitlements import Entitlement, Quota
    from src.modules.security_access_control.models import (
        Permission,
        PermissionSet,
        PermissionSetPermission,
        UserPermissionSet,
    )

    fixed_now = timezone.datetime(2026, 1, 15, 12, 0, tzinfo=datetime_timezone.utc)
    monkeypatch.setattr(seed_default_users_module.timezone, "now", lambda: fixed_now)

    tenant_uuid = uuid.uuid4()
    user = User.objects.create_user(
        username="local-access@example.com",
        email="local-access@example.com",
        password="LocalAccess123!",  # pragma: allowlist secret
    )
    command = Command()
    monkeypatch.setattr(
        command,
        "_collect_local_access_contracts",
        lambda: ({"crm.configuration:read"}, {"crm.api.win_rate"}, {"crm"}),
    )

    command._bootstrap_local_access(str(tenant_uuid), (user,))

    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, "saraise:seed:local-access@example.com")
    permission = Permission.objects.get(module="crm", resource="configuration", action="read")
    with tenant_context(tenant_uuid):
        permission_set = PermissionSet.objects.for_tenant(tenant_uuid).get(name="Local development administrator")
        membership = PermissionSetPermission.objects.for_tenant(tenant_uuid).get(
            permission_set=permission_set,
            permission=permission,
            removed_at__isnull=True,
        )
        grant = UserPermissionSet.objects.for_tenant(tenant_uuid).get(
            user=user,
            permission_set=permission_set,
            revoked_at__isnull=True,
        )

    assert permission_set.description == "Explicit seeded grant for local end-to-end UAT."
    assert permission_set.default_duration_days == 365
    assert permission_set.is_active is True
    assert permission_set.is_deleted is False
    assert permission_set.deleted_at is None
    assert permission_set.created_by == actor_id
    assert permission_set.updated_by == actor_id
    assert membership.added_by == actor_id
    assert grant.expires_at == fixed_now + timedelta(days=365)
    assert grant.granted_by == actor_id
    assert grant.reason == "Seeded local development UAT access"
    assert Entitlement.objects.get(tenant_id=tenant_uuid, capability="crm").enabled is True
    assert Entitlement.objects.get(tenant_id=tenant_uuid, capability="crm.configuration:read").enabled is True
    quota = Quota.objects.get(tenant_id=tenant_uuid, resource="crm.api.win_rate")
    assert quota.limit == 1_000_000
    assert quota.remaining == 1_000_000


@pytest.mark.django_db
def test_bootstrap_local_access_reactivates_existing_set_and_refreshes_existing_grant(monkeypatch) -> None:
    from src.core.access.entitlements import Entitlement, Quota
    from src.modules.security_access_control.models import (
        Permission,
        PermissionSet,
        PermissionSetPermission,
        UserPermissionSet,
    )

    fixed_now = timezone.datetime(2026, 2, 20, 9, 30, tzinfo=datetime_timezone.utc)
    monkeypatch.setattr(seed_default_users_module.timezone, "now", lambda: fixed_now)

    tenant_uuid = uuid.uuid4()
    old_actor = uuid.uuid4()
    user = User.objects.create_user(
        username="refresh-access@example.com",
        email="refresh-access@example.com",
        password="LocalAccess123!",  # pragma: allowlist secret
    )
    permission = Permission.objects.create(
        module="crm",
        resource="configuration",
        action="read",
        name="crm.configuration:read",
        description="Existing permission",
        risk_level=Permission.RiskLevel.LOW,
    )
    with tenant_context(tenant_uuid):
        permission_set = PermissionSet.objects.for_tenant(tenant_uuid).create(
            tenant_id=tenant_uuid,
            name="Local development administrator",
            description="stale",
            default_duration_days=30,
            is_active=False,
            is_deleted=True,
            deleted_at=fixed_now - timedelta(days=1),
            created_by=old_actor,
            updated_by=old_actor,
        )
        PermissionSetPermission.objects.create(
            tenant_id=tenant_uuid,
            permission_set=permission_set,
            permission=permission,
            added_by=old_actor,
        )
        grant = UserPermissionSet.objects.create(
            tenant_id=tenant_uuid,
            user=user,
            permission_set=permission_set,
            granted_at=fixed_now - timedelta(days=30),
            expires_at=fixed_now + timedelta(days=7),
            granted_by=old_actor,
            reason="stale",
        )

    command = Command()
    monkeypatch.setattr(
        command,
        "_collect_local_access_contracts",
        lambda: ({"crm.configuration:read"}, {"crm.api.win_rate"}, {"crm"}),
    )

    command._bootstrap_local_access(str(tenant_uuid), (user,))

    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, "saraise:seed:refresh-access@example.com")
    permission_set.refresh_from_db()
    grant.refresh_from_db()
    with tenant_context(tenant_uuid):
        membership_count = (
            PermissionSetPermission.objects.for_tenant(tenant_uuid)
            .filter(
                permission_set=permission_set,
                permission=permission,
                removed_at__isnull=True,
            )
            .count()
        )

    assert permission_set.is_active is True
    assert permission_set.is_deleted is False
    assert permission_set.deleted_at is None
    assert permission_set.updated_by == actor_id
    assert membership_count == 1
    assert grant.expires_at == fixed_now + timedelta(days=365)
    assert grant.reason == "Seeded local development UAT access"
    assert Entitlement.objects.get(tenant_id=tenant_uuid, capability="crm.configuration:read").enabled is True
    assert Quota.objects.get(tenant_id=tenant_uuid, resource="crm.configuration:read").remaining == 1_000_000


@pytest.mark.django_db
def test_bootstrap_local_access_repairs_inactive_and_deleted_sets_independently(monkeypatch) -> None:
    from src.modules.security_access_control.models import PermissionSet

    fixed_now = timezone.datetime(2026, 3, 10, 8, 0, tzinfo=datetime_timezone.utc)
    monkeypatch.setattr(seed_default_users_module.timezone, "now", lambda: fixed_now)
    command = Command()
    monkeypatch.setattr(command, "_collect_local_access_contracts", lambda: (set(), set(), set()))

    inactive_tenant = uuid.uuid4()
    deleted_tenant = uuid.uuid4()
    old_actor = uuid.uuid4()
    for tenant_uuid, is_active, is_deleted in (
        (inactive_tenant, False, False),
        (deleted_tenant, True, True),
    ):
        with tenant_context(tenant_uuid):
            PermissionSet.objects.for_tenant(tenant_uuid).create(
                tenant_id=tenant_uuid,
                name="Local development administrator",
                description="stale",
                default_duration_days=30,
                is_active=is_active,
                is_deleted=is_deleted,
                deleted_at=fixed_now - timedelta(days=1) if is_deleted else None,
                created_by=old_actor,
                updated_by=old_actor,
            )

        command._bootstrap_local_access(str(tenant_uuid), ())

        with tenant_context(tenant_uuid):
            permission_set = PermissionSet.objects.for_tenant(tenant_uuid).get(
                name="Local development administrator",
            )
        assert permission_set.is_active is True
        assert permission_set.is_deleted is False
        assert permission_set.deleted_at is None


@pytest.mark.django_db
def test_bootstrap_local_access_refreshes_exact_expiry_grant_reason(monkeypatch) -> None:
    from src.modules.security_access_control.models import PermissionSet, UserPermissionSet

    fixed_now = timezone.datetime(2026, 4, 5, 14, 0, tzinfo=datetime_timezone.utc)
    monkeypatch.setattr(seed_default_users_module.timezone, "now", lambda: fixed_now)
    tenant_uuid = uuid.uuid4()
    old_actor = uuid.uuid4()
    user = User.objects.create_user(
        username="exact-expiry@example.com",
        email="exact-expiry@example.com",
        password="LocalAccess123!",  # pragma: allowlist secret
    )
    with tenant_context(tenant_uuid):
        permission_set = PermissionSet.objects.for_tenant(tenant_uuid).create(
            tenant_id=tenant_uuid,
            name="Local development administrator",
            description="active",
            default_duration_days=365,
            is_active=True,
            is_deleted=False,
            created_by=old_actor,
            updated_by=old_actor,
        )
        grant = UserPermissionSet.objects.create(
            tenant_id=tenant_uuid,
            user=user,
            permission_set=permission_set,
            granted_at=fixed_now - timedelta(days=1),
            expires_at=fixed_now + timedelta(days=365),
            granted_by=old_actor,
            reason="stale",
        )

    command = Command()
    monkeypatch.setattr(command, "_collect_local_access_contracts", lambda: (set(), set(), set()))

    command._bootstrap_local_access(str(tenant_uuid), (user,))

    grant.refresh_from_db()
    assert grant.expires_at == fixed_now + timedelta(days=365)
    assert grant.reason == "Seeded local development UAT access"

"""Governed-envelope isolation plus nested/action immutability proofs."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from src.core.testing.tenant_contract import TenantIsolationContract
from src.modules.security_access_control.api import GovernedSecurityViewSet
from src.modules.security_access_control.models import (
    FieldSecurity,
    Permission,
    PermissionSet,
    PermissionSetPermission,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfile,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/security-access-control"


@pytest.fixture(autouse=True)
def authorize_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GovernedSecurityViewSet, "get_permissions", lambda self: [IsAuthenticated()])


class V2IsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response: object) -> list[dict[str, object]]:
        return response.json()["data"]

    def test_cross_tenant_delete_is_denied_and_unchanged(self) -> None:
        """Supply required domain reason while proving the foreign row is invisible."""

        _, foreign = self._validated_rows()
        before = self._row_snapshot(foreign)
        response = self.get_client().delete(f"{self.get_detail_url(foreign)}?reason=isolation-proof")
        assert response.status_code == 404, response.content
        assert self._row_snapshot(foreign) == before


@pytest.fixture
def role_pair(tenant_a, tenant_b) -> tuple[Role, Role]:
    return (
        Role.objects.create(tenant_id=tenant_a.id, name="Own role", code="own_role"),
        Role.objects.create(tenant_id=tenant_b.id, name="Foreign role", code="foreign_role"),
    )


@pytest.fixture
def set_pair(tenant_a, tenant_b) -> tuple[PermissionSet, PermissionSet]:
    return (
        PermissionSet.objects.create(tenant_id=tenant_a.id, name="Own set"),
        PermissionSet.objects.create(tenant_id=tenant_b.id, name="Foreign set"),
    )


@pytest.fixture
def profile_pair(tenant_a, tenant_b) -> tuple[SecurityProfile, SecurityProfile]:
    return (
        SecurityProfile.objects.create(tenant_id=tenant_a.id, name="Own profile"),
        SecurityProfile.objects.create(tenant_id=tenant_b.id, name="Foreign profile"),
    )


class TestRoleIsolation(V2IsolationContract):
    model = Role
    list_url = f"{BASE}/roles/"
    detail_url_template = f"{BASE}/roles/{{pk}}/"
    create_payload = {"name": "Spoof role", "code": "spoof_role", "tenant_id": str(uuid.uuid4())}
    update_payload = {"name": "Cross tenant"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, role_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = role_pair


class TestPermissionSetIsolation(V2IsolationContract):
    model = PermissionSet
    list_url = f"{BASE}/permission-sets/"
    detail_url_template = f"{BASE}/permission-sets/{{pk}}/"
    create_payload = {"name": "Spoof set", "tenant_id": str(uuid.uuid4())}
    update_payload = {"name": "Cross tenant"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, set_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = set_pair


class TestSecurityProfileIsolation(V2IsolationContract):
    model = SecurityProfile
    list_url = f"{BASE}/security-profiles/"
    detail_url_template = f"{BASE}/security-profiles/{{pk}}/"
    create_payload = {"name": "Spoof profile", "tenant_id": str(uuid.uuid4())}
    update_payload = {"description": "Cross tenant"}

    @pytest.fixture(autouse=True)
    def context(self, authenticated_tenant_a_client, profile_pair) -> None:
        self.client = authenticated_tenant_a_client
        self.tenant_a_row, self.tenant_b_row = profile_pair


def snapshot(row: object) -> tuple[object, ...]:
    return tuple(getattr(row, field.attname) for field in row._meta.concrete_fields)


def assert_foreign_unchanged(client, row, collection: str, update: dict[str, object]) -> None:
    row.refresh_from_db()
    before = snapshot(row)
    path = f"{BASE}/{collection}/{row.id}/"
    assert client.get(path).status_code == 404
    assert client.patch(path, update, format="json").status_code == 404
    assert client.delete(f"{path}?reason=foreign").status_code == 404
    row.refresh_from_db()
    assert snapshot(row) == before


def test_every_tenant_list_and_detail_excludes_foreign_resources(
    authenticated_tenant_a_client,
    tenant_a,
    tenant_b,
    tenant_a_user,
    tenant_b_user,
    role_pair,
    set_pair,
    profile_pair,
) -> None:
    own_role, foreign_role = role_pair
    own_set, foreign_set = set_pair
    own_profile, foreign_profile = profile_pair
    actor = tenant_a_user.id
    foreign_actor = tenant_b_user.id
    pairs = [
        ("user-roles", UserRole.objects.create(tenant_id=tenant_a.id, user=tenant_a_user, role=own_role, assigned_by=actor, reason="own"), UserRole.objects.create(tenant_id=tenant_b.id, user=tenant_b_user, role=foreign_role, assigned_by=foreign_actor, reason="foreign")),
        ("user-permission-sets", UserPermissionSet.objects.create(tenant_id=tenant_a.id, user=tenant_a_user, permission_set=own_set, expires_at=timezone.now() + timedelta(days=1), granted_by=actor, reason="own"), UserPermissionSet.objects.create(tenant_id=tenant_b.id, user=tenant_b_user, permission_set=foreign_set, expires_at=timezone.now() + timedelta(days=1), granted_by=foreign_actor, reason="foreign")),
        ("field-security", FieldSecurity.objects.create(tenant_id=tenant_a.id, module="m", resource="r", field="f", role=own_role), FieldSecurity.objects.create(tenant_id=tenant_b.id, module="m", resource="r", field="f", role=foreign_role)),
        ("row-security-rules", RowSecurityRule.objects.create(tenant_id=tenant_a.id, module="m", resource="r", role=own_role, filter_criteria={"op": "tenant", "field": "tenant_id"}), RowSecurityRule.objects.create(tenant_id=tenant_b.id, module="m", resource="r", role=foreign_role, filter_criteria={"op": "tenant", "field": "tenant_id"})),
        ("security-profile-assignments", SecurityProfileAssignment.objects.create(tenant_id=tenant_a.id, security_profile=own_profile, user=tenant_a_user, assigned_by=actor, reason="own"), SecurityProfileAssignment.objects.create(tenant_id=tenant_b.id, security_profile=foreign_profile, user=tenant_b_user, assigned_by=foreign_actor, reason="foreign")),
        ("audit-logs", SecurityAuditLog.objects.create(tenant_id=tenant_a.id, action="own", actor_id=actor, resource_type="test", correlation_id="own"), SecurityAuditLog.objects.create(tenant_id=tenant_b.id, action="foreign", actor_id=foreign_actor, resource_type="test", correlation_id="foreign")),
    ]
    for collection, own, foreign in pairs:
        response = authenticated_tenant_a_client.get(f"{BASE}/{collection}/")
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()["data"]}
        assert str(own.id) in ids and str(foreign.id) not in ids
        assert authenticated_tenant_a_client.get(f"{BASE}/{collection}/{foreign.id}/").status_code == 404


def test_cross_tenant_nested_membership_decision_assignment_simulation_and_mutations_leave_bytes(
    authenticated_tenant_a_client,
    tenant_b,
    tenant_b_user,
    role_pair,
    set_pair,
    profile_pair,
) -> None:
    _, foreign_role = role_pair
    _, foreign_set = set_pair
    _, foreign_profile = profile_pair
    permission = Permission.objects.create(module="m", resource="r", action="read", name="Read")
    role_decision = RolePermission.objects.create(tenant_id=tenant_b.id, role=foreign_role, permission=permission)
    membership = PermissionSetPermission.objects.create(tenant_id=tenant_b.id, permission_set=foreign_set, permission=permission, added_by=tenant_b_user.id)
    role_decision.refresh_from_db(); membership.refresh_from_db()
    before_role, before_set = snapshot(role_decision), snapshot(membership)
    assert authenticated_tenant_a_client.post(f"{BASE}/roles/{foreign_role.id}/permissions/", {"permission_id": str(permission.id), "is_granted": False}, format="json").status_code == 404
    assert authenticated_tenant_a_client.delete(f"{BASE}/roles/{foreign_role.id}/permissions/{permission.id}/").status_code == 404
    assert authenticated_tenant_a_client.put(f"{BASE}/permission-sets/{foreign_set.id}/permissions/", {"permission_ids": []}, format="json").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/user-roles/", {"user_id": str(tenant_b_user.id), "role_id": str(foreign_role.id), "reason": "spoof"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/user-permission-sets/", {"user_id": str(tenant_b_user.id), "permission_set_id": str(foreign_set.id), "duration_days": 1, "reason": "spoof"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/security-profile-assignments/", {"security_profile_id": str(foreign_profile.id), "user_id": str(tenant_b_user.id), "reason": "spoof"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.post(f"{BASE}/access-decisions/simulate/", {"subject_id": str(tenant_b_user.id), "permission_code": permission.code, "resource_context": {}}, format="json").status_code == 404
    role_decision.refresh_from_db(); membership.refresh_from_db()
    assert snapshot(role_decision) == before_role and snapshot(membership) == before_set


def test_foreign_update_delete_for_assignment_rule_and_profile_are_404(
    authenticated_tenant_a_client, tenant_b, tenant_b_user, role_pair, set_pair, profile_pair
) -> None:
    _, role = role_pair; _, permission_set = set_pair; _, profile = profile_pair
    actor = tenant_b_user.id
    rows = [
        (UserRole.objects.create(tenant_id=tenant_b.id, user=tenant_b_user, role=role, assigned_by=actor, reason="foreign"), "user-roles", {"reason": "changed"}),
        (UserPermissionSet.objects.create(tenant_id=tenant_b.id, user=tenant_b_user, permission_set=permission_set, expires_at=timezone.now() + timedelta(days=1), granted_by=actor, reason="foreign"), "user-permission-sets", {"expires_at": (timezone.now() + timedelta(days=2)).isoformat()}),
        (FieldSecurity.objects.create(tenant_id=tenant_b.id, module="m", resource="r", field="f2", role=role), "field-security", {"visibility": "hidden"}),
        (RowSecurityRule.objects.create(tenant_id=tenant_b.id, module="m", resource="r2", role=role, filter_criteria={"op": "tenant", "field": "tenant_id"}), "row-security-rules", {"priority": 10}),
        (SecurityProfileAssignment.objects.create(tenant_id=tenant_b.id, security_profile=profile, user=tenant_b_user, assigned_by=actor, reason="foreign"), "security-profile-assignments", {"precedence": 10}),
    ]
    for row, collection, update in rows:
        assert_foreign_unchanged(authenticated_tenant_a_client, row, collection, update)

"""Governed v2 API contract tests using real session and CSRF authentication."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from src.core.api import OperationFailed
from src.modules.security_access_control.api import (
    GovernedSecurityViewSet,
    SecurityRateThrottle,
    _actor,
    _apply_filters,
    _call,
    _deletion_reason,
    _optional_tenant,
    _path_uuid,
    _tenant,
)
from src.modules.security_access_control.models import Permission, Role
from src.modules.security_access_control.services import (
    SecurityConfigurationMissing,
    SecurityConflict,
    SecurityDependencyUnavailable,
    SecurityNotFound,
    SecurityValidationError,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db
BASE = "/api/v2/security-access-control"


@pytest.fixture(autouse=True)
def authorize_api_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep HTTP contract tests orthogonal to branch-complete authorization tests."""

    monkeypatch.setattr(GovernedSecurityViewSet, "get_permissions", lambda self: [IsAuthenticated()])


def data(response) -> object:
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["correlation_id"] and body["meta"]["timestamp"]
    return body["data"]


def test_authentication_is_401_and_unsupported_methods_are_405(api_client) -> None:
    assert api_client.get(f"{BASE}/roles/").status_code == 401
    assert api_client.put(f"{BASE}/permissions/{uuid.uuid4()}/", {}, format="json").status_code == 401


def test_roles_crud_nested_permissions_envelope_filters_search_order_and_pagination(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    permission = Permission.objects.create(module="finance", resource="journals", action="read", name="Read journals")
    created = authenticated_tenant_a_client.post(
        f"{BASE}/roles/",
        {
            "name": "Analyst",
            "code": "analyst",
            "role_type": "functional",
            "tenant_id": str(tenant_b.id),
        },
        format="json",
        HTTP_X_CORRELATION_ID="corr-role-create",
    )
    assert created.status_code == 201, created.content
    role = data(created)
    assert role["code"] == "analyst" and "tenant_id" not in role
    stored = Role.objects.get(pk=role["id"])
    assert stored.tenant_id == tenant_a.id
    for number in range(27):
        Role.objects.create(tenant_id=tenant_a.id, name=f"Role {number:02}", code=f"role_{number:02}")
    Role.objects.create(tenant_id=tenant_b.id, name="Foreign", code="foreign")
    listing = authenticated_tenant_a_client.get(f"{BASE}/roles/?search=Role&ordering=-name&page_size=25")
    assert listing.status_code == 200
    rows = data(listing)
    assert len(rows) == 25 and all(row["name"] != "Foreign" for row in rows)
    assert listing.json()["meta"]["pagination"]["page_size"] == 25
    too_large = authenticated_tenant_a_client.get(f"{BASE}/roles/?page_size=101")
    assert too_large.status_code == 200
    assert too_large.json()["meta"]["pagination"]["page_size"] == 100
    detail = authenticated_tenant_a_client.get(f"{BASE}/roles/{role['id']}/")
    assert detail.status_code == 200 and data(detail)["id"] == role["id"]
    patched = authenticated_tenant_a_client.patch(
        f"{BASE}/roles/{role['id']}/", {"description": "Updated"}, format="json"
    )
    assert patched.status_code == 200 and data(patched)["description"] == "Updated"
    nested = authenticated_tenant_a_client.post(
        f"{BASE}/roles/{role['id']}/permissions/",
        {"permission_id": str(permission.id), "is_granted": False},
        format="json",
    )
    assert nested.status_code == 200
    removed = authenticated_tenant_a_client.delete(f"{BASE}/roles/{role['id']}/permissions/{permission.id}/")
    assert removed.status_code == 204 and not removed.content
    deleted = authenticated_tenant_a_client.delete(f"{BASE}/roles/{role['id']}/?reason=Retired")
    assert deleted.status_code == 204 and not deleted.content
    stored.refresh_from_db()
    assert stored.is_deleted


def test_cross_tenant_detail_update_delete_are_404_and_byte_unchanged(authenticated_tenant_a_client, tenant_b) -> None:
    foreign = Role.objects.create(tenant_id=tenant_b.id, name="Foreign", code="foreign")
    before = tuple(getattr(foreign, field.attname) for field in foreign._meta.concrete_fields)
    path = f"{BASE}/roles/{foreign.id}/"
    assert authenticated_tenant_a_client.get(path).status_code == 404
    assert authenticated_tenant_a_client.patch(path, {"name": "Changed"}, format="json").status_code == 404
    assert authenticated_tenant_a_client.delete(f"{path}?reason=No").status_code == 404
    foreign.refresh_from_db()
    assert tuple(getattr(foreign, field.attname) for field in foreign._meta.concrete_fields) == before


def test_malformed_detail_id_returns_404_not_500(authenticated_tenant_a_client) -> None:
    response = authenticated_tenant_a_client.get(f"{BASE}/user-roles/__uat_invalid_id__/")

    assert response.status_code == 404


def test_catalog_read_only_filter_search_order_and_methods(authenticated_tenant_a_client) -> None:
    permission = Permission.objects.create(
        module="finance", resource="journals", action="read", name="Read journals", risk_level="low"
    )
    listing = authenticated_tenant_a_client.get(
        f"{BASE}/permissions/?module=finance&resource=journals&action=read&risk_level=low&search=journal&ordering=resource"  # noqa: E501
    )
    assert listing.status_code == 200 and data(listing)[0]["code"] == permission.code
    assert authenticated_tenant_a_client.get(f"{BASE}/permissions/{permission.id}/").status_code == 200
    assert authenticated_tenant_a_client.post(f"{BASE}/permissions/", {}, format="json").status_code == 405
    assert (
        authenticated_tenant_a_client.patch(f"{BASE}/permissions/{permission.id}/", {}, format="json").status_code
        == 405
    )
    assert authenticated_tenant_a_client.delete(f"{BASE}/permissions/{permission.id}/").status_code == 405


def test_assignments_permission_sets_profiles_audit_and_simulation_end_to_end(
    authenticated_tenant_a_client, tenant_a, tenant_a_user
) -> None:
    permission = Permission.objects.create(module="finance", resource="journals", action="read", name="Read")
    role = authenticated_tenant_a_client.post(
        f"{BASE}/roles/", {"name": "Operator", "code": "operator", "role_type": "custom"}, format="json"
    ).json()["data"]
    assert (
        authenticated_tenant_a_client.post(
            f"{BASE}/roles/{role['id']}/permissions/",
            {"permission_id": str(permission.id), "is_granted": True},
            format="json",
        ).status_code
        == 200
    )
    assignment = authenticated_tenant_a_client.post(
        f"{BASE}/user-roles/",
        {"user_id": str(tenant_a_user.id), "role_id": role["id"], "reason": "Approved"},
        format="json",
    )
    assert assignment.status_code == 201, assignment.content
    assignment_id = data(assignment)["id"]
    assert (
        authenticated_tenant_a_client.patch(
            f"{BASE}/user-roles/{assignment_id}/", {"reason": "Extended"}, format="json"
        ).status_code
        == 200
    )
    permission_set = authenticated_tenant_a_client.post(
        f"{BASE}/permission-sets/",
        {"name": "Close", "default_duration_days": 7, "permission_ids": [str(permission.id)]},
        format="json",
    )
    assert permission_set.status_code == 201, permission_set.content
    set_id = data(permission_set)["id"]
    assert (
        authenticated_tenant_a_client.put(
            f"{BASE}/permission-sets/{set_id}/permissions/",
            {"permission_ids": [str(permission.id)]},
            format="json",
        ).status_code
        == 200
    )
    grant = authenticated_tenant_a_client.post(
        f"{BASE}/user-permission-sets/",
        {"user_id": str(tenant_a_user.id), "permission_set_id": set_id, "reason": "Close"},
        format="json",
    )
    assert grant.status_code == 201, grant.content
    grant_id = data(grant)["id"]
    assert (
        authenticated_tenant_a_client.patch(
            f"{BASE}/user-permission-sets/{grant_id}/",
            {"expires_at": (timezone.now() + timedelta(days=8)).isoformat(), "reason": "Extended"},
            format="json",
        ).status_code
        == 200
    )
    profile = authenticated_tenant_a_client.post(
        f"{BASE}/security-profiles/",
        {"name": "Restricted", "profile_type": "restricted", "session_timeout_minutes": 30},
        format="json",
    )
    assert profile.status_code == 201, profile.content
    profile_id = data(profile)["id"]
    profile_assignment = authenticated_tenant_a_client.post(
        f"{BASE}/security-profile-assignments/",
        {
            "security_profile_id": profile_id,
            "user_id": str(tenant_a_user.id),
            "reason": "Restricted access",
        },
        format="json",
    )
    assert profile_assignment.status_code == 201, profile_assignment.content
    simulation = authenticated_tenant_a_client.post(
        f"{BASE}/access-decisions/simulate/",
        {
            "subject_id": str(tenant_a_user.id),
            "permission_code": permission.code,
            "resource_context": {},
        },
        format="json",
        HTTP_X_CORRELATION_ID="corr-simulation",
    )
    assert simulation.status_code == 200, simulation.content
    assert data(simulation)["allowed"] is True
    audit = authenticated_tenant_a_client.get(f"{BASE}/audit-logs/?correlation_id=corr-simulation")
    assert audit.status_code == 200 and len(data(audit)) == 1
    audit_id = audit.json()["data"][0]["id"]
    assert authenticated_tenant_a_client.get(f"{BASE}/audit-logs/{audit_id}/").status_code == 200
    assert authenticated_tenant_a_client.patch(f"{BASE}/audit-logs/{audit_id}/", {}, format="json").status_code == 405
    assert authenticated_tenant_a_client.delete(f"{BASE}/audit-logs/{audit_id}/").status_code == 405
    assert (
        authenticated_tenant_a_client.delete(f"{BASE}/user-roles/{assignment_id}/?reason=Complete").status_code == 204
    )
    assert (
        authenticated_tenant_a_client.delete(f"{BASE}/user-permission-sets/{grant_id}/?reason=Complete").status_code
        == 204
    )


def test_validation_conflict_bad_order_audit_range_and_saas_control_plane_error(authenticated_tenant_a_client) -> None:
    invalid = authenticated_tenant_a_client.post(f"{BASE}/roles/", {"name": "Bad", "code": "Not Valid"}, format="json")
    assert invalid.status_code == 400 and invalid.json()["error"]["correlation_id"]
    created = authenticated_tenant_a_client.post(f"{BASE}/roles/", {"name": "Unique", "code": "unique"}, format="json")
    assert created.status_code == 201
    conflict = authenticated_tenant_a_client.post(
        f"{BASE}/roles/", {"name": "Duplicate", "code": "unique"}, format="json"
    )
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "CONFLICT"
    assert authenticated_tenant_a_client.get(f"{BASE}/roles/?ordering=tenant_id").status_code == 400
    start = (timezone.now() - timedelta(days=91)).isoformat()
    end = timezone.now().isoformat()
    assert authenticated_tenant_a_client.get(f"{BASE}/audit-logs/?from={start}&to={end}").status_code == 400
    with override_settings(SARAISE_MODE="saas"):
        response = authenticated_tenant_a_client.post(f"{BASE}/roles/", {"name": "SaaS", "code": "saas"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTROL_PLANE_OWNED"


def test_throttling_returns_429(authenticated_tenant_a_client, monkeypatch) -> None:
    cache.clear()
    monkeypatch.setattr(SecurityRateThrottle, "rate", "1/min")
    assert authenticated_tenant_a_client.get(f"{BASE}/roles/").status_code == 200
    assert authenticated_tenant_a_client.get(f"{BASE}/roles/").status_code == 429
    cache.clear()


def test_security_api_helpers_fail_closed_for_tenant_actor_and_path_inputs(tenant_a) -> None:
    request = SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id=str(tenant_a.id))))
    assert _optional_tenant(request) == tenant_a.id
    assert request.tenant_id == tenant_a.id
    assert _tenant(request) == tenant_a.id

    with pytest.raises(PermissionDenied):
        _tenant(SimpleNamespace(user=SimpleNamespace(profile=SimpleNamespace(tenant_id=None))))
    with pytest.raises(PermissionDenied):
        _optional_tenant(SimpleNamespace(tenant_id="not-a-uuid", user=SimpleNamespace()))
    with pytest.raises(PermissionDenied):
        _actor(SimpleNamespace(user=SimpleNamespace(id=None)))

    integer_actor = _actor(SimpleNamespace(user=SimpleNamespace(id=42)))
    assert integer_actor == uuid.uuid5(uuid.NAMESPACE_URL, "saraise:user:42")
    assert _path_uuid(str(tenant_a.id)) == tenant_a.id
    with pytest.raises(NotFound):
        _path_uuid("not-a-uuid")


def test_security_call_adapter_maps_domain_errors_to_drf_contracts() -> None:
    assert _call(lambda: "ok") == "ok"

    with pytest.raises(NotFound):
        _call(lambda: (_ for _ in ()).throw(SecurityNotFound("missing")))
    with pytest.raises(OperationFailed) as conflict:
        _call(lambda: (_ for _ in ()).throw(SecurityConflict("duplicate")))
    assert conflict.value.error_code == "CONFLICT"
    assert conflict.value.status_code == 409
    with pytest.raises(ValidationError) as invalid:
        _call(lambda: (_ for _ in ()).throw(SecurityValidationError("bad", detail={"field": ["bad"]})))
    assert invalid.value.detail["field"] == ["bad"]
    with pytest.raises(OperationFailed) as missing_config:
        _call(lambda: (_ for _ in ()).throw(SecurityConfigurationMissing("missing config")))
    assert missing_config.value.error_code == "SECURITY_CONFIGURATION_MISSING"
    with pytest.raises(OperationFailed) as dependency:
        _call(lambda: (_ for _ in ()).throw(SecurityDependencyUnavailable("policy down")))
    assert dependency.value.error_code == "SECURITY_DEPENDENCY_UNAVAILABLE"


def test_security_filter_and_deletion_helpers_parse_booleans_and_require_reason(tenant_a) -> None:
    active = Role.objects.create(tenant_id=tenant_a.id, name="Active", code="active", is_active=True)
    Role.objects.create(tenant_id=tenant_a.id, name="Inactive", code="inactive", is_active=False)

    queryset = _apply_filters(Role.objects.for_tenant(tenant_a.id), {"is_active": "true"}, {"is_active": "is_active"})
    assert list(queryset) == [active]
    assert _deletion_reason(SimpleNamespace(query_params={"reason": " Retired "})) == "Retired"
    with pytest.raises(ValidationError):
        _deletion_reason(SimpleNamespace(query_params={}))


def test_security_rate_throttle_handles_missing_and_invalid_dynamic_policy(tenant_a, monkeypatch) -> None:
    throttle = SecurityRateThrottle()
    no_tenant = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), META={})
    assert throttle.allow_request(no_tenant, object()) is True

    malformed = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True, pk=1, id=uuid.uuid4()), tenant_id=tenant_a.id
    )
    monkeypatch.setattr(
        "src.modules.security_access_control.api.ConfigurationService.current",
        lambda *args, **kwargs: SimpleNamespace(document={"limits": []}),
    )
    assert SecurityRateThrottle().allow_request(malformed, object()) is False

    monkeypatch.setattr(
        "src.modules.security_access_control.api.ConfigurationService.current",
        lambda *args, **kwargs: (_ for _ in ()).throw(SecurityConfigurationMissing("missing")),
    )
    assert SecurityRateThrottle().allow_request(malformed, object()) is False

"""Transactional service behavior, evidence, and fail-closed evaluation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.db import DatabaseError
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.security_access_control.extensions import (
    ResourceFieldDescriptor,
    ResourceFieldType,
    ResourceSecurityDescriptor,
    SecurityExtensionDescriptor,
    register_security_extension,
    unregister_security_extension,
)
from src.modules.security_access_control.models import (
    FieldSecurity,
    Permission,
    PermissionSetPermission,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)
from src.modules.security_access_control.services import (
    AccessEvaluationService,
    AuditService,
    FieldSecurityService,
    PermissionCatalogService,
    PermissionSetService,
    RoleService,
    RowSecurityService,
    SecurityConflict,
    SecurityNotFound,
    SecurityProfileService,
    SecurityValidationError,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.fixture
def actor_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def correlation_id() -> str:
    return f"corr-{uuid.uuid4()}"


@pytest.fixture
def catalog() -> tuple[Permission, Permission]:
    return (
        Permission.objects.create(module="finance", resource="journals", action="read", name="Read journals"),
        Permission.objects.create(module="finance", resource="journals", action="delete", name="Delete journals"),
    )


@pytest.fixture
def resource_extension() -> SecurityExtensionDescriptor:
    descriptor = SecurityExtensionDescriptor(
        owner_manifest="finance-module-test",
        owner_version="1.0.0",
        permission_namespace="finance",
        permissions=(),
        resources=(
            ResourceSecurityDescriptor(
                module="finance",
                resource="journals",
                fields=(
                    ResourceFieldDescriptor("id", ResourceFieldType.UUID),
                    ResourceFieldDescriptor("owner_id", ResourceFieldType.UUID),
                    ResourceFieldDescriptor("amount", ResourceFieldType.DECIMAL),
                ),
                trusted_subject_attributes=("id",),
            ),
        ),
    )
    register_security_extension(descriptor)
    yield descriptor
    unregister_security_extension(descriptor.owner_manifest, expected_version=descriptor.owner_version)


def assert_evidence(tenant_id: uuid.UUID, resource_id: uuid.UUID, event_type: str) -> None:
    audit = SecurityAuditLog.objects.for_tenant(tenant_id).get(resource_id=resource_id, action=event_type)
    event = OutboxEvent.objects.get(id=audit.outbox_event_id)
    assert event.tenant_id == tenant_id
    assert event.event_type == event_type
    assert event.payload["correlation_id"] == audit.correlation_id


def test_role_service_full_lifecycle_permissions_assignments_and_cross_tenant_rejection(
    tenant_a, tenant_b, tenant_a_user, catalog, actor_id, correlation_id
) -> None:
    parent = RoleService.create_role(
        tenant_a.id,
        name="Finance parent",
        code="Finance Parent",
        role_type=Role.RoleType.FUNCTIONAL,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    role = RoleService.create_role(
        tenant_a.id,
        name="Finance child",
        code="finance_child",
        role_type=Role.RoleType.CUSTOM,
        parent_role_id=parent.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert role.code == "finance_child" and role.hierarchy_level == 1
    assert_evidence(tenant_a.id, role.id, "security.role.changed")
    updated = RoleService.update_role(
        tenant_a.id,
        role.id,
        changes={"description": "Updated"},
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert updated.description == "Updated"
    decision = RoleService.set_role_permission(
        tenant_a.id,
        role.id,
        catalog[0].id,
        is_granted=True,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert decision.is_granted
    assignment = RoleService.assign_role(
        tenant_a.id,
        tenant_a_user.id,
        role.id,
        valid_from=None,
        valid_until=timezone.now() + timedelta(days=1),
        reason="Approved",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assignment = RoleService.update_role_assignment(
        tenant_a.id,
        assignment.id,
        valid_from=None,
        valid_until=timezone.now() + timedelta(days=2),
        reason="Extended",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert assignment.reason == "Extended"
    first_revoked_at = RoleService.revoke_role_assignment(
        tenant_a.id,
        assignment.id,
        reason="Closed",
        actor_id=actor_id,
        correlation_id=correlation_id,
    ).revoked_at
    replay = RoleService.revoke_role_assignment(
        tenant_a.id,
        assignment.id,
        reason="Replay",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert replay.revoked_at == first_revoked_at
    RoleService.remove_role_permission(
        tenant_a.id,
        role.id,
        catalog[0].id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert not RolePermission.objects.filter(pk=decision.pk).exists()
    with pytest.raises(SecurityNotFound):
        RoleService.update_role(
            tenant_b.id,
            role.id,
            changes={"name": "Foreign"},
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    RoleService.delete_role(
        tenant_a.id,
        role.id,
        actor_id=actor_id,
        reason="Retired",
        correlation_id=correlation_id,
    )
    role.refresh_from_db()
    assert role.is_deleted and not role.is_active


def test_role_conflicts_validation_and_transaction_rolls_back_when_evidence_fails(
    tenant_a, actor_id, correlation_id, monkeypatch
) -> None:
    role = RoleService.create_role(
        tenant_a.id,
        name="System",
        code="system",
        role_type=Role.RoleType.SYSTEM,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    role.is_system = True
    role.save(update_fields=("is_system",))
    with pytest.raises(SecurityConflict):
        RoleService.delete_role(
            tenant_a.id,
            role.id,
            actor_id=actor_id,
            reason="No",
            correlation_id=correlation_id,
        )
    with pytest.raises(SecurityValidationError):
        RoleService.update_role(
            tenant_a.id,
            role.id,
            changes={"tenant_id": uuid.uuid4()},
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    monkeypatch.setattr(AuditService, "append", Mock(side_effect=DatabaseError("audit unavailable")))
    with pytest.raises(DatabaseError):
        RoleService.create_role(
            tenant_a.id,
            name="Rollback",
            code="rollback",
            role_type=Role.RoleType.CUSTOM,
            actor_id=actor_id,
            correlation_id="corr-rollback",
        )
    assert not Role.objects.for_tenant(tenant_a.id).filter(code="rollback").exists()
    assert not OutboxEvent.objects.filter(payload__correlation_id="corr-rollback").exists()


def test_permission_catalog_filters_resolves_registers_idempotently_and_rejects_drift(
    tenant_a, catalog, actor_id, correlation_id
) -> None:
    assert list(PermissionCatalogService.list_permissions(tenant_a.id, action="read")) == [catalog[0]]
    assert PermissionCatalogService.get_permission(tenant_a.id, catalog[0].id) == catalog[0]
    assert PermissionCatalogService.resolve_code(tenant_a.id, catalog[0].code) == catalog[0]
    with pytest.raises(SecurityValidationError):
        PermissionCatalogService.resolve_code(tenant_a.id, "legacy:bad:code")
    manifest = {
        "name": "inventory",
        "permission_namespace": "inventory",
        "permissions": [
            {"code": "inventory.items:read", "name": "Read items", "risk_level": "low"}
        ],
    }
    first = PermissionCatalogService.register_manifest_permissions(
        tenant_a.id,
        module_manifest=manifest,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    second = PermissionCatalogService.register_manifest_permissions(
        tenant_a.id,
        module_manifest=manifest,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert first[0].id == second[0].id
    drifted = {**manifest, "permissions": [{"code": "inventory.items:read", "name": "Changed"}]}
    with pytest.raises(SecurityConflict):
        PermissionCatalogService.register_manifest_permissions(
            tenant_a.id,
            module_manifest=drifted,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )


def test_permission_set_membership_grant_update_revoke_and_protection(
    tenant_a, tenant_a_user, catalog, actor_id, correlation_id
) -> None:
    item = PermissionSetService.create_permission_set(
        tenant_a.id,
        name="Quarter close",
        default_duration_days=7,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    PermissionSetService.set_permissions(
        tenant_a.id,
        item.id,
        permission_ids=[catalog[0].id, catalog[1].id],
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    PermissionSetService.set_permissions(
        tenant_a.id,
        item.id,
        permission_ids=[catalog[0].id],
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert PermissionSetPermission.objects.for_tenant(tenant_a.id).filter(removed_at__isnull=True).count() == 1
    grant = PermissionSetService.grant_to_user(
        tenant_a.id,
        item.id,
        tenant_a_user.id,
        expires_at=None,
        duration_days=None,
        reason="Close duties",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    with pytest.raises(SecurityConflict):
        PermissionSetService.delete_permission_set(
            tenant_a.id,
            item.id,
            actor_id=actor_id,
            reason="Still active",
            correlation_id=correlation_id,
        )
    grant = PermissionSetService.update_user_grant(
        tenant_a.id,
        grant.id,
        expires_at=timezone.now() + timedelta(days=10),
        reason="Extended",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    first = PermissionSetService.revoke_user_grant(
        tenant_a.id,
        grant.id,
        reason="Complete",
        actor_id=actor_id,
        correlation_id=correlation_id,
    ).revoked_at
    replay = PermissionSetService.revoke_user_grant(
        tenant_a.id,
        grant.id,
        reason="Replay",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert replay.revoked_at == first
    PermissionSetService.delete_permission_set(
        tenant_a.id,
        item.id,
        actor_id=actor_id,
        reason="Complete",
        correlation_id=correlation_id,
    )


def test_field_and_row_rules_use_registered_metadata_resolve_and_version(
    tenant_a, tenant_a_user, actor_id, correlation_id, resource_extension
) -> None:
    role = RoleService.create_role(
        tenant_a.id,
        name="Journal owner",
        code="journal_owner",
        role_type="custom",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    RoleService.assign_role(
        tenant_a.id,
        tenant_a_user.id,
        role.id,
        valid_from=None,
        valid_until=None,
        reason="Ownership",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    field = FieldSecurityService.create_rule(
        tenant_a.id,
        module="finance",
        resource="journals",
        field="amount",
        role_id=role.id,
        visibility="masked",
        edit_control="read_only",
        mask_pattern="####.##",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    decision = FieldSecurityService.resolve_field_access(
        tenant_a.id,
        tenant_a_user.id,
        "finance",
        "journals",
        fields=("amount", "owner_id"),
    )
    assert decision["amount"].visibility == "masked"
    assert decision["owner_id"].reason_codes == ("DENY_DEFAULT",)
    field = FieldSecurityService.update_rule(
        tenant_a.id,
        field.id,
        changes={"visibility": "redacted", "mask_pattern": ""},
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert field.visibility == "redacted"
    predicate = {"op": "owner", "field": "owner_id"}
    row = RowSecurityService.create_rule(
        tenant_a.id,
        module="finance",
        resource="journals",
        role_id=role.id,
        rule_type="ownership",
        filter_criteria=predicate,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    explanation = RowSecurityService.explain_row_access(
        tenant_a.id,
        tenant_a_user.id,
        "finance",
        "journals",
        record_attributes={"owner_id": tenant_a_user.id},
    )
    assert explanation.allowed and explanation.applied_rule_ids == (str(row.id),)
    version = RowSecurityService.update_rule(
        tenant_a.id,
        row.id,
        changes={"priority": 10},
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assert version.version == 2
    row.refresh_from_db()
    assert row.is_deleted
    RowSecurityService.delete_rule(
        tenant_a.id,
        version.id,
        actor_id=actor_id,
        reason="Retired",
        correlation_id=correlation_id,
    )
    FieldSecurityService.delete_rule(
        tenant_a.id,
        field.id,
        actor_id=actor_id,
        reason="Retired",
        correlation_id=correlation_id,
    )


def test_profile_assignment_merge_update_revoke_and_delete(
    tenant_a, tenant_a_user, actor_id, correlation_id
) -> None:
    profile = SecurityProfileService.create_profile(
        tenant_a.id,
        name="Restricted",
        mfa_required="always",
        session_timeout_minutes=15,
        download_allowed=False,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    assignment = SecurityProfileService.assign_profile(
        tenant_a.id,
        profile.id,
        user_id=tenant_a_user.id,
        role_id=None,
        reason="Privileged access",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    effective = SecurityProfileService.resolve_effective_profile(tenant_a.id, tenant_a_user.id)
    assert effective.restrictions["mfa_required"] == "always"
    assert effective.restrictions["download_allowed"] is False
    with pytest.raises(SecurityConflict):
        SecurityProfileService.delete_profile(
            tenant_a.id,
            profile.id,
            actor_id=actor_id,
            reason="Assigned",
            correlation_id=correlation_id,
        )
    SecurityProfileService.update_profile_assignment(
        tenant_a.id,
        assignment.id,
        changes={"precedence": 10},
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    SecurityProfileService.revoke_profile_assignment(
        tenant_a.id,
        assignment.id,
        reason="Complete",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    SecurityProfileService.update_profile(
        tenant_a.id,
        profile.id,
        changes={"description": "Retired profile"},
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    SecurityProfileService.delete_profile(
        tenant_a.id,
        profile.id,
        actor_id=actor_id,
        reason="Complete",
        correlation_id=correlation_id,
    )
    assert SecurityProfileAssignment.objects.get(pk=assignment.id).revoked_at is not None


def test_effective_permissions_expand_parent_explicit_deny_and_permission_set(
    tenant_a, tenant_a_user, catalog, actor_id, correlation_id
) -> None:
    parent = RoleService.create_role(
        tenant_a.id,
        name="Parent",
        code="parent",
        role_type="custom",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    child = RoleService.create_role(
        tenant_a.id,
        name="Child",
        code="child",
        role_type="custom",
        parent_role_id=parent.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    RoleService.set_role_permission(
        tenant_a.id,
        parent.id,
        catalog[0].id,
        is_granted=True,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    RoleService.set_role_permission(
        tenant_a.id,
        child.id,
        catalog[0].id,
        is_granted=False,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    RoleService.assign_role(
        tenant_a.id,
        tenant_a_user.id,
        child.id,
        valid_from=None,
        valid_until=None,
        reason="Child duties",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    permission_set = PermissionSetService.create_permission_set(
        tenant_a.id,
        name="Additional",
        default_duration_days=1,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    PermissionSetService.set_permissions(
        tenant_a.id,
        permission_set.id,
        permission_ids=[catalog[1].id],
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    PermissionSetService.grant_to_user(
        tenant_a.id,
        permission_set.id,
        tenant_a_user.id,
        expires_at=None,
        duration_days=None,
        reason="Additional",
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    effective = AccessEvaluationService.get_effective_permissions(tenant_a.id, tenant_a_user.id)
    assert catalog[0].code in effective.denied and catalog[0].code not in effective.allowed
    assert catalog[1].code in effective.allowed
    assert not AccessEvaluationService.evaluate_local(
        tenant_a.id, tenant_a_user, catalog[0].code
    ).allowed
    assert AccessEvaluationService.evaluate_local(
        tenant_a.id, tenant_a_user, catalog[1].code
    ).allowed


@pytest.mark.parametrize(
    "response,reason",
    [
        (SimpleNamespace(status_code=503, json=lambda: {}), "ENGINE_UNAVAILABLE"),
        (SimpleNamespace(status_code=200, json=lambda: {"unexpected": True}), "INVALID_POLICY_RESPONSE"),
    ],
)
def test_remote_evaluation_fail_closed_for_dependency_and_invalid_payload(
    tenant_a, tenant_a_user, monkeypatch, response, reason
) -> None:
    client = Mock()
    client.post.return_value = response
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    decision = AccessEvaluationService.evaluate_remote(
        tenant_a.id,
        tenant_a_user,
        "finance.journals:read",
        request=SimpleNamespace(correlation_id="corr-remote"),
    )
    assert not decision.allowed and decision.reason_codes == (reason,)
    client.post.assert_called_once()


def test_remote_evaluation_never_reuses_previous_allow_after_timeout(
    tenant_a, tenant_a_user, monkeypatch
) -> None:
    client = Mock()
    client.post.side_effect = [
        SimpleNamespace(
            status_code=200,
            json=lambda: {"decision": "allow", "reason_codes": ["ALLOW"], "applied_policies": ["p1"]},
        ),
        TimeoutError("timed out"),
    ]
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    first = AccessEvaluationService.evaluate_remote(tenant_a.id, tenant_a_user, "finance.journals:read")
    second = AccessEvaluationService.evaluate_remote(tenant_a.id, tenant_a_user, "finance.journals:read")
    assert first.allowed
    assert not second.allowed and second.reason_codes == ("ENGINE_UNAVAILABLE",)


def test_audit_redacts_secrets_bounds_payload_and_links_outbox(tenant_a, actor_id, correlation_id) -> None:
    event, audit = AuditService.append_with_outbox(
        tenant_a.id,
        action="security.test.changed",
        actor_type="user",
        actor_id=actor_id,
        resource_type="test",
        resource_id=uuid.uuid4(),
        decision=None,
        reason_codes=("CONFIGURATION_CHANGED",),
        details={"password": "secret", "nested": {"authorization": "Bearer secret"}, "safe": True},
        ip_address=None,
        user_agent="x" * 1000,
        correlation_id=correlation_id,
    )
    assert audit.outbox_event_id == event.id and audit.details["safe"] is True
    assert "secret" not in str(audit.details).lower()
    assert len(audit.user_agent) == 512
    with pytest.raises(SecurityValidationError):
        AuditService.append(
            tenant_a.id,
            action="security.too_large",
            actor_type="user",
            actor_id=actor_id,
            resource_type="test",
            resource_id=None,
            decision=None,
            reason_codes=(),
            details={"safe": "x" * (17 * 1024)},
            ip_address=None,
            user_agent="",
            correlation_id=correlation_id,
        )

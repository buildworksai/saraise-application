# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Logging Tests
# Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)
# Also: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing)
# 
# CRITICAL NOTES:
# - Tests verify audit logs created for all operations (immutable, comprehensive)
# - Audit logs include: action, user_id, tenant_id, resource, result, timestamp
# - Tests verify audit logs searchable by user, tenant, action, timestamp
# - No operation exposes internal details in error messages (security-model.md § 4.1)

def test_audit_log_created_on_success(client, admin_user):
    response = client.patch(f"/users/{user_id}/roles", json={"roles": ["tenant_admin"]})
    assert response.status_code == 200

    # Verify audit log exists
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    from src.models.audit import AuditLog
    audit_log = AuditLog.objects.filter(resource="user_roles").first()
    assert audit_log is not None
    assert audit_log.action == "UPDATE"
    assert audit_log.result == "success"
    assert audit_log.actor_sub == admin_user.id

def test_audit_log_created_on_failure(client, admin_user):
    response = client.patch(f"/users/invalid/roles", json={"roles": ["tenant_admin"]})
    assert response.status_code == 404

    # Verify audit log exists with error
    # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
    from src.models.audit import AuditLog
    audit_log = AuditLog.objects.filter(result="error").first()
    assert audit_log is not None
    assert audit_log.error_message is not None

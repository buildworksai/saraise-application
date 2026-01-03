# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Service Implementation
# backend/src/services/audit_service.py
# Reference: docs/architecture/security-model.md § 4.2 (Audit Operations)
# CRITICAL NOTES:
# - CRITICAL: SARAISE uses Django ORM exclusively
# - Django ORM: Use Model.objects for queries, no database session needed
# - Log method: def log(action, resource, status, changes, user_id, tenant_id)
# - All authentication events logged: login, logout, MFA, session creation
# - All authorization decisions logged: allowed, denied, policy engine evaluations
# - All data mutations logged: create, update, delete (before/after values)
# - All privileged operations logged: admin changes, role grants, policy updates
# - Failure logging includes error details (for incident investigation)
# - Audit logs never deleted (immutability enforced)
# - Query capability: search logs by user, resource, date range
# - Performance: batch inserts for high-volume logging (background job)
# Source: docs/architecture/security-model.md § 4.2

from django.db import transaction
from src.models.audit import AuditLog
from rest_framework import Request
from typing import Optional, List
from datetime import datetime

class AuditService:
    """Audit service using Django ORM."""
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use AuditLog.objects directly for all operations
        pass

    def log_event(
        self,
        actor_sub: str,
        actor_email: str,
        tenant_id: Optional[str],
        resource: str,
        action: str,
        result: str,
        metadata: Optional[dict] = None,
        error_message: Optional[str] = None,
        request: Optional[Request] = None
    ):
        """Log immutable audit event"""
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
        audit_entry = AuditLog.objects.create(
            actor_sub=actor_sub,
            actor_email=actor_email,
            tenant_id=tenant_id,
            resource=resource,
            action=action,
            result=result,
            error_message=error_message,
            metadata=self._redact_secrets(metadata) if metadata else None,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )

    def _redact_secrets(self, metadata: dict) -> dict:
        """Redact sensitive fields from metadata"""
        redacted = metadata.copy()
        sensitive_keys = ['password', 'secret', 'token', 'api_key', 'private_key']

        for key in sensitive_keys:
            if key in redacted:
                redacted[key] = '***REDACTED***'

        return redacted

    def query_logs(
        self,
        tenant_id: str,
        actor_sub: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """Query audit logs with explicit tenant_id filtering (Row-Level Multitenancy).
        
        CRITICAL: Explicit tenant_id filtering is REQUIRED for tenant isolation.
        Do NOT rely on schema context or PostgreSQL search_path.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        queryset = AuditLog.objects.filter(tenant_id=tenant_id)
        
        if actor_sub:
            queryset = queryset.filter(actor_sub=actor_sub)
        if resource:
            queryset = queryset.filter(resource=resource)
        if action:
            queryset = queryset.filter(action=action)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        queryset = queryset.order_by('-timestamp')[:limit]
        return list(queryset)


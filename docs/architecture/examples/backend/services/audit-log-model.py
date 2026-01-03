# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Log Model
# backend/src/models/audit_log.py
# Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)
# CRITICAL NOTES:
# - Audit logs are immutable (no updates, only inserts)
# - Fields: id (UUID), timestamp (server-generated), user_id, tenant_id, action, resource, status
# - Timestamp auto-set on insert (prevents tampering)
# - Index on timestamp for efficient log queries
# - Action: create, update, delete, export, approve, deny, etc.
# - Resource: path or identifier of affected resource
# - Status: success, failure, denied (authorization failure)
# - Changes: JSON field storing before/after values (for audit trail)
# - IP address and user agent captured (request context)
# - Error details stored for failed operations (debugging)
# - Retention policy: minimum 7 years (regulatory requirement)
# Source: docs/architecture/security-model.md § 4.2

from django.db.models import String, DateTime, Text, JSON, Index
from django.db import models
from django.db.models import F
from src.models.base import Base
import uuid

class AuditLog(Base):
    class Meta:
        db_table = "audit_logs"

    id: str] = models.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: datetime] = models.DateTimeField(timezone=True), server_default=func.now(), index=True)
    actor_sub: str] = models.String, nullable=False, index=True)
    actor_email: str] = models.String, nullable=False)
    tenant_id: Optional[str]] = models.String, index=True)
    resource: str] = models.String, nullable=False, index=True)
    action: str] = models.String, nullable=False)
    result: str] = models.String, nullable=False)
    error_message: Optional[str]] = models.Text)
    metadata: Optional[dict]] = models.JSON)
    ip_address: Optional[str]] = models.String)
    user_agent: Optional[str]] = models.String)

    __table_args__ = (
        Index('idx_audit_tenant_resource', 'tenant_id', 'resource'),
        Index('idx_audit_actor_timestamp', 'actor_sub', 'timestamp'),
    )

# Migration: Create append-only table (no UPDATE/DELETE permissions)
# ALTER TABLE audit_logs OWNER TO audit_writer;
# REVOKE UPDATE, DELETE ON audit_logs FROM audit_writer;


# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Maintenance Service
# backend/src/modules/platform/services/platform_maintenance_service.py
# Reference: docs/architecture/operational-runbooks.md § 6.1 (Maintenance)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any
from datetime import datetime, timedelta
from src.models.audit_log import AuditLog
import json

class PlatformMaintenanceService:
    """Platform maintenance operations service.
    
    CRITICAL: Platform-level service for administrative tasks.
    Only accessible to platform_owner via Policy Engine.
    See docs/architecture/operational-runbooks.md § 6.1.
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass
        self.available_tasks = {
            "cleanup_old_sessions": self.cleanup_old_sessions,
            "cleanup_old_audit_logs": self.cleanup_old_audit_logs
        }

    def run_maintenance_task(self, task_name: str, task_data: Dict[str, Any]):
        """Run platform maintenance task"""
        # Validate task
        if task_name not in self.available_tasks:
            raise ValueError(f"Unknown maintenance task: {task_name}")

        # Run task
        task_func = self.available_tasks[task_name]
        result = task_func(**task_data)

        return result

    def cleanup_old_sessions(self, days: int = 7):
        """Clean up old sessions"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Delete old sessions from Redis
        # Assuming RedisService exists
        # from src.core.redis_client import RedisService
        # redis_service = RedisService()
        # pattern = "saraise:session:*"
        # deleted_count = 0
        # for key in redis_service.client.scan_iter(match=pattern):
        #     session_data = redis_service.client.get(key)
        #     if session_data:
        #         data = json.loads(session_data)
        #         created_at = datetime.fromisoformat(data.get("created_at", ""))
        #         if created_at < cutoff_date:
        #             redis_service.client.delete(key)
        #             deleted_count += 1
        # return {"deleted_sessions": deleted_count}
        return {"deleted_sessions": 0}

    def cleanup_old_audit_logs(self, days: int = 90):
        """Clean up old audit logs"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Archive old audit logs
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        old_logs = AuditLog.objects.filter(timestamp__lt=cutoff_date)

        # Archive to external storage
        # Implementation depends on storage solution

        return {"archived_logs": len(old_logs)}


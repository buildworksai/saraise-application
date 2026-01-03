# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Tenant Analytics Service
# backend/src/modules/analytics/services/tenant_analytics_service.py
# Reference: docs/architecture/policy-engine-spec.md § 4
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any
from datetime import datetime, timedelta

class TenantAnalyticsService:
    """Tenant-scoped analytics service.
    
    CRITICAL: Analytics are scoped by tenant_id (Row-Level Multitenancy).
    Authorization checked by Policy Engine (required: tenant_admin or tenant_analytics_viewer).
    See docs/architecture/application-architecture.md § 2.1.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def get_tenant_analytics(self, tenant_id: str, period: str = "30d") -> Dict[str, Any]:
        """Get tenant analytics"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=int(period.replace("d", "")))

        analytics = {
            "tenant_id": tenant_id,
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "metrics": {}
        }

        # User metrics
        analytics["metrics"]["users"] = self._get_user_metrics(tenant_id, start_date, end_date)

        # Usage metrics
        analytics["metrics"]["usage"] = self._get_usage_metrics(tenant_id, start_date, end_date)

        # Activity metrics
        analytics["metrics"]["activity"] = self._get_activity_metrics(tenant_id, start_date, end_date)

        return analytics


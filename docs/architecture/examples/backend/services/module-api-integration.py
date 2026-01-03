# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Cross-Module API Integration
# backend/src/modules/module_name/services.py
# Reference: docs/architecture/module-framework.md § 4.3 (Inter-Module Communication)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from src.services.api_client import APIClient
from src.core.errors import ExternalServiceError

class ModuleService:
    """Service with cross-module API integration.
    
    CRITICAL: All inter-module communication must include authentication context.
    Tenant_id passed to dependent modules for row-level multitenancy.
    See docs/architecture/module-framework.md § 4.3.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id
        self.api_client = APIClient()

    def integrate_with_other_module(self, data: dict):
        """Integrate with another module via API"""
        try:
            response = self.api_client.call_api(
                endpoint="/api/v1/other_module/items",
                method="POST",
                data=data,
                tenant_id=self.tenant_id  # Pass tenant context to dependent module
            )
            return response
        except Exception as e:
            raise ExternalServiceError(f"Integration failed: {e}")


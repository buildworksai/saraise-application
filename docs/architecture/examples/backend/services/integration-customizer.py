# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Integration Customizer
# backend/src/customization/services/integration_customizer.py
# Reference: docs/architecture/module-framework.md § 4.1, security-model.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, Optional
from src.customization.models import CustomIntegration

class IntegrationCustomizer:
    """Custom integration management for tenant customizations.
    
    CRITICAL: All operations are tenant-scoped and require explicit
    tenant_id filtering per Row-Level Multitenancy specification.
    Authorization evaluated by Policy Engine at request time.
    See docs/architecture/security-model.md § 2.1.
    """
    
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def create_custom_integration(
        self,
        name: str,
        tenant_id: str,
        integration_type: str,
        config: Dict[str, Any]
    ):
        """Create custom integration for tenant"""
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
        integration = CustomIntegration.objects.create(
            name=name,
            tenant_id=tenant_id,
            integration_type=integration_type,
            config=config
        )
        return integration


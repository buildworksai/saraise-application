# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Form Customization Service
# backend/src/modules/*/services.py
# Reference: docs/architecture/module-framework.md § 5
# Reference: docs/architecture/application-architecture.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, Optional
from src.models.tenant_custom_form import TenantCustomForm
from src.models.form_field import FormField

class FormCustomizer:
    """
    Tenant-scoped form customization service.
    
    Architecture:
    - Custom form definitions stored per tenant
    - Row-Level Multitenancy: all queries filter by tenant_id
    - No schema context / search_path isolation
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    def customize_form_layout(
        self,
        tenant_id: int,
        entity_type: str,
        layout: Dict[str, Any]
    ) -> TenantCustomForm:
        """
        Create custom form layout for tenant entity type.
        
        CRITICAL: Explicitly set tenant_id for Row-Level Multitenancy.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        custom_form = TenantCustomForm.objects.create(
            tenant_id=tenant_id,  # CRITICAL: Explicit tenant isolation
            entity_type=entity_type,
            layout=layout
        )
        return custom_form

    def get_custom_form_layout(
        self,
        tenant_id: int,
        entity_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get custom form layout for tenant.
        
        CRITICAL: Filter by tenant_id explicitly (Row-Level Multitenancy).
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        custom_form = TenantCustomForm.objects.filter(
            tenant_id=tenant_id,
            entity_type=entity_type
        ).first()
        
        return custom_form.layout if custom_form else None

    def get_form_fields(
        self,
        tenant_id: int,
        entity_type: str
    ) -> list:
        """
        Get form fields (standard + custom) for tenant entity.
        
        CRITICAL: Filter by tenant_id for custom fields.
        """
        # Get standard fields for entity type
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM
        standard_fields = FormField.objects.filter(
            entity_type=entity_type,
            is_custom=False
        )
        
        # Get tenant-specific custom fields
        custom_fields = FormField.objects.filter(
            tenant_id=tenant_id,
            entity_type=entity_type,
            is_custom=True
        )
        
        return list(standard_fields) + list(custom_fields)

# ✅ CORRECT: Usage in route
# def create("/api/v1/forms/customize")
# def customize_form(
#     customize_request: CustomizeFormRequest,
#     request.user,
#     # Django ORM uses automatic transaction management,
#     self.policy_engine
# ):
#     # Authorization check
#     decision = policy_engine.evaluate(
#         user_id=current_user.id,
#         tenant_id=current_user.tenant_id,
#         resource="tenant.customization.forms",
#         action="edit",
#         context={"entity_type": customize_request.entity_type}
#     )
#     if not decision.allowed:
#         raise Response(status=status.HTTP_403)
#     
#     # Customize form - always use current_user.tenant_id
#     form_customizer = FormCustomizer(db)
#     custom_form = form_customizer.customize_form_layout(
#         tenant_id=current_user.tenant_id,  # CRITICAL: Use authenticated tenant
#         entity_type=customize_request.entity_type,
#         layout=customize_request.layout
#     )
#     return custom_form


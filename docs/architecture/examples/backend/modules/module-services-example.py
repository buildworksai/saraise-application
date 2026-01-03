# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module Service Structure with Row-Level Multitenancy
# backend/src/modules/module_name/services.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy § 2)
# Reference: docs/architecture/module-framework.md

from django.db import transaction
from django.db.models import Q
from typing import List, Optional
from .models import ModuleSpecificModel
from .serializers import ModuleItemCreateSerializer, ModuleItemResponseSerializer

class ModuleService:
    """Service layer for module business logic with Row-Level Multitenancy."""
    
    def create_item(
        self, 
        item_data: dict,
        tenant_id: str
    ) -> ModuleSpecificModel:
        """Create module item with explicit tenant_id filtering.
        
        CRITICAL: Row-Level Multitenancy requires explicit tenant_id on all new records.
        Do NOT rely on schema context or implicit isolation.
        """
        with transaction.atomic():
            item = ModuleSpecificModel.objects.create(
                name=item_data.get('name'),
                description=item_data.get('description'),
                tenant_id=tenant_id
            )
        return item

    def list_items(self, tenant_id: str) -> List[ModuleSpecificModel]:
        """List module items with explicit tenant_id filtering.
        
        CRITICAL: Row-Level Multitenancy requires filtering by tenant_id in all queries.
        Do NOT rely on schema context or implicit isolation.
        """
        return list(
            ModuleSpecificModel.objects.filter(
                tenant_id=tenant_id
            ).order_by('-created_at')
        )

    def get_item(self, item_id: str, tenant_id: str) -> Optional[ModuleSpecificModel]:
        """Get single item with tenant isolation.
        
        CRITICAL: Always filter by tenant_id to prevent cross-tenant data access.
        """
        return ModuleSpecificModel.objects.filter(
            module_id=item_id,
            tenant_id=tenant_id
        ).first()

    def update_item(
        self,
        item_id: str,
        item_data: dict,
        tenant_id: str
    ) -> Optional[ModuleSpecificModel]:
        """Update module item with tenant isolation.
        
        CRITICAL: Verify tenant_id before updating.
        """
        with transaction.atomic():
            item = ModuleSpecificModel.objects.filter(
                module_id=item_id,
                tenant_id=tenant_id
            ).first()
            
            if item:
                for field, value in item_data.items():
                    setattr(item, field, value)
                item.save()
            
            return item

    def delete_item(self, item_id: str, tenant_id: str) -> bool:
        """Delete module item with tenant isolation.
        
        CRITICAL: Verify tenant_id before deleting.
        """
        with transaction.atomic():
            deleted_count, _ = ModuleSpecificModel.objects.filter(
                module_id=item_id,
                tenant_id=tenant_id
            ).delete()
            return deleted_count > 0




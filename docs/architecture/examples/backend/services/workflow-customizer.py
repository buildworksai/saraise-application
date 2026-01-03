# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Workflow Customization Service
# backend/src/customization/services/workflow_customizer.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, List
from src.models.customization import CustomWorkflow

class WorkflowCustomizer:
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def create_custom_workflow(
        self,
        name: str,
        entity_name: str,
        states: List[Dict[str, Any]],
        transitions: List[Dict[str, Any]]
    ):
        """Create custom workflow for tenant with explicit tenant_id filtering.
        
        CRITICAL: All custom workflows include tenant_id for Row-Level Multitenancy.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.create() instead of db.add()/commit()
        workflow = CustomWorkflow.objects.create(
            name=name,
            entity_name=entity_name,
            tenant_id=self.tenant_id,
            states=states,
            transitions=transitions
        )

        self.# Django ORM: instance.save()workflow)
        self.# Django ORM: instance.save() or transaction.atomic()
        return workflow


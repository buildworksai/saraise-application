# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Custom Report Customization Service
# backend/src/customization/services/report_customizer.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, List
from src.models.customization import CustomReport

class ReportCustomizer:
    def __init__(self, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.tenant_id = tenant_id

    def create_custom_report(
        self,
        name: str,
        entity_name: str,
        query: str,
        columns: List[Dict[str, Any]]
    ):
        """Create custom report for tenant with explicit tenant_id filtering.
        
        CRITICAL: All custom reports include tenant_id for Row-Level Multitenancy.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        report = CustomReport.objects.create(
            name=name,
            entity_name=entity_name,
            tenant_id=self.tenant_id,
            query=query,
            columns=columns
        )
        return report


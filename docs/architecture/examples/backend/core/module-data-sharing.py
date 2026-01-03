# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Module data sharing patterns
# backend/src/core/module_data_sharing.py
# CRITICAL: SARAISE uses Django ORM exclusively
from typing import Dict, Any, Optional
from django.db import transaction
from src.core.models import SharedData

class ModuleDataSharing:
    """Module data sharing using Django ORM."""
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        pass

    @transaction.atomic
    def share_data(self, source_module: str, target_module: str, data: Dict[str, Any]):
        """Share data between modules"""
        # Store shared data
        # ✅ CORRECT: Django ORM - use Model.objects.create() or instance.save()
        shared_data = SharedData.objects.create(
            source_module=source_module,
            target_module=target_module,
            data=data
        )
        return shared_data

    def get_shared_data(self, source_module: str, target_module: str) -> Optional[Dict[str, Any]]:
        """Get shared data from another module"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        shared_data = SharedData.objects.filter(
            source_module=source_module,
            target_module=target_module
        ).first()
        return shared_data.data if shared_data else None


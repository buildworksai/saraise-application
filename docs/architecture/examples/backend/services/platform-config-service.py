# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Platform Configuration Service
# backend/src/modules/platform/services/platform_config_service.py
# Reference: docs/architecture/application-architecture.md § 3.1 (Platform Services)
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from typing import Dict, Any, Optional
from src.modules.platform.models import PlatformSettings

class PlatformConfigService:
    """Platform-wide configuration management service.
    
    CRITICAL: Platform-level service (no tenant isolation).
    Only accessible to platform_owner role via Policy Engine.
    See docs/architecture/security-model.md § 3.1.
    """
    
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use PlatformSettings.objects directly for all operations
        pass

    def get_setting(self, key: str) -> Optional[Dict[str, Any]]:
        """Get platform setting"""
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        setting = PlatformSettings.objects.filter(key=key).first()
        return setting.value if setting else None

    @transaction.atomic
    def set_setting(self, key: str, value: Dict[str, Any], updated_by: str):
        """Set platform setting"""
        # ✅ CORRECT: Django ORM - use Model.objects.get_or_create() or filter().first()
        setting = PlatformSettings.objects.filter(key=key).first()

        if setting:
            setting.value = value
            setting.updated_by = updated_by
            setting.save()
        else:
            setting = PlatformSettings.objects.create(
                id=f"setting_{key}",
                key=key,
                value=value,
                updated_by=updated_by
            )
        return setting

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all platform settings"""
        # ✅ CORRECT: Django ORM - use Model.objects.all() using Django ORM QuerySet
        settings = PlatformSettings.objects.all()
        return {setting.key: setting.value for setting in settings}

